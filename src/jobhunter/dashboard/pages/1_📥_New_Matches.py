import streamlit as st
import time
import uuid
from typing import Any, Optional, TYPE_CHECKING
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.components import render_job_card
from jobhunter.db.session import get_session
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.application import ApplicationRepo
from jobhunter.db.enums import JobTier, JobStatus, ApplicationStatus

if TYPE_CHECKING:
    from jobhunter.db.models import Job

# Page configuration
st.set_page_config(page_title="New Matches", page_icon="📥", layout="wide")

# Authentication
require_auth()

# Main Layout
render_header()
render_sidebar()

# Initialize session state for modals
if "show_apply_modal" not in st.session_state:
    st.session_state.show_apply_modal = False
if "selected_job_id" not in st.session_state:
    st.session_state.selected_job_id = None


@st.cache_data(ttl=60)  # type: ignore
def fetch_jobs(
    tiers: Optional[list[JobTier]],
    sources: Optional[list[str]],
    min_score: int,
    min_salary: int,
    stacks: Optional[list[str]],
    limit: int,
    offset: int,
) -> list[dict[str, Any]]:
    with get_session() as session:
        job_repo = JobRepo(session)
        jobs = job_repo.list_new_matches(
            tiers=tiers,
            sources=sources,
            min_score=min_score,
            min_salary=min_salary,
            stacks=stacks,
            limit=limit,
            offset=offset,
        )
        return [
            {
                "id": j.id,
                "title": j.title,
                "company": j.company,
                "tier": j.tier,
                "fit_score": j.fit_score,
                "source": j.source,
                "scraped_at": j.scraped_at,
                "location_raw": j.location_raw,
                "score_data": j.score_data,
                "url": j.url,
            }
            for j in jobs
        ]


@st.cache_data(ttl=60)  # type: ignore
def get_total_count(
    tiers: Optional[list[JobTier]],
    sources: Optional[list[str]],
    min_score: int,
    min_salary: int,
    stacks: Optional[list[str]],
) -> int:
    with get_session() as session:
        job_repo = JobRepo(session)
        return job_repo.count_new_matches(
            tiers=tiers, sources=sources, min_score=min_score, min_salary=min_salary, stacks=stacks
        )


def handle_skip(job: "Job") -> None:
    with get_session() as session:
        job_repo = JobRepo(session)
        job_repo.mark_status(job.id, JobStatus.ARCHIVED)
        session.commit()
    st.toast(f"Job {job.title} archived.")
    st.cache_data.clear()
    st.rerun()


def open_apply_modal(job: "Job") -> None:
    st.session_state.show_apply_modal = True
    st.session_state.selected_job_id = job.id
    st.rerun()


@st.dialog("Mark as Applied")  # type: ignore
def apply_modal(job_id: uuid.UUID) -> None:
    with get_session() as session:
        job_repo = JobRepo(session)
        job = job_repo.get(job_id)
        if not job:
            st.error("Job not found.")
            if st.button("Close"):
                st.session_state.show_apply_modal = False
                st.rerun()
            return

        st.write(f"Applying for **{job.title}** at **{job.company}**")

        with st.form("apply_form"):
            method = st.selectbox(
                "Method", ["LinkedIn", "Company Website", "Email", "Ottaa", "Other"]
            )
            cv_variant = st.selectbox("CV Variant", ["ai_python", "flutter", "fullstack"])
            notes = st.text_area("Notes")

            submitted = st.form_submit_button("Confirm Application")
            if submitted:
                app_repo = ApplicationRepo(session)
                app_repo.create_for_job(
                    job_id=job.id,
                    application_method=method,
                    cv_variant=cv_variant,
                    notes=notes,
                    status=ApplicationStatus.APPLIED,
                )
                job_repo.mark_status(job.id, JobStatus.APPLIED)
                session.commit()
                st.session_state.show_apply_modal = False
                st.success("Application recorded!")
                st.cache_data.clear()
                time.sleep(1)
                st.rerun()

        if st.button("Cancel"):
            st.session_state.show_apply_modal = False
            st.rerun()


def main() -> None:
    st.header("📥 New Matches")

    # Auto-refresh logic (5 minutes = 300 seconds)
    auto_refresh = st.sidebar.toggle("Auto-refresh (5m)", value=True)
    if auto_refresh and not st.session_state.show_apply_modal:
        # We use a simple script injection for auto-refresh.
        # This will trigger a rerun by setting a dummy query param.
        st.markdown(
            """
            <script>
            if (!window.refreshTimer) {
                window.refreshTimer = setTimeout(function(){
                    const url = new URL(window.location.href);
                    url.searchParams.set('refresh', Date.now());
                    window.parent.history.replaceState({}, '', url);
                    window.parent.postMessage({type: 'streamlit:rerunScript'}, '*');
                    delete window.refreshTimer;
                }, 300000);
            }
            </script>
            """,
            unsafe_allow_html=True,
        )

    with get_session() as session:
        job_repo = JobRepo(session)
        metrics = job_repo.get_dashboard_metrics()

    col1, col2 = st.columns(2)
    col1.metric("New jobs today", metrics["new_today"])
    col2.metric("Pending A-tier matches", metrics["pending_a"])

    # Sidebar Filters
    st.sidebar.divider()
    st.sidebar.subheader("Filters")

    tiers = st.sidebar.multiselect(
        "Tier", options=[JobTier.A, JobTier.B, JobTier.C], default=[JobTier.A, JobTier.B]
    )

    with get_session() as session:
        from jobhunter.db.models import Job

        available_sources = [s[0] for s in session.query(Job.source).distinct().all()]

    sources = st.sidebar.multiselect("Source", options=available_sources)
    min_score = st.sidebar.slider("Min score", 50, 100, 70)
    stacks = st.sidebar.multiselect("Stack", options=["Python", "Flutter", "AI/ML", "Backend"])
    min_salary = st.sidebar.number_input("Min salary USD/month", min_value=0, value=0, step=500)

    # Pagination
    limit = 20
    total_jobs = get_total_count(tiers, sources, min_score, min_salary, stacks)
    total_pages = (total_jobs // limit) + (1 if total_jobs % limit > 0 else 0)

    if total_jobs == 0:
        st.info("No jobs found matching the criteria.")
        return

    page_col1, page_col2 = st.columns([0.2, 0.8])
    page = page_col1.number_input("Page", min_value=1, max_value=max(1, total_pages), value=1)
    page_col2.write(f"Total: {total_jobs} jobs | Page {page} of {total_pages}")

    offset = (page - 1) * limit

    jobs_data = fetch_jobs(tiers, sources, min_score, min_salary, stacks, limit, offset)

    # Render Jobs
    for job_dict in jobs_data:
        from jobhunter.db.models import Job

        job = Job(**job_dict)
        render_job_card(job, on_skip=handle_skip, on_apply=open_apply_modal)

    # Handle modals outside the loop
    if st.session_state.show_apply_modal:
        apply_modal(st.session_state.selected_job_id)
        # Reset state after dialog closes (or when it's open)
        # Note: @st.dialog handles closing, but we might want to reset session state
        # Actually, st.dialog is non-blocking in some ways but it's a modal.


if __name__ == "__main__":
    main()
