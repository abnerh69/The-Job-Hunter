from datetime import datetime
from typing import AsyncIterator

from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.registry import get_all_sources, register_source


def test_registry() -> None:
    @register_source
    class MockSource1(BaseSource):
        async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
            if False:
                yield RawJob(
                    source_name="", source_id="", url="", title="", company="", description=""
                )

    @register_source
    class MockSource2(BaseSource):
        async def fetch(self, since: datetime) -> AsyncIterator[RawJob]:
            if False:
                yield RawJob(
                    source_name="", source_id="", url="", title="", company="", description=""
                )

    sources = get_all_sources()
    assert MockSource1 in sources
    assert MockSource2 in sources
    assert len(sources) >= 2
