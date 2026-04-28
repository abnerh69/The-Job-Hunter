import pytest
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from jobhunter.__main__ import app
from jobhunter.sources.orchestrator import IngestionReport, SourceResult
from datetime import datetime, timezone

runner = CliRunner(env={"NO_COLOR": "1"})


@pytest.fixture
def mock_ingestion_report() -> IngestionReport:
    return IngestionReport(
        source_results=[
            SourceResult(
                source_name="ArbeitnowSource",
                status="success",
                new_jobs=5,
                duplicates=2,
                duration_ms=100,
            ),
            SourceResult(
                source_name="RemoteOKSource", status="failed", error="API Error", duration_ms=50
            ),
        ],
        total_new=5,
        total_duplicates=2,
        total_errors=1,
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
    )


def test_ingest_help() -> None:
    result = runner.invoke(app, ["ingest", "--help"])
    assert result.exit_code == 0
    assert "Run job ingestion from configured sources" in result.output
    assert "--source" in result.output
    assert "--since" in result.output
    assert "--limit" in result.output
    assert "--dry-run" in result.output


@patch("jobhunter.__main__.get_all_sources")
@patch("jobhunter.__main__.run_ingestion")
@patch("jobhunter.__main__.get_session")
def test_ingest_dry_run(
    mock_get_session: MagicMock,
    mock_run_ingestion: MagicMock,
    mock_get_all_sources: MagicMock,
    mock_ingestion_report: IngestionReport,
) -> None:
    class MockSource:
        pass

    MockSource.__name__ = "MockSource"
    mock_get_all_sources.return_value = [MockSource]
    mock_run_ingestion.return_value = mock_ingestion_report

    # We use a successful report for this test to check exit code
    mock_ingestion_report.total_errors = 0
    mock_ingestion_report.source_results[1].status = "success"

    result = runner.invoke(app, ["ingest", "--dry-run", "--limit", "10"])

    assert result.exit_code == 0
    assert "Ingestion Report (DRY RUN)" in result.output
    assert "ArbeitnowSource" in result.output
    mock_run_ingestion.assert_called_once()
    args, kwargs = mock_run_ingestion.call_args
    assert kwargs["dry_run"] is True
    assert kwargs["limit"] == 10


@patch("jobhunter.__main__.get_all_sources")
@patch("jobhunter.__main__.run_ingestion")
@patch("jobhunter.__main__.get_session")
def test_ingest_error_exit_code(
    mock_get_session: MagicMock,
    mock_run_ingestion: MagicMock,
    mock_get_all_sources: MagicMock,
    mock_ingestion_report: IngestionReport,
) -> None:
    class MockSource:
        pass

    MockSource.__name__ = "MockSource"
    mock_get_all_sources.return_value = [MockSource]
    mock_run_ingestion.return_value = mock_ingestion_report

    result = runner.invoke(app, ["ingest"])

    assert result.exit_code == 1
    assert "failed" in result.output


def test_sources_list_help() -> None:
    result = runner.invoke(app, ["sources", "list", "--help"])
    assert result.exit_code == 0
    assert "List all registered job sources" in result.output


@patch("jobhunter.__main__.SourceHealthRepo")
@patch("jobhunter.__main__.get_session")
@patch("jobhunter.__main__.get_all_sources")
def test_sources_list(
    mock_get_all_sources: MagicMock, mock_get_session: MagicMock, mock_repo_cls: MagicMock
) -> None:
    class MockSource:
        pass

    MockSource.__name__ = "MockSource"
    mock_get_all_sources.return_value = [MockSource]

    mock_repo = MagicMock()
    mock_repo_cls.return_value = mock_repo

    mock_health = MagicMock()
    mock_health.state = "OPEN"
    mock_health.last_failure_at = datetime(2023, 1, 1, tzinfo=timezone.utc)
    mock_health.opened_until = datetime(2023, 1, 2, tzinfo=timezone.utc)
    mock_repo.get_by_source.return_value = mock_health

    result = runner.invoke(app, ["sources", "list"])

    assert result.exit_code == 0
    assert "Job Sources Health" in result.output
    assert "MockSource" in result.output
    assert "OPEN" in result.output
    assert "2023-01-01" in result.output
