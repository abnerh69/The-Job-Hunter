from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator

from pydantic import BaseModel, ConfigDict


class RawJob(BaseModel):
    """
    Pydantic model representing a raw job listing from a source.
    This model is frozen to ensure immutability.
    """

    model_config = ConfigDict(frozen=True)

    source_name: str
    source_id: str
    url: str
    title: str
    company: str
    location_raw: str | None = None
    description: str
    posted_at: datetime | None = None
    raw_payload: dict[str, Any] | None = None


class BaseSource(ABC):
    """
    Abstract Base Class for all job sources.
    """

    @abstractmethod
    async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
        """
        Fetches job listings from the source that were posted after the given datetime.

        Args:
            since: The datetime from which to start fetching jobs.

        Yields:
            RawJob: A normalized job listing.
        """
        # This is an abstract method and must be implemented by subclasses.
        # We use a dummy yield to make it an async generator.
        if False:
            yield RawJob(
                source_name="",
                source_id="",
                url="",
                title="",
                company="",
                description="",
            )
