from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import requests
from urllib.parse import urlparse


class SummarizeRequest(BaseModel):
    repo_url: str
    issue_number: int


app = FastAPI()


def parse_repo_url(repo_url: str):
    """Return (owner, repo) from a standard GitHub repo URL."""
    try:
        parsed = urlparse(repo_url)
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


@app.post("/summarize")
def summarize(req: SummarizeRequest):
    try:
        owner, repo = parse_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"

    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{req.issue_number}"
    r = requests.get(api_url, headers=headers, timeout=15)
    if r.status_code != 200:
        raise HTTPException(status_code=r.status_code, detail=r.text)

    issue = r.json()
    title = issue.get("title", "(no title)")
    body = issue.get("body", "") or ""
    comments = issue.get("comments", 0)

    # Very simple summary: title + truncated body + counts
    trimmed_body = body.strip()
    if len(trimmed_body) > 800:
        trimmed_body = trimmed_body[:800] + "..."

    summary_text = (
        f"Title: {title}\n\n"
        f"Summary: {trimmed_body if trimmed_body else '(no body)'}\n\n"
        f"Comments: {comments}\n"
        f"URL: {issue.get('html_url')}"
    )

    return {"summary": summary_text}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
