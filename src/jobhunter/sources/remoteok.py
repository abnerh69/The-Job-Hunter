from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog

from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.http import SourceHttpClient
from jobhunter.sources.registry import register_source

logger = structlog.get_logger(__name__)

API_URL = "https://remoteok.com/api"


@register_source
class RemoteOKSource(BaseSource):
    """
    Job source for RemoteOK (remoteok.com).
    """

    default_rate_limit: float = 0.33
    DEFAULT_TAGS: list[str] = ["python", "ai", "ml", "flutter", "dart", "senior", "backend"]

    def __init__(self, http_client: SourceHttpClient | None = None, tags: list[str] | None = None):
        """
        Initializes the RemoteOKSource.

        Args:
            http_client: Optional SourceHttpClient instance.
            tags: Optional list of tags to filter by.
        """
        self.http_client = http_client or SourceHttpClient()
        self.tags = [t.lower() for t in (tags or self.DEFAULT_TAGS)]

    async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
        """
        Fetches job listings from RemoteOK posted after the given datetime.

        Args:
            since: The datetime from which to start fetching jobs.

        Yields:
            RawJob: A normalized job listing.
        """
        response = await self.http_client.get(API_URL)
        payload = response.json()

        if not isinstance(payload, list) or len(payload) <= 1:
            logger.warning("received empty or invalid payload from RemoteOK")
            return

        # Skip the first element as it contains metadata
        jobs_data = payload[1:]

        for raw_job in jobs_data:
            job = self._parse_job(raw_job)
            if job:
                if job.posted_at and job.posted_at < since:
                    # RemoteOK returns jobs in descending order of date.
                    # Since it's a single page, we could potentially stop,
                    # but continuing is safer if order is not strictly guaranteed.
                    continue

                if self._matches_tags(raw_job.get("tags", [])):
                    yield job

    def _matches_tags(self, job_tags: list[str] | None) -> bool:
        """
        Checks if the job tags match any of the configured tags.

        Args:
            job_tags: The list of tags from the job listing.

        Returns:
            bool: True if at least one tag matches, False otherwise.
        """
        if not job_tags:
            return False
        job_tags_lower = [t.lower() for t in job_tags]
        return any(tag in job_tags_lower for tag in self.tags)

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
            date_str = raw.get("date")
            if date_str:
                # ISO8601 parsing
                posted_at = datetime.fromisoformat(date_str)
                # Ensure it's UTC
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                else:
                    posted_at = posted_at.astimezone(timezone.utc)

            return RawJob(
                source_name="remoteok",
                source_id=str(raw["id"]),
                url=raw["url"],
                title=raw["position"],
                company=raw["company"],
                location_raw=raw.get("location"),
                description=raw["description"],
                posted_at=posted_at,
                raw_payload=raw,
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("failed to parse job", error=str(e), job_id=raw.get("id"))
            return None
