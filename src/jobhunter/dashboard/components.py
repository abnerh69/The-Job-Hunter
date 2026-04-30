import streamlit as st
from typing import Any, Callable
from datetime import datetime, timezone
from jobhunter.db.models import Job
from jobhunter.db.enums import JobTier


def render_job_card(
    job: Job, on_skip: Callable[[Job], Any], on_apply: Callable[[Job], Any]
) -> None:
    """
    Renders a visual card for a job.
    """
    tier_emoji = {
        JobTier.A: "🔥",
        JobTier.B: "⭐",
        JobTier.C: "🔍",
        JobTier.REJECT: "❌",
    }.get(job.tier, "❓")

    with st.container(border=True):
        col_header, col_score = st.columns([0.8, 0.2])
        with col_header:
            st.subheader(f"{tier_emoji} {job.title}")
            st.text(f"{job.company} | {job.location_raw or 'Remote'}")
        with col_score:
            st.metric("Score", f"{job.fit_score}/100")

        # Salary and source info
        score_data = job.score_data or {}
        comp = score_data.get("compensation", {})
        salary_min = comp.get("salary_min_usd_month")
        salary_max = comp.get("salary_max_usd_month")

        salary_text = "Salary: Not specified"
        if salary_min and salary_max:
            salary_text = f"Salary: ${salary_min:,.0f} - ${salary_max:,.0f} / month"
        elif salary_min:
            salary_text = f"Salary: From ${salary_min:,.0f} / month"

        st.caption(
            f"{salary_text} | Source: {job.source} | Scraped: {format_relative_time(job.scraped_at)}"
        )

        # Match Points
        match_analysis = score_data.get("match_analysis", {})
        match_points = match_analysis.get("key_match_points", [])[:3]
        if match_points:
            st.write("**Top Match Points:**")
            for point in match_points:
                st.markdown(f"- {point}")

        # Flags
        red_flags = score_data.get("red_flags", [])
        yellow_flags = score_data.get("yellow_flags", [])

        if red_flags or yellow_flags:
            cols = st.columns(2)
            with cols[0]:
                if red_flags:
                    st.error("🚩 " + ", ".join(red_flags))
            with cols[1]:
                if yellow_flags:
                    st.warning("⚠️ " + ", ".join(yellow_flags))

        # Action buttons
        st.divider()
        btn_cols = st.columns([1, 1, 1, 1])
        with btn_cols[0]:
            st.link_button(
                "🚀 Assist",
                f"/Manual_Review?job_id={job.id}",
                use_container_width=True,
                type="primary",
            )
        with btn_cols[1]:
            if st.button("✅ Applied", key=f"apply_{job.id}", use_container_width=True):
                on_apply(job)
        with btn_cols[2]:
            # Skip with confirmation via popover if available, else session state
            with st.popover("🗑️ Skip", use_container_width=True):
                st.write("Are you sure you want to archive this job?")
                if st.button(
                    "Confirm Skip", key=f"confirm_skip_{job.id}", use_container_width=True
                ):
                    on_skip(job)
        with btn_cols[3]:
            st.link_button("🔗 View JD", job.url, use_container_width=True)


def format_relative_time(dt: datetime) -> str:
    """Formats a datetime as a relative string (e.g., 'hace 2h')."""
    if not dt:
        return "unknown"

    now = datetime.now(timezone.utc)
    # Ensure dt is timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    diff = now - dt

    if diff.days > 0:
        return f"hace {diff.days}d"
    hours = diff.seconds // 3600
    if hours > 0:
        return f"hace {hours}h"
    minutes = (diff.seconds // 60) % 60
    return f"hace {minutes}m"
