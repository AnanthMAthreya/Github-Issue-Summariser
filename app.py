import os
import requests
import streamlit as st

st.set_page_config(page_title="AI-powered Github issue summarizer")

st.title("AI-powered Github issue summarizer")

st.markdown("Enter a public GitHub repository URL (e.g., https://github.com/facebook/react) and an issue number.")

repo_url = st.text_input("GitHub repository URL", placeholder="https://github.com/facebook/react")
issue_number = st.text_input("Issue number", placeholder="1")

backend_url = os.getenv("BACKEND_URL", "http://localhost:8000/analyze")

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
            with st.spinner("Contacting backend and requesting analysis..."):
                try:
                    resp = requests.post(backend_url, json=payload, timeout=60)
                except Exception as e:
                    st.error(f"Error contacting backend: {e}")
                    resp = None

            if resp is not None:
                if resp.status_code == 200:
                    try:
                        data = resp.json()
                    except Exception as e:
                        st.error(f"Failed to decode JSON from backend: {e}")
                    else:
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

                        st.subheader("Justification")
                        st.write(data.get("justification", ""))

                        st.subheader("Suggested Labels")
                        labels = data.get("suggested_labels", []) or []
                        if labels:
                            st.write(", ".join([f"`{l}`" for l in labels]))
                        else:
                            st.write("(none suggested)")

                        # Raw JSON expander removed per request; show only formatted fields.
                else:
                    st.error(f"Backend error {resp.status_code}: {resp.text}")
