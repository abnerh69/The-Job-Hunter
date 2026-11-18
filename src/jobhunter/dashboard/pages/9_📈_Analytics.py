import streamlit as st
import hashlib
from datetime import datetime, timedelta, timezone
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.db.session import get_session
from jobhunter.analytics.ab_testing import get_ab_test_results
from jobhunter.analytics.recommendations import get_recommendations, Recommendation
from jobhunter.db.models import RecommendationState, ABTest, Job
from jobhunter.db.enums import RecommendationStatus, ABTestStatus, JobTier, JobStatus
from sqlalchemy import select, and_
from typing import List, Any
import time
from pathlib import Path

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("📈 Advanced Analytics")


# --- Global Actions ---
def handle_generate_report() -> None:
    from jobhunter.analytics.report_generator import (
        get_month_range,
        collect_metrics_for_period,
        calculate_comparison,
        generate_narrative_report,
        format_report_as_html,
        convert_html_to_pdf,
    )
    from jobhunter.analytics.regression_detector import check_metrics
    from jobhunter.llm.factory import create_llm_client
    from jobhunter.config import Settings
    import asyncio

    with st.spinner("Generating narrative report... This may take up to 60s."):
        try:
            now = datetime.now(timezone.utc)
            first_of_this_month = now.replace(day=1)
            report_month_date = (first_of_this_month - timedelta(days=1)).replace(day=1).date()
            month_label = report_month_date.strftime("%Y-%m")

            with get_session() as session:
                start_date, end_date = get_month_range(
                    report_month_date.year, report_month_date.month
                )
                current_metrics = collect_metrics_for_period(
                    session, start_date, end_date, month_label
                )

                prev_month_date = (report_month_date - timedelta(days=1)).replace(day=1)
                p_start, p_end = get_month_range(prev_month_date.year, prev_month_date.month)
                prev_metrics = collect_metrics_for_period(session, p_start, p_end, "Prev Month")

                q_start = (report_month_date - timedelta(days=90)).replace(day=1)
                q_end = report_month_date - timedelta(days=1)
                prev_quarter_metrics = collect_metrics_for_period(
                    session, q_start, q_end, "Prev Quarter"
                )

                prev_month_comp = calculate_comparison(current_metrics, prev_metrics)
                prev_quarter_comp = calculate_comparison(current_metrics, prev_quarter_metrics)
                anomalies = check_metrics(session)

                settings = Settings()  # type: ignore
                llm_client = create_llm_client(settings)

                report_md = asyncio.run(
                    generate_narrative_report(
                        session,
                        llm_client,
                        month_label,
                        current_metrics,
                        prev_month_comp,
                        prev_quarter_comp,
                        anomalies,
                    )
                )

                reports_dir = Path("reports")
                reports_dir.mkdir(exist_ok=True)

                base_filename = f"{month_label}-monthly"
                (reports_dir / f"{base_filename}.md").write_text(report_md)

                html_report = format_report_as_html(report_md, month_label)
                convert_html_to_pdf(html_report, str(reports_dir / f"{base_filename}.pdf"))

                st.success(f"Report for {month_label} generated successfully!")
                st.cache_data.clear()
        except Exception as e:
            st.error(f"Failed to generate report: {e}")


col_h1, col_h2 = st.columns([4, 1])
with col_h2:
    if st.button("✨ Generate Monthly Report"):
        handle_generate_report()


def get_reco_hash(reco: Recommendation) -> str:
    """Generates a stable hash for a recommendation."""
    content = f"{reco.action}:{reco.reason}:{reco.impact}"
    return hashlib.sha256(content.encode()).hexdigest()


def update_reco_state(reco_hash: str, status: RecommendationStatus, snooze_days: int = 0) -> None:
    with get_session() as session:
        state = session.get(RecommendationState, reco_hash)
        if not state:
            state = RecommendationState(reco_hash=reco_hash)
            session.add(state)

        state.status = status
        if status == RecommendationStatus.SNOOZED:
            state.snoozed_until = datetime.now(timezone.utc) + timedelta(days=snooze_days)
        else:
            state.snoozed_until = None

        session.commit()
    st.cache_data.clear()


def render_recommendation_card(reco: Recommendation) -> None:
    reco_hash = get_reco_hash(reco)

    # Priority colors
    p_colors = {"P1": "red", "P2": "orange", "P3": "gray"}
    p_color = p_colors.get(reco.priority, "gray")

    with st.container(border=True):
        col1, col2 = st.columns([4, 1])
        with col1:
            st.markdown(f"**{reco.action}**")
            st.caption(f"Reason: {reco.reason}")
            st.caption(f"Impact: {reco.impact} | Effort: {reco.effort}")
        with col2:
            st.markdown(f":{p_color}[{reco.priority}]")

        b_col1, b_col2, b_col3 = st.columns(3)
        if b_col1.button("Snooze (7d)", key=f"snooze_{reco_hash}"):
            update_reco_state(reco_hash, RecommendationStatus.SNOOZED, snooze_days=7)
            st.toast("Snoozed for 7 days")
            time.sleep(0.5)
            st.rerun()
        if b_col2.button("Acted on", key=f"acted_{reco_hash}"):
            update_reco_state(reco_hash, RecommendationStatus.ACTED)
            st.toast("Marked as acted on")
            time.sleep(0.5)
            st.rerun()
        if b_col3.button("Ignore", key=f"ignore_{reco_hash}"):
            update_reco_state(reco_hash, RecommendationStatus.IGNORED)
            st.toast("Recommendation ignored")
            time.sleep(0.5)
            st.rerun()


# --- Section 1: Recommendations ---
col_r1, col_r2 = st.columns([4, 1])
with col_r1:
    st.subheader("💡 Actionable Recommendations")


def handle_export_recommendations_pdf(recs: List[Recommendation]) -> None:
    from jobhunter.analytics.report_generator import convert_html_to_pdf
    import jinja2

    html_template = """
    <html>
    <body>
        <h1>Actionable Recommendations</h1>
        <ul>
        {% for r in recs %}
            <li>
                <strong>{{ r.action }}</strong><br/>
                Reason: {{ r.reason }}<br/>
                Impact: {{ r.impact }} | Effort: {{ r.effort }} | Priority: {{ r.priority }}
            </li>
        {% endfor %}
        </ul>
    </body>
    </html>
    """
    template = jinja2.Template(html_template)
    html_content = template.render(recs=recs)

    output_path = "reports/recommendations_export.pdf"
    convert_html_to_pdf(html_content, output_path)

    with open(output_path, "rb") as f:
        st.download_button(
            "⬇️ Download PDF Export",
            data=f,
            file_name="recommendations_export.pdf",
            mime="application/pdf",
        )


with col_r2:
    if st.button("📄 Export to PDF"):
        # We need the current recs
        # Note: this button will show the download button after click
        st.session_state.show_reco_export = True


@st.cache_data(ttl=600)
def fetch_filtered_recommendations() -> List[Recommendation]:
    with get_session() as session:
        all_recs = get_recommendations(session)

        # Filter by state in DB
        now = datetime.now(timezone.utc)
        stmt = select(RecommendationState)
        states = {s.reco_hash: s for s in session.scalars(stmt).all()}

        filtered = []
        for r in all_recs:
            h = get_reco_hash(r)
            state = states.get(h)
            if not state:
                filtered.append(r)
                continue

            if state.status in (RecommendationStatus.ACTED, RecommendationStatus.IGNORED):
                continue

            if (
                state.status == RecommendationStatus.SNOOZED
                and state.snoozed_until
                and state.snoozed_until > now
            ):
                continue

            filtered.append(r)

        return filtered


recs = fetch_filtered_recommendations()

if st.session_state.get("show_reco_export"):
    handle_export_recommendations_pdf(recs)
    if st.button("Close Export"):
        st.session_state.show_reco_export = False
        st.rerun()

if not recs:
    st.info("No active recommendations. Good job!")
else:
    for r in recs:
        render_recommendation_card(r)

# --- Section 2: A/B Tests ---
st.divider()
st.subheader("🧪 Active A/B Tests")

with get_session() as session:
    active_tests = session.scalars(select(ABTest).where(ABTest.status == ABTestStatus.ACTIVE)).all()

if not active_tests:
    st.info("No active A/B tests.")
else:
    for test in active_tests:
        try:
            results = get_ab_test_results(session, test.name)
            with st.expander(f"Test: {test.name} ({test.metric_target})"):
                st.write(test.description or "No description.")
                st.write(f"Started at: {test.started_at}")

                # Table
                cols = st.columns(len(results.variants))
                for i, v in enumerate(results.variants):
                    with cols[i]:
                        st.metric(f"Variant: {v.variant}", f"{v.conversion_rate:.2%}")
                        st.caption(f"Sample: {v.sample_size} | Conv: {v.conversions}")

                st.write(f"P-value: {results.p_value:.4f}")
                if results.statistical_significance:
                    st.success("Statistically Significant! 🎉")

                if st.button("End Test", key=f"end_test_{test.name}"):
                    # In a real scenario we'd need a winner and notes, but let's implement basic end
                    test.status = ABTestStatus.CONCLUDED
                    test.ended_at = datetime.now(timezone.utc)
                    session.commit()
                    st.success(f"Test {test.name} concluded.")
                    time.sleep(0.5)
                    st.rerun()
        except Exception as e:
            st.error(f"Error loading results for {test.name}: {e}")

# --- Section 3: False Rejects Review ---
st.divider()
st.subheader("🔍 False Rejects Review")


@st.cache_data(ttl=300)
def fetch_false_rejects() -> List[Job]:
    with get_session() as session:
        # Jobs with tier REJECT that were manually promoted
        stmt = (
            select(Job)
            .where(and_(Job.tier == JobTier.REJECT, Job.manually_promoted_at.is_not(None)))
            .order_by(Job.manually_promoted_at.desc())
            .limit(20)
        )
        return list(session.scalars(stmt).all())


false_rejects = fetch_false_rejects()


def handle_promote_again(job_id: Any) -> None:
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.status = JobStatus.QUEUED
            session.commit()
    st.cache_data.clear()
    st.success("Promoted to QUEUED")
    time.sleep(0.5)
    st.rerun()


if not false_rejects:
    st.info("No false rejects found (manually promoted jobs with REJECT tier).")
else:
    for fr in false_rejects:
        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{fr.company} - {fr.title}**")
                st.caption(f"Promoted at: {fr.manually_promoted_at}")
                if fr.manually_promoted_reason:
                    st.caption(f"Reason: {fr.manually_promoted_reason}")
            with col2:
                if fr.status != JobStatus.QUEUED:
                    if st.button("Promote to QUEUED", key=f"prom_{fr.id}"):
                        handle_promote_again(fr.id)
                else:
                    st.write("Status: QUEUED")

# --- Section 4: Reports Archive ---
st.divider()
st.subheader("📁 Reports Archive")

reports_dir = Path("reports")
if not reports_dir.exists():
    reports_dir.mkdir()

report_files = sorted(
    list(reports_dir.glob("*.pdf")) + list(reports_dir.glob("*.md")),
    key=lambda x: x.name,
    reverse=True,
)

if not report_files:
    st.info("No reports found in reports/ directory.")
else:
    # Group by base name
    reports_by_name: dict[str, List[Path]] = {}
    for f in report_files:
        base = f.stem.replace(".md", "").replace(".pdf", "")
        if base not in reports_by_name:
            reports_by_name[base] = []
        reports_by_name[base].append(f)

    for base, files in reports_by_name.items():
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"**Report: {base}**")
                # Preview first paragraph if md exists
                md_file = next((f for f in files if f.suffix == ".md"), None)
                if md_file:
                    content = md_file.read_text()
                    first_para = content.split("\n\n")[0] if "\n\n" in content else content[:200]
                    st.caption(first_para[:300] + "...")

            with col2:
                for f in files:
                    with open(f, "rb") as file_bytes:
                        st.download_button(
                            label=f"Download {f.suffix[1:].upper()}",
                            data=file_bytes,
                            file_name=f.name,
                            mime="application/pdf" if f.suffix == ".pdf" else "text/markdown",
                            key=f"dl_{f.name}",
                        )
