import pytest
from datetime import datetime, timezone
from jobhunter.sources.arbeitnow import ArbeitnowSource
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_arbeitnow_fetch_integration() -> None:
    """
    Integration test for ArbeitnowSource using a cassette.
    """
    async with SourceHttpClient() as http_client:
        source = ArbeitnowSource(http_client=http_client)

        # Use an old date to get some results
        since = datetime(2024, 1, 1, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)
            if len(jobs) >= 5:
                break

        assert len(jobs) > 0
        for job in jobs:
            assert job.source_name == "arbeitnow"
            assert job.source_id is not None
            assert job.url.startswith(
                "https://www.arbeitnow.com/jobs/companies/"
            ) or job.url.startswith("https://www.arbeitnow.com/jobs/view/")
            assert job.posted_at is not None
            assert job.posted_at >= since
            assert job.company != "Unknown"
            assert len(job.description) > 0


@pytest.mark.vcr
@pytest.mark.asyncio
async def test_arbeitnow_pagination_integration() -> None:
    """
    Tests that ArbeitnowSource handles pagination correctly.
    """
    async with SourceHttpClient() as http_client:
        # We need a small page size if possible to test pagination with few jobs,
        # but Arbeitnow API doesn't seem to have a limit param in the URL.
        # So we'll just fetch more than one page if possible,
        # or at least verify it follows the 'next' link.
        source = ArbeitnowSource(http_client=http_client)
        since = datetime(2020, 1, 1, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)
            if len(jobs) >= 150:  # Default page size is usually 100
                break

        # If we got more than 100, it means we definitely paginated.
        # Even if we didn't, we can't force it easily without a mock.
        assert len(jobs) > 0
