import os
import os
import requests
import streamlit as st

# Simple Streamlit UI for the Github-Issue-Summariser project.
# - Accepts a single GitHub issue URL from the user
# - Parses the URL client-side to extract owner/repo and issue number
# - Posts to the backend `/analyze` endpoint and renders the structured analysis

st.set_page_config(page_title="AI-powered Github issue summarizer")

st.title("AI-powered Github issue summarizer")

st.markdown(
    "Enter a public GitHub repository issue URL (e.g., https://github.com/facebook/react/issues/35225)"
)

# Single input for the full issue link
issue_url = st.text_input("GitHub issue URL", placeholder="https://github.com/facebook/react/issues/35225")

# Backend URL (can be overridden with BACKEND_URL env var)
backend_url = os.getenv("BACKEND_URL", "http://localhost:8000/analyze")

from urllib.parse import urlparse


def _parse_issue_url(url: str):
    """Parse a GitHub issue URL and return a canonical repo URL and the issue number.

    Accepts forms like:
      - https://github.com/owner/repo/issues/123
      - github.com/owner/repo/issues/123 (scheme added)
      - Handles backslashes pasted from Windows paths

    Returns:
      (repo_url, issue_number)

    Raises ValueError on malformed input.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Empty URL")
    # Normalize common paste mistakes (backslashes)
    u = url.strip().replace("\\", "/")
    # Ensure urlparse sees a scheme; default to https when missing
    parsed = urlparse(u if "://" in u else ("https://" + u))
    parts = [p for p in parsed.path.split("/") if p]
    # Validate the hostname is github.com so frontend and backend behave consistently
    hostname = (parsed.hostname or "").lower()
    allowed_hosts = {"github.com", "www.github.com"}
    if hostname not in allowed_hosts:
        # Match backend error text so the UI shows the same message as Postman
        raise ValueError(f"Repository URL must be on github.com (got host '{hostname}')")
    # Expect a path containing 'issues' followed by the number
    if "issues" not in parts:
        raise ValueError("URL does not look like a GitHub issue URL (missing '/issues/').")
    idx = parts.index("issues")
    if idx < 2:
        raise ValueError("URL path is too short to contain owner and repo.")
    owner = parts[idx - 2]
    repo = parts[idx - 1]
    try:
        issue_number = int(parts[idx + 1])
    except Exception:
        raise ValueError("Could not determine issue number from URL")
    # Build a canonical repo URL for the backend to parse
    repo_url = f"https://github.com/{owner}/{repo}"
    return repo_url, issue_number


if st.button("Submit"):
    # Validate and parse the single issue URL, then call the backend unchanged
    if not issue_url:
        st.error("Please paste a GitHub issue URL.")
    else:
        try:
            repo_url_parsed, issue_num_int = _parse_issue_url(issue_url)
        except Exception as e:
            st.error(f"Invalid issue URL: {e}")
        else:
            payload = {"repo_url": repo_url_parsed, "issue_number": issue_num_int}
            with st.spinner("Analysis loading..."):
                try:
                    resp = requests.post(backend_url, json=payload, timeout=60)
                except Exception as e:
                    st.error(f"Error contacting backend: {e}")
                    resp = None

            # Render the response if available
            if resp is not None:
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception as e:
                        st.error(f"Failed to decode JSON from backend: {e}")
                    else:
                        # Structured display of returned analysis fields
                        st.subheader("Summary")
                        st.write(data.get("summary", "(no summary returned)"))

                        col1, col2, col3 = st.columns([2, 1, 2])
                        with col1:
                            st.markdown("**Type**")
                            st.write(data.get("type", ""))
                        with col2:
                            st.markdown("**Priority**")
                            st.write(data.get("priority_score", ""))
                        with col3:
                            st.markdown("**Potential Impact**")
                            st.write(data.get("potential_impact", ""))

                        st.subheader("Justification for the priority")
                        st.write(data.get("justification", ""))

                        st.subheader("Suggested Labels")
                        labels = data.get("suggested_labels", []) or []
                        if labels:
                            st.write(", ".join([f"`{l}`" for l in labels]))
                        else:
                            st.write("(none suggested)")

                        # Raw JSON expander removed per request; show only formatted fields.
                else:
                    # Show backend error to the user (status + body)
                    st.error(f"Backend error {resp.status_code}: {resp.text}")
