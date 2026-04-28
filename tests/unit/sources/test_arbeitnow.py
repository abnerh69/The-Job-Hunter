import httpx
import pytest
from datetime import datetime, timezone

from jobhunter.sources.arbeitnow import ArbeitnowSource, API_URL
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.asyncio
async def test_arbeitnow_fetch_success() -> None:
    # Prepare mock data
    mock_payload = {
        "data": [
            {
                "slug": "job-1",
                "company_name": "Company 1",
                "title": "Title 1",
                "description": "Desc 1",
                "url": "http://example.com/1",
                "location": "Berlin",
                "created_at": 1777384845,
            },
            {
                "slug": "job-2",
                "company_name": "Company 2",
                "title": "Title 2",
                "description": "Desc 2",
                "url": "http://example.com/2",
                "location": "Remote",
                "created_at": 1777384800,
            },
        ],
        "links": {"next": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = ArbeitnowSource(http_client=http_client)
        since = datetime.fromtimestamp(1777000000, tz=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 2
        assert jobs[0].source_id == "job-1"
        assert jobs[0].company == "Company 1"
        assert jobs[0].posted_at == datetime.fromtimestamp(1777384845, tz=timezone.utc)
        assert jobs[1].source_id == "job-2"


@pytest.mark.asyncio
async def test_arbeitnow_fetch_since_filter() -> None:
    # Job 1 is new, Job 2 is old.
    mock_payload = {
        "data": [
            {
                "slug": "new-job",
                "company_name": "Company 1",
                "title": "Title 1",
                "description": "Desc 1",
                "url": "http://example.com/1",
                "created_at": 1777384845,
            },
            {
                "slug": "old-job",
                "company_name": "Company 2",
                "title": "Title 2",
                "description": "Desc 2",
                "url": "http://example.com/2",
                "created_at": 1777000000,
            },
        ],
        "links": {"next": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = ArbeitnowSource(http_client=http_client)
        # since is between Job 1 and Job 2
        since = datetime.fromtimestamp(1777100000, tz=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 1
        assert jobs[0].source_id == "new-job"


@pytest.mark.asyncio
async def test_arbeitnow_pagination() -> None:
    # Page 1 has a link to Page 2
    page1 = {
        "data": [
            {
                "slug": "job-1",
                "company_name": "C1",
                "title": "T1",
                "description": "D1",
                "url": "U1",
                "created_at": 1777384845,
            }
        ],
        "links": {"next": API_URL + "?page=2"},
    }
    page2 = {
        "data": [
            {
                "slug": "job-2",
                "company_name": "C2",
                "title": "T2",
                "description": "D2",
                "url": "U2",
                "created_at": 1777384840,
            }
        ],
        "links": {"next": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json=page2)
        return httpx.Response(200, json=page1)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        source = ArbeitnowSource(http_client=http_client)
        since = datetime.fromtimestamp(1777000000, tz=timezone.utc)

        jobs = []
        async for job in source.fetch(since):
            jobs.append(job)

        assert len(jobs) == 2
        assert jobs[0].source_id == "job-1"
        assert jobs[1].source_id == "job-2"


@pytest.mark.asyncio
async def test_arbeitnow_malformed_job() -> None:
    mock_payload = {
        "data": [
            {
                "slug": "good-job",
                "company_name": "C1",
                "title": "T1",
                "description": "D1",
                "url": "U1",
                "created_at": 1777384845,
            },
            {
                "slug": "bad-job",
                # missing company_name and title
                "description": "D2",
                "url": "U2",
                "created_at": 1777384840,
            },
        ],
        "links": {"next": None},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as http_client:
        from unittest.mock import patch

        with patch("jobhunter.sources.arbeitnow.logger") as mock_logger:
            source = ArbeitnowSource(http_client=http_client)
            since = datetime.fromtimestamp(1777000000, tz=timezone.utc)

            jobs = []
            async for job in source.fetch(since):
                jobs.append(job)

            assert len(jobs) == 1
            assert jobs[0].source_id == "good-job"
            mock_logger.warning.assert_called()
