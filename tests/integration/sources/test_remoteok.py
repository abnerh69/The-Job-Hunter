import pytest
import vcr
from datetime import datetime, timezone
from jobhunter.sources.remoteok import RemoteOKSource
from jobhunter.sources.http import SourceHttpClient

# Configure VCR
my_vcr = vcr.VCR(
    cassette_library_dir="tests/integration/sources/cassettes",
    record_mode="once",
    match_on=["method", "scheme", "host", "port", "path", "query"],
    filter_headers=["User-Agent"],  # User-Agent might vary, but for RemoteOK it's mandatory.
    # Actually, let's NOT filter it to ensure it's recorded correctly.
)


@pytest.mark.asyncio
async def test_remoteok_fetch_integration() -> None:
    """
    Integration test for RemoteOKSource using a cassette.
    """
    with my_vcr.use_cassette("remoteok.yaml"):
        async with SourceHttpClient() as http_client:
            # We use a broad tag set to ensure we get some results from the cassette
            # or we use the default tags.
            source = RemoteOKSource(http_client=http_client)

            # Use a very old 'since' to get many jobs from the top of the feed
            since = datetime(2020, 1, 1, tzinfo=timezone.utc)

            jobs = []
            async for job in source.fetch(since):
                jobs.append(job)
                if len(jobs) >= 5:  # Limit to 5 for the test
                    break

            assert len(jobs) > 0
            for job in jobs:
                assert job.source_name == "remoteok"
                assert job.source_id is not None
                assert job.url.lower().startswith("https://remoteok.com")
                assert job.posted_at is not None
                assert job.posted_at >= since


@pytest.mark.asyncio
async def test_remoteok_metadata_skipped_integration() -> None:
    """
    Ensures that the first element (metadata) is skipped.
    """
    with my_vcr.use_cassette("remoteok.yaml"):
        async with SourceHttpClient() as http_client:
            source = RemoteOKSource(http_client=http_client)
            since = datetime(2020, 1, 1, tzinfo=timezone.utc)

            async for job in source.fetch(since):
                # The first yielded item should be a real job, not metadata.
                # Metadata doesn't have 'position' or 'company' in the same way.
                # Our parser would return None for metadata anyway, but fetch skips it.
                assert job.title is not None
                assert job.company is not None
                # RemoteOK metadata has "legal" and "last_updated", not "position"
                assert "legal" not in job.raw_payload if job.raw_payload else True
                break


@pytest.mark.asyncio
async def test_remoteok_tag_filtering_integration() -> None:
    """
    Tests that tag filtering works as expected.
    """
    with my_vcr.use_cassette("remoteok.yaml"):
        async with SourceHttpClient() as http_client:
            # Filter by a specific tag we expect to find, e.g., 'python'
            source = RemoteOKSource(http_client=http_client, tags=["python"])
            since = datetime(2020, 1, 1, tzinfo=timezone.utc)

            jobs = []
            async for job in source.fetch(since):
                jobs.append(job)
                # Check that at least one tag of the job is 'python'
                tags = [t.lower() for t in job.raw_payload.get("tags", [])]
                assert "python" in tags
                if len(jobs) >= 3:
                    break

            assert len(jobs) > 0
