from datetime import datetime, timezone
from typing import Any, AsyncIterator

import feedparser  # type: ignore[import-untyped]
import structlog
from bs4 import BeautifulSoup

from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.http import SourceHttpClient
from jobhunter.sources.registry import register_source

logger = structlog.get_logger(__name__)

BASE_RSS_URL = "https://weworkremotely.com/categories/{category}.rss"

DEFAULT_CATEGORIES = [
    "remote-programming-jobs",
    "devops-sysadmin-jobs",
    "back-end-programming-jobs",
]


@register_source
class WeWorkRemotelySource(BaseSource):
    """
    Job source for We Work Remotely (weworkremotely.com).
    Fetches jobs from multiple RSS feeds.
    """

    def __init__(
        self,
        http_client: SourceHttpClient | None = None,
        categories: list[str] | None = None,
    ):
        """
        Initializes the WeWorkRemotelySource.

        Args:
            http_client: Optional SourceHttpClient instance.
            categories: Optional list of WWR categories to fetch from.
        """
        self.http_client = http_client or SourceHttpClient()
        self.categories = categories or DEFAULT_CATEGORIES

    async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
        """
        Fetches job listings from We Work Remotely posted after the given datetime.

        Args:
            since: The datetime from which to start fetching jobs.

        Yields:
            RawJob: A normalized job listing.
        """
        seen_urls: set[str] = set()

        for category in self.categories:
            url = BASE_RSS_URL.format(category=category)
            try:
                response = await self.http_client.get(url)
                # feedparser.parse can take a string
                feed = feedparser.parse(response.text)

                if feed.bozo:
                    logger.warning(
                        "feedparser encountered an error",
                        url=url,
                        error=str(feed.bozo_exception),
                    )

                for entry in feed.entries:
                    job = self._parse_entry(entry)
                    if not job:
                        continue

                    if job.url in seen_urls:
                        continue

                    if job.posted_at and job.posted_at < since:
                        continue

                    seen_urls.add(job.url)
                    yield job

            except Exception as e:
                logger.error("failed to fetch or parse WWR feed", category=category, error=str(e))

    def _strip_html(self, html: str) -> str:
        """
        Strips HTML tags from a string, preserving text.

        Args:
            html: The HTML string to strip.

        Returns:
            str: The plain text content.
        """
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        # get_text() joins text with a separator, we'll use space or newline.
        return soup.get_text(separator=" ", strip=True)

    def _parse_entry(self, entry: Any) -> RawJob | None:
        """
        Parses a feed entry into a RawJob model.

        Args:
            entry: The feed entry from feedparser.

        Returns:
            RawJob | None: The normalized RawJob or None if malformed.
        """
        try:
            # feedparser handles RFC 822 dates and provides a published_parsed tuple
            # or we can use the published string and parse it.
            # published_parsed is a time.struct_time in UTC.
            posted_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                # entry.published_parsed is a time.struct_time
                posted_at = datetime(
                    entry.published_parsed.tm_year,
                    entry.published_parsed.tm_mon,
                    entry.published_parsed.tm_mday,
                    entry.published_parsed.tm_hour,
                    entry.published_parsed.tm_min,
                    entry.published_parsed.tm_sec,
                    tzinfo=timezone.utc,
                )

            # WWR RSS entries usually have:
            # title: "Company: Position" or just "Position"
            # link: URL to the job
            # summary: HTML description
            # id: often the same as link

            title_full = entry.get("title", "")
            company = "Unknown"
            title = title_full

            if ":" in title_full:
                parts = title_full.split(":", 1)
                company = parts[0].strip()
                title = parts[1].strip()

            return RawJob(
                source_name="weworkremotely",
                source_id=entry.get("id") or entry.get("link", ""),
                url=entry.get("link", ""),
                title=title,
                company=company,
                description=self._strip_html(entry.get("summary", "")),
                posted_at=posted_at,
                raw_payload=dict(entry),
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("failed to parse WWR entry", error=str(e))
            return None
