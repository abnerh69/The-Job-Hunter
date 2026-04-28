import pytest
from datetime import datetime, timezone
from jobhunter.sources.wwr import WeWorkRemotelySource
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_wwr_fetch_integration() -> None:
    """
    Integration test for WeWorkRemotelySource using a cassette.
    """
    async with SourceHttpClient() as http_client:
        # Fetch from only one category to keep the cassette small
        source = WeWorkRemotelySource(
            http_client=http_client, categories=["remote-programming-jobs"]
        )

        # Use a relatively old date to get some results
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)
            if len(jobs) >= 5:  # Limit to 5 for the test
                break

        assert len(jobs) > 0
        for job in jobs:
            assert job.source_name == "weworkremotely"
            assert job.source_id is not None
            assert job.url.startswith("https://weworkremotely.com")
            assert job.posted_at is not None
            assert job.posted_at >= since
            assert job.company != "Unknown"
            assert len(job.description) > 0
            # Verify HTML stripping
            assert "<p>" not in job.description
            assert "</a>" not in job.description
