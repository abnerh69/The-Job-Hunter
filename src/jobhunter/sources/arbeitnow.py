from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog

from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.http import SourceHttpClient
from jobhunter.sources.registry import register_source

logger = structlog.get_logger(__name__)

API_URL = "https://www.arbeitnow.com/api/job-board-api"


@register_source
class ArbeitnowSource(BaseSource):
    """
    Job source for Arbeitnow (arbeitnow.com).
    """

    def __init__(self, http_client: SourceHttpClient | None = None):
        """
        Initializes the ArbeitnowSource.

        Args:
            http_client: Optional SourceHttpClient instance.
        """
        self.http_client = http_client or SourceHttpClient()

    async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
        """
        Fetches job listings from Arbeitnow posted after the given datetime.

        Args:
            since: The datetime from which to start fetching jobs.

        Yields:
            RawJob: A normalized job listing.
        """
        url: str | None = API_URL

        while url:
            response = await self.http_client.get(url)
            payload = response.json()

            jobs_data = payload.get("data", [])
            if not jobs_data:
                break

            for raw_job in jobs_data:
                job = self._parse_job(raw_job)
                if job:
                    if job.posted_at and job.posted_at < since:
                        # Since Arbeitnow is ordered by created_at desc,
                        # once we hit an old job, we can stop fetching.
                        return

                    yield job

            url = payload.get("links", {}).get("next")

    def _parse_job(self, raw: dict[str, Any]) -> RawJob | None:
        """
        Parses a raw job dictionary into a RawJob model.

        Args:
            raw: The raw job dictionary from the API.

        Returns:
            RawJob | None: The normalized RawJob or None if malformed.
        """
        try:
            posted_at = None
            created_at = raw.get("created_at")
            if created_at:
                # Arbeitnow uses Unix timestamps
                posted_at = datetime.fromtimestamp(created_at, tz=timezone.utc)

            return RawJob(
                source_name="arbeitnow",
                source_id=str(raw["slug"]),
                url=raw["url"],
                title=raw["title"],
                company=raw["company_name"],
                location_raw=raw.get("location"),
                description=raw["description"],
                posted_at=posted_at,
                raw_payload=raw,
            )
        except (KeyError, TypeError) as e:
            logger.warning("failed to parse job", error=str(e), slug=raw.get("slug"))
            return None
