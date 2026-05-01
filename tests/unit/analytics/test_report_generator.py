import pytest
from unittest.mock import MagicMock, AsyncMock
from jobhunter.analytics.report_generator import (
    MonthlyMetrics,
    calculate_comparison,
    generate_narrative_report,
    format_report_as_html,
)


@pytest.fixture
def sample_metrics() -> MonthlyMetrics:
    return MonthlyMetrics(
        month="2024-01",
        funnel={"1. Ingested": 100, "4. Applied": 10, "6. Interview": 2},
        tier_distribution={"A": 5, "B": 10},
        false_rejects_count=1,
        total_cost=5.5,
        cost_per_outcome=[],
        outreach_performance={
            "total_sent": 20,
            "total_replied": 2,
            "response_rate": 0.1,
            "template_stats": [],
            "market_stats": [],
            "quality_stats": [],
            "mean_response_time": 0.0,
            "status_counts": {},
        },
        matcher_metrics={
            "total_processed": 10,
            "auto_matched": 5,
            "ai_matched": 2,
            "user_confirmed": 6,
            "user_rejected": 1,
            "precision": 0.9,
            "recall": 0.0,
        },
        prompt_performance=[],
    )


@pytest.fixture
def reference_metrics() -> MonthlyMetrics:
    return MonthlyMetrics(
        month="2023-12",
        funnel={"1. Ingested": 80, "4. Applied": 8, "6. Interview": 1},
        tier_distribution={"A": 4, "B": 8},
        false_rejects_count=0,
        total_cost=4.0,
        cost_per_outcome=[],
        outreach_performance={
            "total_sent": 15,
            "total_replied": 1,
            "response_rate": 0.06,
            "template_stats": [],
            "market_stats": [],
            "quality_stats": [],
            "mean_response_time": 0.0,
            "status_counts": {},
        },
        matcher_metrics={
            "total_processed": 8,
            "auto_matched": 4,
            "ai_matched": 1,
            "user_confirmed": 4,
            "user_rejected": 1,
            "precision": 0.8,
            "recall": 0.0,
        },
        prompt_performance=[],
    )


def test_calculate_comparison(
    sample_metrics: MonthlyMetrics, reference_metrics: MonthlyMetrics
) -> None:
    comp = calculate_comparison(sample_metrics, reference_metrics)

    assert "funnel" in comp
    assert comp["funnel"]["1. Ingested"]["change_pct"] == 25.0
    assert comp["total_cost"]["change_pct"] == 37.5
    assert comp["interview_rate"]["current"] == 20.0  # 2/10 * 100
    assert comp["interview_rate"]["reference"] == 12.5  # 1/8 * 100


@pytest.mark.asyncio
async def test_generate_narrative_report(sample_metrics: MonthlyMetrics) -> None:
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(return_value=MagicMock(text="Mocked Narrative Report"))

    mock_session = MagicMock()
    mock_anomalies = MagicMock()
    mock_anomalies.model_dump.return_value = {}

    report = await generate_narrative_report(
        session=mock_session,
        llm_client=mock_llm,
        month="2024-01",
        current_metrics=sample_metrics,
        prev_month_comp={},
        prev_quarter_comp={},
        anomalies=mock_anomalies,
    )

    assert report == "Mocked Narrative Report"
    mock_llm.complete.assert_called_once()


def test_format_report_as_html() -> None:
    md = "# Title\n\n**Bold Text**"
    html = format_report_as_html(md, "2024-01")

    assert "<h1>Title</h1>" in html or "Title" in html
    assert "<strong>Bold Text</strong>" in html or "Bold Text" in html
    assert "2024-01" in html
