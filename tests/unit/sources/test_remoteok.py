import httpx
import pytest
from datetime import datetime, timezone
from jobhunter.sources.remoteok import RemoteOKSource
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.asyncio
async def test_remoteok_parse_job_success() -> None:
    source = RemoteOKSource()
    raw_job = {
        "id": "123",
        "url": "https://remoteok.com/123",
        "position": "Software Engineer",
        "company": "Tech Corp",
        "location": "Worldwide",
        "description": "A great job",
        "date": "2024-04-28T10:00:00+00:00",
        "tags": ["python", "backend"],
    }
    job = source._parse_job(raw_job)
    assert job is not None
    assert job.source_id == "123"
    assert job.title == "Software Engineer"
    assert job.posted_at == datetime(2024, 4, 28, 10, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_remoteok_parse_job_malformed() -> None:
    source = RemoteOKSource()
    raw_job = {
        "id": "123",
        # missing mandatory fields
    }
    job = source._parse_job(raw_job)
    assert job is None


@pytest.mark.asyncio
async def test_remoteok_matches_tags() -> None:
    source = RemoteOKSource(tags=["python", "ai"])
    assert source._matches_tags(["Python", "Something"]) is True
    assert source._matches_tags(["AI", "Deep Learning"]) is True
    assert source._matches_tags(["java", "rust"]) is False
    assert source._matches_tags([]) is False
    assert source._matches_tags(None) is False


@pytest.mark.asyncio
async def test_remoteok_fetch_since_filter_unit() -> None:
    # Metadata + 2 jobs
    mock_payload = [
        {"legal": "Terms..."},
        {
            "id": "new",
            "url": "https://remoteok.com/new",
            "position": "New Job",
            "company": "C1",
            "description": "D1",
            "date": "2024-04-28T10:00:00+00:00",
            "tags": ["python"],
        },
        {
            "id": "old",
            "url": "https://remoteok.com/old",
            "position": "Old Job",
            "company": "C2",
            "description": "D2",
            "date": "2024-04-20T10:00:00+00:00",
            "tags": ["python"],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = RemoteOKSource(http_client=http_client)
        # since is between New and Old
        since = datetime(2024, 4, 25, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 1
        assert jobs[0].source_id == "new"
