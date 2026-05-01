import streamlit as st
from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.db.session import get_session
from jobhunter.config import Settings
from jobhunter.health import get_health_report

st.set_page_config(page_title="System Status", page_icon="🏥", layout="wide")
require_auth()
render_header()
render_sidebar()

st.header("🏥 System Status")

settings = Settings()  # type: ignore[call-arg]

with get_session() as session:
    report = get_health_report(session, settings)

# Overall Status
status_emoji = "✅" if report.status == "healthy" else "⚠️" if report.status == "degraded" else "🚨"
st.subheader(f"Overall Status: {status_emoji} {report.status.upper()}")

# Metrics Cards
m_col1, m_col2, m_col3 = st.columns(3)
m_col1.metric("Last Pipeline Run", report.metrics.last_pipeline_run_at)
m_col2.metric("Monthly LLM Cost", f"${report.metrics.monthly_cost_usd:.2f}")
m_col3.metric("Budget Used", f"{report.metrics.budget_pct_used}%")

# Checks Detail
st.divider()
st.subheader("Subsystem Checks")

for name, check in report.checks.items():
    check_emoji = "✅" if check.status == "ok" else "⚠️" if check.status == "warning" else "❌"
    with st.expander(f"{check_emoji} {name.replace('_', ' ').title()}: {check.status.upper()}"):
        if check.latency_ms:
            st.write(f"**Latency:** {check.latency_ms}ms")
        if check.last_call_at:
            st.write(f"**Last Activity:** {check.last_call_at}")
        if check.message:
            st.write(f"**Message:** {check.message}")

        if name == "db":
            st.info("Includes database connectivity and migration status (alembic).")
        elif name == "anthropic_api":
            st.info("Status based on history of successful LLM calls.")
        elif name == "telegram":
            st.info("Checks configuration and status of last notification attempt.")
        elif name == "gmail":
            st.info("Checks existence and validity of OAuth tokens.")

# Circuit Breakers
st.divider()
st.subheader("Circuit Breakers")
if report.metrics.active_circuit_breakers:
    st.warning(
        f"Active Circuit Breakers (OPEN): {', '.join(report.metrics.active_circuit_breakers)}"
    )
    st.write("These sources are currently paused due to consecutive failures.")
else:
    st.success("All circuit breakers are CLOSED (Normal operation).")

if st.button("Refresh Status"):
    st.rerun()
