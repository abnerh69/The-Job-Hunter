from datetime import datetime
from typing import Any, AsyncIterator

import structlog

from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.http import SourceHttpClient
from jobhunter.sources.registry import register_source

logger = structlog.get_logger(__name__)

BASE_API_URL = "https://4dayweek.io/api/v2/jobs"


@register_source
class FourDayWeekSource(BaseSource):
    """
    Job source for 4dayweek.io.
    Fetches jobs from their public JSON API (v2).
    """

    def __init__(
        self,
        http_client: SourceHttpClient | None = None,
        limit: int = 100,
    ):
        """
        Initializes the FourDayWeekSource.

        Args:
            http_client: Optional SourceHttpClient instance.
            limit: Number of items per page (max 100).
        """
        self.http_client = http_client or SourceHttpClient()
        self.limit = limit

    async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
        """
        Fetches job listings from 4dayweek.io posted after the given datetime.

        Args:
            since: The datetime from which to start fetching jobs.

        Yields:
            RawJob: A normalized job listing.
        """
        page = 1
        has_more = True

        while has_more:
            params = {
                "page": page,
                "limit": self.limit,
                "sort": "date",
            }

            try:
                response = await self.http_client.get(BASE_API_URL, params=params)
                data = response.json()

                jobs_data = data.get("data", [])
                for item in jobs_data:
                    job = self._parse_job(item)
                    if not job:
                        continue

                    if job.posted_at and job.posted_at < since:
                        # Since they are sorted by date desc, if we find one older than since,
                        # we can stop fetching.
                        has_more = False
                        break

                    yield job

                has_more = has_more and data.get("has_more", False)
                page += 1

            except Exception as e:
                logger.error("failed to fetch 4dayweek jobs", page=page, error=str(e))
                break

    def _parse_job(self, item: dict[str, Any]) -> RawJob | None:
        """
        Parses an API job item into a RawJob model.

        Args:
            item: The job item from the API.

        Returns:
            RawJob | None: The normalized RawJob or None if malformed.
        """
        try:
            posted_at_str = item.get("posted_at")
            posted_at = None
            if posted_at_str:
                # 4dayweek.io v2 API uses ISO 8601 strings (e.g., "2025-01-12T00:00:00Z")
                # and fromisoformat supports 'Z' since Python 3.11
                posted_at = datetime.fromisoformat(posted_at_str.replace("Z", "+00:00"))

            # Location handling
            locations = []
            office_locations = item.get("office_locations", [])
            for loc in office_locations:
                city = loc.get("city")
                country = loc.get("country")
                if city and country:
                    locations.append(f"{city}, {country}")
                elif country:
                    locations.append(country)

            remote_allowed = item.get("remote_allowed", [])
            for loc in remote_allowed:
                country = loc.get("country")
                if country:
                    locations.append(f"Remote ({country})")

            if not locations and item.get("is_remote"):
                locations.append("Remote")

            location_raw = "; ".join(locations) if locations else None

            company_data = item.get("company", {})
            company_name = company_data.get("name", "Unknown")

            return RawJob(
                source_name="fourdayweek",
                source_id=item.get("id") or item.get("slug", ""),
                url=item.get("url", ""),
                title=item.get("title", ""),
                company=company_name,
                location_raw=location_raw,
                description=item.get("description", ""),
                posted_at=posted_at,
                raw_payload=item,
            )
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("failed to parse 4dayweek job item", error=str(e))
            return None
