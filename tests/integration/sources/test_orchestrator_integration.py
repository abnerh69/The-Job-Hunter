import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from jobhunter.sources.orchestrator import run_ingestion
from jobhunter.sources.fourdayweek import FourDayWeekSource
from jobhunter.sources.remoteok import RemoteOKSource
from jobhunter.sources.wwr import WeWorkRemotelySource
from jobhunter.sources.arbeitnow import ArbeitnowSource
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_orchestrator_full_ingestion_integration() -> None:
    """
    Integration test for IngestionOrchestrator with all 4 sources using cassettes.
    """
    # Use MagicMock for session and repositories to avoid DB issues in this environment
    mock_session = MagicMock()

    # Mock JobRepo.bulk_create_skipping_duplicates to return some IDs
    with (
        patch("jobhunter.sources.orchestrator.JobRepo") as MockJobRepo,
        patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockBreaker,
    ):
        job_repo_instance = MockJobRepo.return_value
        job_repo_instance.bulk_create_skipping_duplicates.return_value = ["uuid1", "uuid2"]

        breaker_instance = MockBreaker.return_value
        breaker_instance.allow_request.return_value = True

        async with SourceHttpClient() as http_client:
            sources = [
                FourDayWeekSource(http_client=http_client, limit=2),
                RemoteOKSource(http_client=http_client),
                WeWorkRemotelySource(
                    http_client=http_client, categories=["remote-programming-jobs"]
                ),
                ArbeitnowSource(http_client=http_client),
            ]

            since = datetime(2024, 1, 1, tzinfo=timezone.utc)

            # Run ingestion
            report = await run_ingestion(
                sources=sources, since=since, session=mock_session, limit=2
            )

            assert report.total_new > 0
            assert len(report.source_results) == 4
            for res in report.source_results:
                assert res.status == "success"

            # Verify bulk_create called for each source
            assert job_repo_instance.bulk_create_skipping_duplicates.call_count == 4


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_orchestrator_deduplication_integration() -> None:
    """
    Tests that running ingestion twice doesn't create duplicate jobs.
    """
    mock_session = MagicMock()

    with (
        patch("jobhunter.sources.orchestrator.JobRepo") as MockJobRepo,
        patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockBreaker,
    ):
        job_repo_instance = MockJobRepo.return_value
        breaker_instance = MockBreaker.return_value
        breaker_instance.allow_request.return_value = True

        async with SourceHttpClient() as http_client:
            sources = [FourDayWeekSource(http_client=http_client, limit=2)]
            since = datetime(2024, 1, 1, tzinfo=timezone.utc)

            # Run ingestion once.
            # We mock the return of bulk_create_skipping_duplicates to simulate 2 new jobs.
            job_repo_instance.bulk_create_skipping_duplicates.return_value = ["uuid1", "uuid2"]
            report1 = await run_ingestion(sources, since, mock_session, limit=2)
            assert report1.total_new == 2

            # Second call to bulk_create_skipping_duplicates returns empty list (duplicates)
            # Note: We are using the same jobs fetched in the first call (because we're only mocking the Repo, not the Source)
            # Wait, run_ingestion calls source.fetch again.
            # VCR should play the same response.
            job_repo_instance.bulk_create_skipping_duplicates.return_value = []
            report2 = await run_ingestion(sources, since, mock_session, limit=2)

            assert report2.total_new == 0
            # Total duplicates should be 2 because we fetched 2 jobs and 0 were inserted.
            assert report2.total_duplicates == 2


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_orchestrator_circuit_breaker_integration() -> None:
    """
    Tests that the circuit breaker skips a source if allow_request returns False.
    """
    mock_session = MagicMock()

    with patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockBreaker:
        breaker_instance = MockBreaker.return_value
        breaker_instance.allow_request.return_value = False

        async with SourceHttpClient() as http_client:
            sources = [FourDayWeekSource(http_client=http_client, limit=2)]
            since = datetime(2024, 1, 1, tzinfo=timezone.utc)

            report = await run_ingestion(sources, since, mock_session)

            assert len(report.source_results) == 1
            assert report.source_results[0].status == "skipped_breaker"
            assert report.total_new == 0


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_orchestrator_failure_isolation_integration() -> None:
    """
    Tests that one failing source doesn't prevent others from completing.
    """
    mock_session = MagicMock()

    with (
        patch("jobhunter.sources.orchestrator.JobRepo") as MockJobRepo,
        patch("jobhunter.sources.orchestrator.CircuitBreaker") as MockBreaker,
    ):
        job_repo_instance = MockJobRepo.return_value
        job_repo_instance.bulk_create_skipping_duplicates.return_value = ["uuid-remoteok"]

        breaker_instance = MockBreaker.return_value
        breaker_instance.allow_request.return_value = True

        async with SourceHttpClient() as http_client:
            # We'll mock one source to fail
            failing_source = FourDayWeekSource(http_client=http_client)

            with patch.object(FourDayWeekSource, "fetch") as mock_fetch:
                mock_fetch.side_effect = Exception("API Down")

                sources = [failing_source, RemoteOKSource(http_client=http_client)]
                since = datetime(2024, 1, 1, tzinfo=timezone.utc)

                report = await run_ingestion(sources, since, mock_session, limit=1)

                assert len(report.source_results) == 2

                # Find results
                fail_res = next(
                    r for r in report.source_results if r.source_name == "FourDayWeekSource"
                )
                success_res = next(
                    r for r in report.source_results if r.source_name == "RemoteOKSource"
                )

                assert fail_res.status == "failed"
                assert fail_res.error == "API Down"
                assert success_res.status == "success"
                assert success_res.new_jobs > 0

                assert report.total_errors == 1
                assert report.total_new == success_res.new_jobs
