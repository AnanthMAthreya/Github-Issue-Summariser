import os
import requests
import streamlit as st

st.set_page_config(page_title="AI-powered Github issue summarizer")

st.title("AI-powered Github issue summarizer")

st.markdown("Enter a public GitHub repository URL (e.g., https://github.com/facebook/react) and an issue number.")

repo_url = st.text_input("GitHub repository URL", placeholder="https://github.com/facebook/react")
issue_number = st.text_input("Issue number", placeholder="1")

backend_url = os.getenv("BACKEND_URL", "http://localhost:8000/summarize")

if st.button("Submit"):
    if not repo_url or not issue_number:
        st.error("Please provide both a repository URL and an issue number.")
    else:
        try:
            issue_num_int = int(issue_number)
        except ValueError:
            st.error("Issue number must be an integer.")
        else:
            payload = {"repo_url": repo_url, "issue_number": issue_num_int}
            with st.spinner("Contacting backend and fetching summary..."):
                try:
                    resp = requests.post(backend_url, json=payload, timeout=30)
                except Exception as e:
                    st.error(f"Error contacting backend: {e}")
                else:
                    if resp.status_code == 200:
                        data = resp.json()
                        st.subheader("Summary")
                        st.code(data.get("summary", "(no summary returned)"))
                    else:
                        st.error(f"Backend error {resp.status_code}: {resp.text}")
