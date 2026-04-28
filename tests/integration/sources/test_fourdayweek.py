import pytest
import vcr  # type: ignore[import-untyped]
from datetime import datetime, timezone
from jobhunter.sources.fourdayweek import FourDayWeekSource
from jobhunter.sources.http import SourceHttpClient

# Configure VCR
my_vcr = vcr.VCR(
    cassette_library_dir="tests/integration/sources/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path", "query"],
)


@pytest.mark.asyncio
async def test_fourdayweek_fetch_integration() -> None:
    """
    Integration test for FourDayWeekSource using a cassette.
    """
    with my_vcr.use_cassette("fourdayweek.yaml"):
        async with SourceHttpClient() as http_client:
            source = FourDayWeekSource(http_client=http_client, limit=5)

            # Use a date that should return some results based on the cassette
            # In a real recording, we'd use a date from the past
            since = datetime(2024, 1, 1, tzinfo=timezone.utc)

            jobs = []
            async for job in source.fetch(since):
                jobs.append(job)
                if len(jobs) >= 5:
                    break

            assert len(jobs) > 0
            for job in jobs:
                assert job.source_name == "fourdayweek"
                assert job.source_id is not None
                assert job.url.startswith("https://4dayweek.io/job/")
                assert job.posted_at is not None
                assert job.posted_at >= since
                assert job.company != "Unknown"
                assert len(job.description) > 0
