# Github-Issue-Summariser

Simple Streamlit UI + FastAPI backend that fetches a public GitHub issue and returns a short summary.

Running locally
 - Install dependencies (prefer a venv):
```
pip install -r requirements.txt
```
 - Start the backend (from project root):
```
python backend.py
```
 - Start the Streamlit UI in a separate terminal:
```
streamlit run app.py
```

Notes
 - The backend calls the GitHub REST API. You can optionally set a `GITHUB_TOKEN` environment variable to increase rate limits and avoid hitting the unauthenticated API rate cap.
 - It's recommended to keep GitHub API calls and tokens in the backend (not in the browser) for security and to protect credentials.