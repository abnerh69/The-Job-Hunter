import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from jobhunter.sources.orchestrator import run_ingestion, SourceResult
from jobhunter.sources.base import BaseSource, RawJob


class MockSource(BaseSource):
    async def fetch(self, since: datetime):
        yield RawJob(
            source_name=self.__class__.__name__,
            source_id="1",
            url="http://example.com/1",
            title="Job 1",
            company="Company 1",
            description="Desc 1",
        )


@pytest.mark.asyncio
async def test_run_ingestion_parallel_success():
    source_ok = MockSource()
    source_fail = MockSource()
    source_fail.__class__ = type("FailingSource", (MockSource,), {})
    # Mock fetch to fail for source_fail
    async def failing_fetch(since):
        raise ValueError("Failed")
        yield  # make it a generator
    source_fail.fetch = failing_fetch

    sources = [source_ok, source_fail]
    since = datetime.now(timezone.utc)
    mock_session = MagicMock()

    with patch("jobhunter.sources.orchestrator.JobRepo") as MockJobRepo, \
         patch("jobhunter.sources.orchestrator.SourceHealthRepo"), \
         patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockCB:

        # Setup JobRepo mock
        job_repo_instance = MockJobRepo.return_value
        job_repo_instance.bulk_create_skipping_duplicates.return_value = [1]

        # Setup CircuitBreaker mock
        cb_instance = MockCB.return_value
        cb_instance.allow_request.return_value = True

        report = await run_ingestion(sources, since, mock_session)

        assert len(report.source_results) == 2

        results_map = {r.source_name: r for r in report.source_results}
        assert results_map["MockSource"].status == "success"
        assert results_map["MockSource"].new_jobs == 1

        assert results_map["FailingSource"].status == "failed"
        # Wait, if they have same class name, the results might overwrite or be duplicated in list
        # In my implementation they are appended to list.

@pytest.mark.asyncio
async def test_run_ingestion_with_breaker():
    source_ok = MockSource()
    source_skipped = MockSource()
    source_skipped.__class__ = type("SkippedSource", (MockSource,), {})

    sources = [source_ok, source_skipped]
    since = datetime.now(timezone.utc)
    mock_session = MagicMock()

    with patch("jobhunter.sources.orchestrator.JobRepo") as MockJobRepo, \
         patch("jobhunter.sources.orchestrator.SourceHealthRepo"), \
         patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockCB:

        job_repo_instance = MockJobRepo.return_value
        job_repo_instance.bulk_create_skipping_duplicates.return_value = [1]

        cb_instance = MockCB.return_value
        # Allow first, skip second
        cb_instance.allow_request.side_effect = [True, False]

        report = await run_ingestion(sources, since, mock_session)

        assert len(report.source_results) == 2
        status_counts = {"success": 0, "skipped_breaker": 0}
        for r in report.source_results:
            status_counts[r.status] += 1

        assert status_counts["success"] == 1
        assert status_counts["skipped_breaker"] == 1
        assert report.total_new == 1
