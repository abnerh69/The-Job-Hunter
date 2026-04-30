from datetime import date, timedelta
from typing import Any

import pandas as pd
import plotly.express as px  # type: ignore
import streamlit as st

from jobhunter.dashboard.auth import require_auth
from jobhunter.dashboard.layout import render_header, render_sidebar
from jobhunter.dashboard.services.metrics import get_metrics_service
from jobhunter.db.session import get_session

# Page config
st.set_page_config(page_title="Metrics & Analytics", page_icon="📊", layout="wide")

# Auth & Layout
require_auth()
render_header()
render_sidebar()


def main() -> None:
    st.header("📊 Metrics & Insights")
    st.write("System performance and recruitment funnel analytics.")

    # Global Filters & Actions in Sidebar
    st.sidebar.divider()
    st.sidebar.subheader("📅 Global Filter")
    today = date.today()
    default_start = today - timedelta(days=28)

    date_range = st.sidebar.date_input(
        "Date Range",
        value=(default_start, today),
        max_value=today,
    )

    # Handle single date selection or range
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = date_range if isinstance(date_range, date) else default_start
        end_date = today

    st.sidebar.divider()
    st.sidebar.subheader("📤 Actions")
    if st.sidebar.button("Export to PDF (Coming Soon)", disabled=True):
        pass

    # Tabs for different sections
    tab_funnel, tab_sources, tab_trends, tab_costs, tab_health = st.tabs(
        [
            "🎯 Funnel",
            "🔌 Sources",
            "📈 Trends",
            "💰 LLM Costs",
            "🩺 System Health",
        ]
    )

    with tab_funnel:
        render_funnel_section(start_date, end_date)

    with tab_sources:
        render_sources_section(start_date, end_date)

    with tab_trends:
        render_trends_section()

    with tab_costs:
        render_costs_section(start_date, end_date)

    with tab_health:
        render_health_section()


@st.cache_data(ttl=300)
def get_cached_funnel_metrics(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_funnel_metrics(start_date, end_date)


@st.cache_data(ttl=300)
def get_cached_tier_distribution(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_tier_distribution(start_date, end_date)


def render_funnel_section(start_date: date, end_date: date) -> None:
    st.subheader("Recruitment Funnel")
    col1, col2 = st.columns([2, 1])

    data = get_cached_funnel_metrics(start_date, end_date)
    df = pd.DataFrame(data)

    with col1:
        if not df.empty and df["count"].sum() > 0:
            fig = px.funnel(df, x="count", y="stage", color_discrete_sequence=["#00CC96"])
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No data available for the selected period.")

    with col2:
        st.write("### Conversion Rates")
        for i in range(len(data) - 1):
            current = data[i]
            next_stage = data[i + 1]
            rate = (next_stage["count"] / current["count"] * 100) if current["count"] > 0 else 0
            st.metric(
                label=f"{current['stage']} → {next_stage['stage']}",
                value=f"{rate:.1f}%",
                delta=f"{next_stage['count']} total",
            )

    # Tier Distribution
    st.divider()
    st.subheader("Job Tier Distribution")
    tier_data = get_cached_tier_distribution(start_date, end_date)
    if tier_data:
        df_tier = pd.DataFrame(tier_data)
        fig_tier = px.pie(df_tier, values="count", names="tier", hole=0.4)
        st.plotly_chart(fig_tier, use_container_width=True)
    else:
        st.write("No tier data for this period.")


@st.cache_data(ttl=300)
def get_cached_source_metrics(start_date: date, end_date: date) -> list[dict[str, Any]]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_source_metrics(start_date, end_date)


def render_sources_section(start_date: date, end_date: date) -> None:
    st.subheader("Performance by Source")
    source_data = get_cached_source_metrics(start_date, end_date)

    if source_data:
        df = pd.DataFrame(source_data)
        # Format percentages
        df["tier_a_pct"] = df["tier_a_pct"].map("{:.1f}%".format)
        df["response_rate"] = df["response_rate"].map("{:.1f}%".format)

        st.dataframe(
            df.rename(
                columns={
                    "source": "Source",
                    "ingested": "Ingested",
                    "tier_a_pct": "% Tier A",
                    "applied": "Applied",
                    "response_rate": "Response Rate",
                }
            ),
            use_container_width=True,
            hide_index=True,
        )

        # Visualize Ingested vs Applied
        fig = px.bar(
            df,
            x="source",
            y=["ingested", "applied"],
            barmode="group",
            title="Ingestion vs Applications by Source",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No source data found.")


@st.cache_data(ttl=300)
def get_cached_temporal_trends(weeks: int = 8) -> list[dict[str, Any]]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_temporal_trends(weeks=weeks)


def render_trends_section() -> None:
    st.subheader("Weekly Trends (Last 8 Weeks)")
    trends = get_cached_temporal_trends(weeks=8)

    if trends:
        df = pd.DataFrame(trends)
        df["week"] = pd.to_datetime(df["week"])

        # Apps Sent line chart
        fig_apps = px.line(df, x="week", y="apps_sent", markers=True, title="Applications per Week")
        st.plotly_chart(fig_apps, use_container_width=True)

        # Response Rate line chart
        fig_rate = px.line(df, x="week", y="response_rate", markers=True, title="Response Rate (%)")
        st.plotly_chart(fig_rate, use_container_width=True)
    else:
        st.info("Insufficient data for trends.")


@st.cache_data(ttl=300)
def get_cached_llm_cost_metrics(start_date: date, end_date: date) -> dict[str, Any]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_llm_cost_metrics(start_date, end_date)


def render_costs_section(start_date: date, end_date: date) -> None:
    st.subheader("LLM Usage & Costs")
    cost_metrics = get_cached_llm_cost_metrics(start_date, end_date)

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Cost", f"${cost_metrics['total_cost_usd']:.2f}")

    # Purpose breakdown
    st.write("### Breakdown by Purpose")
    if cost_metrics["purpose_breakdown"]:
        df_pb = pd.DataFrame(
            [{"purpose": k, "cost": v} for k, v in cost_metrics["purpose_breakdown"].items()]
        )
        fig_pb = px.pie(df_pb, values="cost", names="purpose", hole=0.4)
        st.plotly_chart(fig_pb, use_container_width=True)
    else:
        st.write("No cost data for this period.")

    # Daily trend
    if cost_metrics["daily_trend"]:
        st.write("### Daily Cost Trend")
        df_dt = pd.DataFrame(cost_metrics["daily_trend"])
        fig_dt = px.area(df_dt, x="day", y="cost", title="Daily LLM Cost (USD)")
        st.plotly_chart(fig_dt, use_container_width=True)


@st.cache_data(ttl=60)
def get_cached_system_health() -> list[dict[str, Any]]:
    with get_session() as session:
        service = get_metrics_service(session)
        return service.get_system_health()


def render_health_section() -> None:
    st.subheader("System & Source Health")
    health_data = get_cached_system_health()

    if health_data:
        for item in health_data:
            with st.expander(f"{item['source'].upper()} - {item['state']}", expanded=True):
                col1, col2, col3 = st.columns(3)

                # State with color
                state = item["state"]
                color = "green" if state == "closed" else "red" if state == "open" else "orange"
                col1.markdown(f"**Status:** :{color}[{state.upper()}]")

                col2.metric("Failures", item["failures"])

                if item["last_ingest"]:
                    last_ingest_str = item["last_ingest"].strftime("%Y-%m-%d %H:%M")
                else:
                    last_ingest_str = "Never"
                col3.write(f"**Last Ingest:** {last_ingest_str}")

                if item["last_failure"]:
                    st.write(
                        f"**Last Failure:** {item['last_failure'].strftime('%Y-%m-%d %H:%M:%S')}"
                    )
    else:
        st.info("No source health data available.")


if __name__ == "__main__":
    main()
