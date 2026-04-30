import streamlit as st
from datetime import datetime, timezone
from typing import Callable
from jobhunter.db.models import Job
from jobhunter.db.enums import JobTier


def format_relative_time(dt: datetime) -> str:
    """
    Returns a human-readable relative time string in Spanish.
    """
    if not dt:
        return ""

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt

    seconds = diff.total_seconds()
    if seconds < 60:
        return "hace unos segundos"

    minutes = seconds // 60
    if minutes < 60:
        return f"hace {int(minutes)}m"

    hours = minutes // 60
    if hours < 24:
        return f"hace {int(hours)}h"

    days = hours // 24
    if days == 1:
        return "ayer"

    return f"hace {int(days)}d"


def render_job_card(
    job: Job, on_skip: Callable[[Job], None], on_apply: Callable[[Job], None]
) -> None:
    """
    Renders a visual card for a job match.
    """
    tier_emoji = {
        JobTier.A: "🔥",
        JobTier.B: "✅",
        JobTier.C: "⚖️",
        JobTier.REJECT: "❌",
    }.get(job.tier if job.tier else JobTier.C, "❓")

    with st.container(border=True):
        col1, col2 = st.columns([0.8, 0.2])

        with col1:
            st.subheader(f"{tier_emoji} {job.title}")
            st.write(f"**{job.company}**")

        with col2:
            st.metric("Fit Score", f"{job.fit_score}%")

        # Salary and metadata
        salary_info = "Salario no especificado"
        if job.score_data and "compensation" in job.score_data:
            comp = job.score_data["compensation"]
            s_min = comp.get("salary_min_usd_month")
            s_max = comp.get("salary_max_usd_month")
            if s_min and s_max:
                salary_info = f"💰 ${s_min:,.0f} - ${s_max:,.0f} / mes"
            elif s_max:
                salary_info = f"💰 hasta ${s_max:,.0f} / mes"

        st.write(salary_info)

        # Match Points
        if job.score_data and "match_analysis" in job.score_data:
            points = job.score_data["match_analysis"].get("key_match_points", [])[:3]
            if points:
                st.write("**Top Match Points:**")
                for p in points:
                    st.write(f"• {p}")

        # Flags
        if job.score_data:
            red_flags = job.score_data.get("red_flags", [])
            yellow_flags = job.score_data.get("yellow_flags", [])

            if red_flags:
                st.warning(f"🚩 **Red Flags:** {', '.join(red_flags)}")
            if yellow_flags:
                st.info(f"⚠️ **Yellow Flags:** {', '.join(yellow_flags)}")

        # Footer
        st.divider()
        f_col1, f_col2 = st.columns([0.5, 0.5])

        with f_col1:
            st.caption(f"Fuente: {job.source} | {format_relative_time(job.scraped_at)}")

        with f_col2:
            btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

            with btn_col1:
                # Green button for assist
                if st.button("🚀 Assist", key=f"assist_{job.id}", type="primary"):
                    st.query_params["job_id"] = str(job.id)
                    # Note: We point to Pipeline page for now as a destination for assist
                    # if a dedicated assistant page doesn't exist yet.
                    # Or we can just show an info message if it's not implemented.
                    st.info("Assist page implementation in progress (E07-S08).")

            with btn_col2:
                if st.button("⏭️ Skip", key=f"skip_{job.id}"):
                    on_skip(job)

            with btn_col3:
                if st.button("📝 Apply", key=f"apply_{job.id}"):
                    on_apply(job)

            with btn_col4:
                st.link_button("🌐 View", job.url)
