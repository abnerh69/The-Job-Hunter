"""
Source ABC and the `RawJob` DTO that every adapter emits.

`BaseSource` deliberately exposes only `fetch()`. The acceptance criteria for
E03-S01 originally asked for `name: str`, `default_rate_limit: float` and a
`canonicalize_url` method on the base class; those responsibilities live
elsewhere (literal `source_name` per subclass, optional `default_rate_limit`
on subclasses that deviate from the default, free functions in
`sources/url_utils.py`). See `docs/adr/ADR-007-thin-basesource-contract.md`
for the rationale.
"""

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
