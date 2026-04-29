import streamlit as st
from jobhunter.dashboard.auth import logout
from jobhunter.db.session import get_session
from jobhunter.db.models import Job
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.db.enums import JobTier, JobStatus


def render_header() -> None:
    """Renders the dashboard header."""
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.title("🎯 Job Hunter EU")
        st.caption("v0.1.0 - Automated job search system")
    with col2:
        if st.button("Logout"):
            logout()


def render_sidebar() -> None:
    """Renders the dashboard sidebar with system status."""
    st.sidebar.title("System Status")

    try:
        with get_session() as session:
            job_repo = JobRepo(session)
            notify_repo = NotificationsRepo(session)

            # Pending A matches
            pending_a = len(job_repo.list(tier=JobTier.A, status=JobStatus.QUEUED))
            st.sidebar.metric("Pending Tier-A", pending_a)

            # Recent failures (last 24h)
            failures = notify_repo.get_failure_breakdown(hours=24)
            total_failures = sum(failures.values())
            st.sidebar.metric("Recent Failures (24h)", total_failures, delta_color="inverse")

            # Last ingestion
            # We don't have a direct "last ingestion" table easily accessible here without more queries,
            # but we can check the latest scraped_at
            latest_job = session.query(Job).order_by(Job.scraped_at.desc()).first()
            if latest_job:
                st.sidebar.text(
                    f"Last ingestion: {latest_job.scraped_at.strftime('%Y-%m-%d %H:%M')}"
                )

    except Exception as e:
        st.sidebar.error(f"Error loading status: {e}")

    if st.sidebar.button("Refresh Data"):
        st.rerun()
