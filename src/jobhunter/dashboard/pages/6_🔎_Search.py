from typing import Any

import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.db.session import get_session
from jobhunter.db.repos.search import SearchRepo
from jobhunter.dashboard.components import format_relative_time

st.set_page_config(page_title="Search Results", page_icon="🔎", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("🔎 Search Results")

query = st.session_state.get("global_search_query", "")

if not query:
    st.info("Please enter a search query in the sidebar.")
else:
    st.write(f"Showing results for: **{query}**")

    @st.cache_data(ttl=60)
    def perform_search(search_query: str) -> dict[str, list[Any]]:
        with get_session() as session:
            repo = SearchRepo(session)
            return repo.search(search_query)

    results = perform_search(query)

    total_results = len(results["jobs"]) + len(results["applications"]) + len(results["contacts"])

    if total_results == 0:
        st.warning("No results found.")
    else:
        st.write(f"Found {total_results} results.")

        tabs = st.tabs(
            [
                f"Jobs ({len(results['jobs'])})",
                f"Applications ({len(results['applications'])})",
                f"Contacts ({len(results['contacts'])})",
            ]
        )

        with tabs[0]:
            if not results["jobs"]:
                st.info("No matching jobs.")
            for job in results["jobs"]:
                with st.container(border=True):
                    col1, col2 = st.columns([0.8, 0.2])
                    with col1:
                        st.subheader(job.title)
                        st.write(f"**{job.company}**")
                        st.caption(
                            f"Source: {job.source} | Scraped: {format_relative_time(job.scraped_at)}"
                        )
                    with col2:
                        if st.button("View in Matches", key=f"job_{job.id}"):
                            st.switch_page("pages/1_📥_New_Matches.py")
                            # We'll use query params for focus in the next step
                            st.query_params["focus"] = str(job.id)

        with tabs[1]:
            if not results["applications"]:
                st.info("No matching applications.")
            for app in results["applications"]:
                with st.container(border=True):
                    col1, col2 = st.columns([0.8, 0.2])
                    with col1:
                        st.subheader(f"{app.job.title} @ {app.job.company}")
                        st.write(
                            f"Status: `{app.status.value}` | Applied: {format_relative_time(app.applied_at)}"
                        )
                        if app.notes:
                            st.markdown(f"**Notes snippet:** {app.notes[:200]}...")
                    with col2:
                        if st.button("View in Pipeline", key=f"app_{app.id}"):
                            st.switch_page("pages/2_📋_Pipeline.py")
                            st.query_params["focus"] = str(app.id)

        with tabs[2]:
            if not results["contacts"]:
                st.info("No matching contacts.")
            for contact in results["contacts"]:
                with st.container(border=True):
                    col1, col2 = st.columns([0.8, 0.2])
                    with col1:
                        st.subheader(contact.name)
                        st.write(
                            f"**{contact.company or 'Unknown Company'}** | {contact.role or 'No Role'}"
                        )
                        st.caption(f"Status: {contact.status.value}")
                    with col2:
                        if st.button("View in Outreach", key=f"contact_{contact.id}"):
                            st.switch_page("pages/4_💌_Outreach.py")
                            st.query_params["focus"] = str(contact.id)
