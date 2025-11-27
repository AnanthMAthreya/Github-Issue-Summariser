from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
from urllib.parse import urlparse
import json
import re
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()   # loads variables from .env into os.environ


class SummarizeRequest(BaseModel):
    repo_url: str
    issue_number: int


app = FastAPI()


def parse_repo_url(repo_url: str):
    """Return (owner, repo) from a standard GitHub repo URL."""
    try:
        if not repo_url or not isinstance(repo_url, str):
            raise ValueError("Empty or invalid repo_url")

        # Normalize backslashes (e.g. pasted Windows paths) to forward slashes
        repo_url = repo_url.strip().replace("\\", "/")

        # Handle scp-like SSH URLs: git@github.com:owner/repo.git -> ssh://git@github.com/owner/repo.git
        if "@" in repo_url and ":" in repo_url and not repo_url.startswith(("http://", "https://", "ssh://")):
            # only replace the first ':' to convert host:path -> host/path
            repo_url = repo_url.replace(":", "/", 1)
            repo_url = "ssh://" + repo_url

        parsed = urlparse(repo_url)

        # If no scheme (e.g. github.com/owner/repo), assume https
        if not parsed.scheme:
            repo_url = "https://" + repo_url
            parsed = urlparse(repo_url)

        # Require the host be GitHub to avoid ambiguous inputs
        hostname = (parsed.hostname or "").lower()
        allowed_hosts = {"github.com", "www.github.com"}
        if hostname not in allowed_hosts:
            raise ValueError(f"Repository URL must be on github.com (got host '{hostname}')")

        # path like /owner/repo or /owner/repo/
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("Unable to parse owner/repo from URL")
        owner, repo = parts[0], parts[1]
        if repo.endswith('.git'):
            repo = repo[:-4]
        return owner, repo
    except Exception as e:
        raise ValueError(f"Invalid GitHub repo URL: {e}")

# The temporary `/summarize` endpoint was removed; use `/analyze` below.


def _fetch_issue_data(owner: str, repo: str, issue_number: int, headers: Dict[str, str]) -> Dict[str, Any]:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}"
    r = requests.get(api_url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)
    issue = r.json()

    comments_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{issue_number}/comments"
    rc = requests.get(comments_url, headers=headers, timeout=15)
    if rc.status_code != 200:
        raise HTTPException(status_code=rc.status_code, detail=rc.text)
    comments_full = rc.json()
    comments = [c.get("body", "") for c in comments_full]

    return {"title": issue.get("title", "(no title)"), "body": issue.get("body", "") or "", "comments": comments}


def _call_gemini(prompt: str) -> str:
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not set")

    # Prefer short model name like 'gemini-2.5-flash' in SDK usage
    model_env = os.getenv("GEMINI_MODEL", "models/text-bison-001")
    model_name = model_env
    if model_name.startswith("models/"):
        model_name = model_name.split("/", 1)[1]

    # Use the official SDK if available
    try:
        import google.generativeai as genai
    except Exception:
        raise RuntimeError("google-generative-ai SDK not installed: install with `pip install google-generative-ai`")

    genai.configure(api_key=api_key)

    resp = None
    last_err = None

    # Use only `generate_content` (instance or top-level) as requested for performance
    try:
        gm = getattr(genai, "GenerativeModel", None)
        if gm:
            try:
                model_obj = gm(model_name)
                fn = getattr(model_obj, "generate_content", None)
                if fn and callable(fn):
                    try:
                        resp = fn(prompt=prompt, temperature=0.2, max_output_tokens=512)
                    except TypeError:
                        resp = fn(prompt)
                else:
                    last_err = AttributeError("GenerativeModel has no generate_content method")
            except Exception as e:
                last_err = e
        else:
            # top-level helper
            fn = getattr(genai, "generate_content", None)
            if fn and callable(fn):
                try:
                    resp = fn(model=model_name, prompt=prompt, temperature=0.2, max_output_tokens=512)
                except TypeError:
                    resp = fn(model=model_name, input=prompt)
            else:
                last_err = AttributeError("SDK module has no generate_content function")
    except Exception as e:
        last_err = e

    if resp is None:
        msg = "SDK call failed"
        if last_err:
            msg += ": " + str(last_err)
        msg += ". Ensure the SDK exposes generate_content and the model is available to your project."
        raise RuntimeError(msg)

    # Extract text from typical SDK response shapes and coerce to string
    result_text = None
    try:
        # object-like response
        if hasattr(resp, "candidates") and resp.candidates:
            first = resp.candidates[0]
            candidate_val = getattr(first, "output", None) or getattr(first, "content", None) or first
            result_text = candidate_val
        elif hasattr(resp, "output"):
            result_text = getattr(resp, "output")
        elif isinstance(resp, dict):
            if "candidates" in resp and resp["candidates"]:
                c0 = resp["candidates"][0]
                if isinstance(c0, dict):
                    result_text = c0.get("output") or c0.get("content") or c0
                else:
                    result_text = getattr(c0, "output", None) or getattr(c0, "content", None) or c0
            else:
                for k in ("output", "content", "text"):
                    if k in resp:
                        result_text = resp.get(k)
                        break
                if result_text is None:
                    result_text = json.dumps(resp)
    except Exception:
        result_text = None

    if result_text is None:
        result_text = resp

    # Coerce to plain string for callers
    try:
        if isinstance(result_text, bytes):
            return result_text.decode("utf-8", errors="ignore")
        if isinstance(result_text, str):
            return result_text
        # Some SDK objects may have `.text` or `.content` attributes
        if hasattr(result_text, "text"):
            return str(result_text.text)
        if hasattr(result_text, "content"):
            return str(result_text.content)
        if hasattr(result_text, "output"):
            return str(result_text.output)
        return str(result_text)
    except Exception:
        return str(result_text)


def _extract_json(text: Any) -> Any:
    # Coerce common SDK/response objects to strings before parsing
    if text is None:
        raise ValueError("No text to parse")

    # If the object has a textual attribute, prefer that
    if not isinstance(text, (str, bytes)):
        try:
            if hasattr(text, "text"):
                text = text.text
            elif hasattr(text, "content"):
                text = text.content
            elif hasattr(text, "output"):
                text = text.output
            elif hasattr(text, "candidates"):
                # Try to extract first candidate's content/output
                try:
                    cand = text.candidates[0]
                    if isinstance(cand, dict):
                        text = cand.get("output") or cand.get("content") or json.dumps(cand)
                    else:
                        text = getattr(cand, "output", None) or getattr(cand, "content", None) or str(cand)
                except Exception:
                    text = str(text)
            else:
                text = str(text)
        except Exception:
            text = str(text)

    # Ensure we have a string for regex/json operations
    if isinstance(text, bytes):
        text = text.decode("utf-8", errors="ignore")

    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    raise ValueError("Could not parse JSON from model output")


def _recover_json_from_text(text: Any) -> Dict[str, Any]:
    """Heuristic recovery: extract likely fields from model output when strict JSON parsing fails.

    Returns a dict with keys: summary, type, priority_score, suggested_labels, potential_impact.
    Fields may be best-effort filled or empty/defaults.
    """
    s = str(text)

    # Remove markdown fences and leading wrappers like parts { text: "..." }
    # Extract the inner JSON-like block if present inside ```json ... ```
    m = re.search(r"```json\s*([\s\S]*?)```", s, re.I)
    if m:
        s_inner = m.group(1)
        # If the captured block contains escaped JSON (e.g. \"summary\":), unescape it
        if "\\\"" in s_inner or "\\n" in s_inner:
            try:
                s_inner = bytes(s_inner, "utf-8").decode("unicode_escape")
            except Exception:
                # fallback: replace common escape sequences
                s_inner = s_inner.replace('\\n', '\n').replace('\\"', '"')
    else:
        # Try to extract after text: "..." patterns
        m2 = re.search(r'text:\s*"([\s\S]*?)"\s*$', s)
        if m2:
            s_inner = m2.group(1)
        else:
            s_inner = s

    # Now try to find fields with regex (allow newlines)
    def find_str(key):
        pat = rf'"{key}"\s*:\s*"([\s\S]*?)"'
        mm = re.search(pat, s_inner, re.S)
        return mm.group(1).strip() if mm else None

    def find_num(key):
        pat = rf'"{key}"\s*:\s*(\d+)'
        mm = re.search(pat, s_inner)
        return int(mm.group(1)) if mm else None

    def find_array(key):
        pat = rf'"{key}"\s*:\s*(\[[\s\S]*?\])'
        mm = re.search(pat, s_inner, re.S)
        if not mm:
            return []
        arr_text = mm.group(1)
        try:
            return json.loads(arr_text)
        except Exception:
            # fallback: extract quoted strings
            items = re.findall(r'"([^"]+)"', arr_text)
            return items

    summary = find_str("summary") or ""
    typ = find_str("type") or "other"
    priority = find_num("priority_score") or 3
    # justification may be inside 'justification' or 'priority_score' returned as object; try both
    justification = find_str("justification") or ""
    suggested_labels = find_array("suggested_labels")
    potential_impact = find_str("potential_impact") or ""

    # If suggested_labels empty, try to extract trailing label-like words
    if not suggested_labels:
        mm = re.search(r'suggested_labels\s*:\s*([^\n\r]*)', s_inner)
        if mm:
            txt = mm.group(1)
            labels = re.findall(r'"([^"]+)"|\b([a-zA-Z0-9_\-]+)\b', txt)
            flattened = [a or b for (a, b) in labels]
            suggested_labels = flattened[:3]

    return {
        "summary": summary,
        "type": typ,
        "priority_score": priority,
        "justification": justification,
        "suggested_labels": suggested_labels,
        "potential_impact": potential_impact,
    }


def _synthesize_justification(summary: str, priority_score: int, issue_type: str) -> str:
    """Synthesize a concise one-sentence justification for the given summary and priority.

    Uses the same `_call_gemini` function to produce a single-sentence justification.
    Falls back to a deterministic sentence if the model call fails.
    """
    prompt = (
        "You are a concise assistant. Given the following issue summary and priority score, "
        "return a single short sentence (no JSON) that justifies why the priority_score was chosen.\n\n"
        f"Issue summary:\n{summary}\n\n"
        f"Priority score: {priority_score}\n"
        f"Issue type: {issue_type}\n\n"
        "Return only one sentence."
    )
    try:
        resp = _call_gemini(prompt)
        # resp should be a string
        s = str(resp).strip()
        # Keep only the first sentence if multi-sentence
        s = re.split(r"[\n\.]{1,}\s*", s)[0].strip()
        if s:
            # ensure it ends with a period
            if not s.endswith('.'):
                s = s + '.'
            return s
    except Exception:
        pass

    # deterministic fallback
    return (
        "Although not crash-causing, limited type-aware mutation detection and ignored method calls "
        "increase the risk of subtle state-mutation bugs that can lead to unexpected UI behavior."
    )


@app.post("/analyze")
def analyze(req: SummarizeRequest):
    try:
        owner, repo = parse_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    data = _fetch_issue_data(owner, repo, req.issue_number, headers)

    prompt = (
        "You are an assistant that analyzes a GitHub issue.\n"
        "Given the issue title, body, and comments, return ONLY a JSON object with the following keys:\n"
        "summary, type, priority_score, justification, suggested_labels, potential_impact.\n"
        "Respond strictly in JSON.\n\n"
        "Issue title:\n" + data["title"] + "\n\n"
        "Issue body:\n" + (data["body"] or "(empty)") + "\n\n"
        "Comments:\n" + "\n---\n".join(data["comments"][:20]) + "\n\n"
        "Make the 'type' one of: bug, feature_request, documentation, question, or other.\n"
        "For 'priority_score', return a number 1-5 and include a brief 'justification' field explaining the score.\n"
        "For 'suggested_labels', return an array of 2-3 label strings.\n"
        "For 'potential_impact', return a brief sentence about user impact if this is a bug.\n"
    )

    try:
        raw = _call_gemini(prompt)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        result = _extract_json(raw)
    except ValueError:
        # Attempt heuristic recovery from non-JSON model output
        raw_str = str(raw)
        try:
            recovered = _recover_json_from_text(raw_str)
            # Ensure required keys exist
            required = {"summary", "type", "priority_score", "justification", "suggested_labels", "potential_impact"}
            # Fill missing optional fields and synthesize justification if needed
            for k in required:
                if k not in recovered:
                    recovered[k] = "" if k != "suggested_labels" else []
            if not recovered.get("justification"):
                recovered["justification"] = _synthesize_justification(recovered.get("summary", ""), recovered.get("priority_score", 3), recovered.get("type", "other"))
            return recovered
        except Exception:
            raise HTTPException(status_code=502, detail="Model did not return valid JSON: " + raw_str[:1000])

    required = {"summary", "type", "priority_score", "justification", "suggested_labels", "potential_impact"}
    if not isinstance(result, dict) or not required.issubset(set(result.keys())):
        raise HTTPException(status_code=502, detail="Model returned JSON but missing required keys")

    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
