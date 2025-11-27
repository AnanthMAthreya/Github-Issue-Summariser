import os
import json
from dotenv import load_dotenv

load_dotenv()

# Prefer GOOGLE_API_KEY env var, but accept GEMINI_API_KEY as fallback
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
MODEL_ENV = os.getenv("GEMINI_MODEL", "models/text-bison-001")

def _extract_text_from_response(resp):
    # Best-effort extraction of text from various SDK/REST response shapes
    if resp is None:
        return None
    # object with attribute
    if hasattr(resp, "text"):
        return resp.text
    if isinstance(resp, dict):
        # candidates -> output/content/text
        c = resp.get("candidates")
        if isinstance(c, list) and c:
            first = c[0]
            if isinstance(first, dict):
                return first.get("output") or first.get("content") or first.get("text") or json.dumps(first)
            return str(first)
        for k in ("output", "content", "text"):
            if k in resp:
                return resp.get(k)
        return json.dumps(resp)
    return str(resp)

def summarize_issue(issue_text: str) -> str:
    """Try to use the `google.generativeai` SDK if available to summarize text.
    If the SDK isn't installed, instruct how to install it.
    """
    try:
        import google.generativeai as genai
    except Exception as e:
        return (
            "google-generative-ai SDK not installed. Install with:\n"
            "    pip install google-generative-ai\n"
            "Then re-run this script. Error: " + str(e)
        )

    if not API_KEY:
        return "No API key found in environment (`GOOGLE_API_KEY` or `GEMINI_API_KEY`)."

    genai.configure(api_key=API_KEY)

    # Normalize model name: SDK often accepts just the short name like 'gemini-2.5-flash'
    model_name = MODEL_ENV
    if model_name.startswith("models/"):
        model_name = model_name.split("/", 1)[1]

    prompt = f"Summarize the following GitHub issue into 3 concise bullet points:\n\n{issue_text}\n"

    # Try model object API if available, otherwise try top-level helpers
    resp = None
    gm = getattr(genai, "GenerativeModel", None)
    if gm:
        try:
            model_obj = gm(model_name)
            # try a set of likely method names
            for method_name in ("generate_content", "generateContent", "generate_text", "generateText", "generate"):
                fn = getattr(model_obj, method_name, None)
                if callable(fn):
                    try:
                        resp = fn(prompt)
                    except TypeError:
                        # some SDK methods expect different args
                        resp = fn("", prompt)
                    break
        except Exception as e:
            return f"SDK model usage failed: {e}"
    else:
        # Try top-level SDK helpers (may vary by SDK version)
        for fn_name in ("generate_text", "generateText", "generate", "generate_content", "generateContent"):
            fn = getattr(genai, fn_name, None)
            if callable(fn):
                try:
                    resp = fn(model=model_name, prompt=prompt)
                except TypeError:
                    try:
                        resp = fn(model=model_name, input=prompt)
                    except Exception as e:
                        resp = f"call failed: {e}"
                break

    return _extract_text_from_response(resp) or "(no textual response)"


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        issue_text = " ".join(sys.argv[1:])
    else:
        issue_text = (
            "Example: When I try to save my settings, the page reloads and the changes are lost. "
            "Steps to reproduce: ..."
        )

    out = summarize_issue(issue_text)
    print("--- Summary output ---")
    print(out)
