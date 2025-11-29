# Github-Issue-Summariser

A small developer tool that demonstrates a Secure backend + Lightweight UI pattern for automatically summarising and analysing GitHub issues using an LLM (Gemini / Google Generative Models).

This repository contains:
- `backend.py` — FastAPI app that fetches issue title/body/comments from GitHub and calls a large-model to return a structured JSON analysis.
- `app.py` — Streamlit frontend that calls the backend `/analyze` endpoint and displays a human-friendly view of the returned fields.

Key features
- Fetches issue data server-side (title, body, comments) to keep tokens and secrets private.
- Uses a generative model to return a strict JSON object with fields: `summary`, `type`, `priority_score`, `justification`, `suggested_labels`, `potential_impact`.
- Robust parsing and recovery for noisy model output and a fallback `justification` generator to ensure the UI always receives a usable justification.

Requirements
- Python 3.10+ (or your environment's supported 3.x release)
- Recommended: create and activate a virtual environment before installing packages.

Install
 - Clone the repository
 - From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If you plan to use the Google Generative AI SDK, install it in the same environment. In many environments the package name is `google-generative-ai`:

```powershell
pip install google-generative-ai
```

If `pip` cannot find `google-generative-ai` in your environment, consult Google Generative Models documentation for the proper install method for your environment or use the REST approach (the backend can be adjusted to use REST instead).

Environment variables
- `GOOGLE_API_KEY` — API key for Generative Models (required for LLM calls). Also accepts `GEMINI_API_KEY` if you prefer that name in your environment.
	- Note: this repository does NOT include a Google/Gemini API key for security reasons. You must create and use your own API key and set it in your local `.env`. If you require a project-specific key, contact the repository owner to request access (do NOT share keys in public channels).
- `GEMINI_MODEL` — Optional model id (e.g. `models/gemini-1.0` or `gemini-2.5-flash`). The backend normalises names that start with `models/`.
- `GITHUB_TOKEN` — Optional GitHub personal access token to increase API rate limits and access private repos (if needed). Keep this secret and do not expose it client-side.
	- Generate a token: go to GitHub -> Settings -> Developer settings -> Personal access tokens -> Generate new token. For public repo access the `public_repo` scope is sufficient; add `repo` if you need private repo access.
	- Store it locally: create a `.env` file in the project root and add the token like:

```text
GITHUB_TOKEN=ghp_yourtokenhere
```

The repository does not include any tokens (the value is intentionally left blank) for security — do NOT commit your `.env` file.
- `BACKEND_URL` — Optional URL the Streamlit UI uses to contact the backend (default `http://localhost:8000/analyze`).

Running locally

1) Start the backend (FastAPI)

```powershell
# from project root
uvicorn backend:app --reload --port 8000
# or: python backend.py
```

2) Start the Streamlit UI in a new terminal

```powershell
streamlit run app.py
```

3) In the UI, paste a full GitHub issue URL (for example `https://github.com/facebook/react/issues/35225`) and click Submit. The UI will call the backend `/analyze` endpoint and show the formatted analysis.

Output format
- The backend returns a JSON object with these keys:
	- `summary`: short human-friendly summary of the issue
	- `type`: one of `bug`, `feature_request`, `documentation`, `question`, or `other`
	- `priority_score`: integer 1-5
	- `justification`: single-sentence justification for the chosen priority
	- `suggested_labels`: array of 2-3 label strings
	- `potential_impact`: brief sentence describing potential user-facing impact

Security notes
- Keep `GITHUB_TOKEN` and `GOOGLE_API_KEY` out of client-side code and version control.
- If you accidentally commit keys, rotate/revoke them immediately.

Troubleshooting
- If the backend raises an error about the SDK not being installed, ensure `google-generative-ai` (or the current SDK package) is installed in the same Python environment used to run `backend.py`.
- If the model returns malformed JSON, the backend includes heuristic recovery and will synthesise a `justification` when missing — check the server logs for the raw model response if you need to debug.
- If you see 403/404 model errors from the Google API, verify the API key's project has access to the requested model (use the Generative Models `GET /v1/models` with your key to inspect available models) and that the Generative AI API is enabled in the project.

Development notes
- The backend currently uses the SDK `generate_content` method for generation. This reduces method-probing and improves per-request performance. If your SDK exposes a different method name, update `backend.py` accordingly.
- Pagination: GitHub comment fetching currently fetches the first page of comments. If you expect many comments, consider paginating across the `Link` header and concatenating results.
- Tests and extension points: add unit tests around `_recover_json_from_text` and `_synthesize_justification` to ensure parsing resiliency.

Next improvements you might want
- Add a server endpoint `/models` to list available models for the configured API key (helps debug model access).
- Cache model outputs for identical inputs to reduce repeated LLM calls.
- Add rate-limiting and authentication on the backend before deploying publicly.

License & attribution
- This project is a small demo and does not include a license file; add one as needed for your usage.

If you'd like, I can also add a short `DEVELOPMENT.md` with notes on testing and extending the backend, or add a small `requirements-dev.txt` for development-only dependencies.
