import httpx
import pytest
from datetime import datetime, timezone
from jobhunter.sources.fourdayweek import FourDayWeekSource
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.asyncio
async def test_fourdayweek_fetch_success() -> None:
    # Prepare mock data
    mock_payload = {
        "data": [
            {
                "id": "job-1",
                "slug": "job-1-slug",
                "title": "Title 1",
                "description": "Desc 1",
                "url": "https://4dayweek.io/job/job-1-slug",
                "posted_at": "2025-01-12T10:00:00Z",
                "company": {"name": "Company 1"},
                "is_remote": True,
                "office_locations": [{"city": "Berlin", "country": "Germany"}],
            },
            {
                "id": "job-2",
                "slug": "job-2-slug",
                "title": "Title 2",
                "description": "Desc 2",
                "url": "https://4dayweek.io/job/job-2-slug",
                "posted_at": "2025-01-12T09:00:00Z",
                "company": {"name": "Company 2"},
                "is_remote": False,
                "remote_allowed": [{"country": "UK"}],
            },
        ],
        "has_more": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = FourDayWeekSource(http_client=http_client)
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 2
        assert jobs[0].source_id == "job-1"
        assert jobs[0].company == "Company 1"
        assert jobs[0].location_raw == "Berlin, Germany"
        assert jobs[1].source_id == "job-2"
        assert jobs[1].location_raw == "Remote (UK)"


@pytest.mark.asyncio
async def test_fourdayweek_fetch_since_filter() -> None:
    # Job 1 is new, Job 2 is old.
    mock_payload = {
        "data": [
            {
                "id": "new-job",
                "title": "New Title",
                "description": "Desc",
                "url": "URL",
                "posted_at": "2025-01-12T10:00:00Z",
                "company": {"name": "C1"},
            },
            {
                "id": "old-job",
                "title": "Old Title",
                "description": "Desc",
                "url": "URL",
                "posted_at": "2025-01-01T00:00:00Z",
                "company": {"name": "C2"},
            },
        ],
        "has_more": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = FourDayWeekSource(http_client=http_client)
        # since is after Job 2
        since = datetime(2025, 1, 5, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 1
        assert jobs[0].source_id == "new-job"


@pytest.mark.asyncio
async def test_fourdayweek_pagination() -> None:
    page1 = {
        "data": [
            {
                "id": "job-1",
                "title": "T1",
                "description": "D1",
                "url": "U1",
                "posted_at": "2025-01-12T10:00:00Z",
                "company": {"name": "C1"},
            }
        ],
        "has_more": True,
    }
    page2 = {
        "data": [
            {
                "id": "job-2",
                "title": "T2",
                "description": "D2",
                "url": "U2",
                "posted_at": "2025-01-12T09:00:00Z",
                "company": {"name": "C2"},
            }
        ],
        "has_more": False,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = FourDayWeekSource(http_client=http_client)
        since = datetime(2025, 1, 1, tzinfo=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 2
        assert jobs[0].source_id == "job-1"
        assert jobs[1].source_id == "job-2"
