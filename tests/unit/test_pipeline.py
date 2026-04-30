"""
Unit tests for the pipeline orchestrator.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from jobhunter.notify.dispatcher import DispatchReport
from jobhunter.pipeline import RunCycleStatus, run_cycle
from jobhunter.scoring.pipeline import ScoringBatchReport
from jobhunter.sources.orchestrator import IngestionReport


@pytest.fixture
def mock_session() -> MagicMock:
    """Fixture for a mock SQLAlchemy session."""
    return MagicMock(spec=Session)


@pytest.mark.asyncio
async def test_run_cycle_success(mock_session: MagicMock) -> None:
    """Test a successful full pipeline cycle."""
    mock_ingestion = IngestionReport(
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        total_new=10,
        total_duplicates=5,
        total_errors=0,
    )
    mock_scoring = ScoringBatchReport(
        total_processed=10,
        success_count=10,
        failed_count=0,
        total_cost_usd=0.05,
    )
    mock_dispatch = DispatchReport(
        total_pending=2,
        success_count=2,
        failure_count=0,
        duration_ms=100,
    )

    with (
        patch("jobhunter.pipeline.run_ingestion", new_callable=AsyncMock) as mock_ing,
        patch("jobhunter.pipeline.score_pending_jobs", new_callable=AsyncMock) as mock_score,
        patch(
            "jobhunter.pipeline.dispatch_tier_a_notifications", new_callable=AsyncMock
        ) as mock_disp,
        patch("jobhunter.pipeline.get_all_sources", return_value=[]),
    ):
        mock_ing.return_value = mock_ingestion
        mock_score.return_value = mock_scoring
        mock_disp.return_value = mock_dispatch

        report = await run_cycle(mock_session)

        assert report.overall_status == RunCycleStatus.SUCCESS
        assert report.ingestion == mock_ingestion
        assert report.scoring == mock_scoring
        assert report.dispatch == mock_dispatch
        assert len(report.errors) == 0
        assert report.total_duration_ms > 0


@pytest.mark.asyncio
async def test_run_cycle_partial_failure_ingestion(mock_session: MagicMock) -> None:
    """Test partial failure when ingestion has errors."""
    mock_ingestion = IngestionReport(
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        total_new=5,
        total_errors=1,
    )

    with (
        patch("jobhunter.pipeline.run_ingestion", new_callable=AsyncMock) as mock_ing,
        patch("jobhunter.pipeline.score_pending_jobs", new_callable=AsyncMock),
        patch("jobhunter.pipeline.dispatch_tier_a_notifications", new_callable=AsyncMock),
        patch("jobhunter.pipeline.get_all_sources", return_value=[]),
    ):
        mock_ing.return_value = mock_ingestion
        # Other mocks return default Success objects if not specified,
        # but let's just check ingestion impact.

        report = await run_cycle(mock_session)

        assert report.overall_status == RunCycleStatus.PARTIAL_FAILURE
        assert "Ingestion had 1 errors" in report.errors


@pytest.mark.asyncio
async def test_run_cycle_total_failure_db(mock_session: MagicMock) -> None:
    """Test total failure when a DB error occurs."""

    class SQLAlchemyError(Exception):
        pass

    with (
        patch("jobhunter.pipeline.run_ingestion", side_effect=SQLAlchemyError("SQLAlchemy Error")),
        patch("jobhunter.pipeline.get_all_sources", return_value=[lambda: MagicMock()]),
    ):
        report = await run_cycle(mock_session)

        assert report.overall_status == RunCycleStatus.TOTAL_FAILURE
        assert "Ingestion failed: SQLAlchemy Error" in report.errors
        # Ensure it stopped early
        assert report.scoring is None
        assert report.dispatch is None


@pytest.mark.asyncio
async def test_run_cycle_skip_steps(mock_session: MagicMock) -> None:
    """Test skipping steps."""
    mock_scoring = ScoringBatchReport(
        total_processed=10,
        success_count=10,
        failed_count=0,
        total_cost_usd=0.05,
    )

    with (
        patch("jobhunter.pipeline.run_ingestion", new_callable=AsyncMock) as mock_ing,
        patch("jobhunter.pipeline.score_pending_jobs", new_callable=AsyncMock) as mock_score,
        patch(
            "jobhunter.pipeline.dispatch_tier_a_notifications", new_callable=AsyncMock
        ) as mock_disp,
    ):
        mock_score.return_value = mock_scoring
        report = await run_cycle(mock_session, skip_steps=["ingest", "notify"])

        assert report.overall_status == RunCycleStatus.SUCCESS
        mock_ing.assert_not_called()
        mock_disp.assert_not_called()
        mock_score.assert_called_once()
        assert report.ingestion is None
        assert report.dispatch is None
        assert report.scoring is not None


@pytest.mark.asyncio
async def test_run_cycle_partial_failure_exception_non_db(mock_session: MagicMock) -> None:
    """Test partial failure when a step raises a non-DB exception."""
    mock_scoring = ScoringBatchReport(
        total_processed=5,
        success_count=5,
        failed_count=0,
    )

    with (
        patch("jobhunter.pipeline.run_ingestion", side_effect=Exception("Network Error")),
        patch("jobhunter.pipeline.score_pending_jobs", return_value=mock_scoring),
        patch("jobhunter.pipeline.dispatch_tier_a_notifications", new_callable=AsyncMock),
        patch("jobhunter.pipeline.get_all_sources", return_value=[MagicMock]),
    ):
        report = await run_cycle(mock_session)

        assert report.overall_status == RunCycleStatus.PARTIAL_FAILURE
        assert "Ingestion failed: Network Error" in report.errors
        # Scoring should still have run
        assert report.scoring == mock_scoring
