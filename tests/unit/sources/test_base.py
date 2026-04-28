from datetime import datetime

import pytest
from pydantic import ValidationError

from jobhunter.sources.base import RawJob


def test_raw_job_valid() -> None:
    job = RawJob(
        source_name="test",
        source_id="123",
        url="https://example.com",
        title="Software Engineer",
        company="Tech Corp",
        description="We are looking for...",
        posted_at=datetime(2023, 10, 27, 12, 0, 0),
        raw_payload={"key": "value"},
    )
    assert job.source_name == "test"
    assert job.raw_payload == {"key": "value"}


def test_raw_job_frozen() -> None:
    job = RawJob(
        source_name="test",
        source_id="123",
        url="https://example.com",
        title="Software Engineer",
        company="Tech Corp",
        description="We are looking for...",
    )
    with pytest.raises(ValidationError):
        # We use a type ignore here because Pydantic models are frozen,
        # but mypy might catch it.
        job.title = "New Title"


def test_raw_job_missing_fields() -> None:
    with pytest.raises(ValidationError):
        # Missing required field source_name
        RawJob(  # type: ignore[call-arg]
            source_id="123",
            url="https://example.com",
            title="Software Engineer",
            company="Tech Corp",
            description="...",
        )
