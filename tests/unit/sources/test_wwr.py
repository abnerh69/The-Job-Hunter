from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from jobhunter.sources.wwr import WeWorkRemotelySource


def test_strip_html() -> None:
    source = WeWorkRemotelySource()
    html = "<p>Hello <b>World</b>!</p><br><a href='http://example.com'>Link</a>"
    # BeautifulSoup's get_text(separator=" ") will put space between tags
    # <p>Hello <b>World</b>!</p> -> "Hello World !" (depending on separator)
    # Actually, separator=" " means tags are replaced by space if they are not inline?
    # Let's see what it actually does.
    stripped = source._strip_html(html)
    assert "Hello" in stripped
    assert "World" in stripped
    assert "Link" in stripped
    assert "<p>" not in stripped
    assert "</a>" not in stripped


def test_parse_entry_with_rfc822_date() -> None:
    source = WeWorkRemotelySource()
    # Mocking a feedparser entry
    entry = MagicMock()
    entry.get.side_effect = lambda k, default=None: {
        "title": "ACME Corp: Senior Backend Engineer",
        "link": "https://weworkremotely.com/jobs/123",
        "summary": "<p>Job description</p>",
        "id": "123",
    }.get(k, default)

    # published_parsed is a time.struct_time (tuple)
    # 2023-10-27 10:00:00 UTC
    published_parsed = MagicMock()
    published_parsed.tm_year = 2023
    published_parsed.tm_mon = 10
    published_parsed.tm_mday = 27
    published_parsed.tm_hour = 10
    published_parsed.tm_min = 0
    published_parsed.tm_sec = 0
    entry.published_parsed = published_parsed

    job = source._parse_entry(entry)

    assert job is not None
    assert job.company == "ACME Corp"
    assert job.title == "Senior Backend Engineer"
    assert job.url == "https://weworkremotely.com/jobs/123"
    assert job.description == "Job description"
    assert job.posted_at == datetime(2023, 10, 27, 10, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_fetch_deduplication() -> None:
    http_client = MagicMock()
    # Mock two categories that return the same job
    source = WeWorkRemotelySource(http_client=http_client, categories=["cat1", "cat2"])

    feed1 = MagicMock()
    feed1.bozo = False
    entry1 = MagicMock()
    entry1.get.side_effect = lambda k, default=None: {
        "title": "Company: Job 1",
        "link": "https://weworkremotely.com/jobs/1",
        "summary": "desc",
        "id": "1",
    }.get(k, default)
    published_parsed1 = MagicMock()
    published_parsed1.tm_year = 2023
    published_parsed1.tm_mon = 10
    published_parsed1.tm_mday = 27
    published_parsed1.tm_hour = 10
    published_parsed1.tm_min = 0
    published_parsed1.tm_sec = 0
    entry1.published_parsed = published_parsed1
    feed1.entries = [entry1]

    feed2 = MagicMock()
    feed2.bozo = False
    entry2 = MagicMock()
    entry2.get.side_effect = lambda k, default=None: {
        "title": "Company: Job 1",
        "link": "https://weworkremotely.com/jobs/1",  # Same URL
        "summary": "desc",
        "id": "1",
    }.get(k, default)
    published_parsed2 = MagicMock()
    published_parsed2.tm_year = 2023
    published_parsed2.tm_mon = 10
    published_parsed2.tm_mday = 27
    published_parsed2.tm_hour = 10
    published_parsed2.tm_min = 0
    published_parsed2.tm_sec = 0
    entry2.published_parsed = published_parsed2
    feed2.entries = [entry2]

    # Since WeWorkRemotelySource calls http_client.get(url) and then feedparser.parse(response.text)

    resp1 = MagicMock()
    resp1.text = "rss content 1"
    resp2 = MagicMock()
    resp2.text = "rss content 2"

    http_client.get = AsyncMock(side_effect=[resp1, resp2])

    # This is tricky because feedparser.parse is called on the module.
    # It's better to patch it.
    import jobhunter.sources.wwr

    original_parse = jobhunter.sources.wwr.feedparser.parse  # type: ignore[attr-defined]
    jobhunter.sources.wwr.feedparser.parse = MagicMock(side_effect=[feed1, feed2])  # type: ignore[attr-defined]

    try:
        jobs = []
        async for job in source.fetch(since=datetime(2000, 1, 1, tzinfo=timezone.utc)):
            jobs.append(job)
    finally:
        jobhunter.sources.wwr.feedparser.parse = original_parse  # type: ignore[attr-defined]

    assert len(jobs) == 1
    assert jobs[0].url == "https://weworkremotely.com/jobs/1"


def test_parse_entry_no_company_in_title() -> None:
    source = WeWorkRemotelySource()
    entry = MagicMock()
    entry.get.side_effect = lambda k, default=None: {
        "title": "Just the Position",
        "link": "https://weworkremotely.com/jobs/123",
        "summary": "desc",
    }.get(k, default)
    entry.published_parsed = None

    job = source._parse_entry(entry)
    assert job is not None
    assert job.company == "Unknown"
    assert job.title == "Just the Position"
