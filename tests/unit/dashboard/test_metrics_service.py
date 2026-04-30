from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from jobhunter.dashboard.services.metrics import MetricsService
from jobhunter.db.enums import (
    ApplicationStatus,
    JobStatus,
    JobTier,
    LLMPurpose,
    SourceState,
)
from jobhunter.db.base import Base
from jobhunter.db.models import Application, Job, LLMCall, SourceHealth


@pytest.fixture(autouse=True)
def setup_db(session: Session) -> None:
    Base.metadata.create_all(bind=session.get_bind())


@pytest.fixture
def metrics_service(session: Session) -> MetricsService:
    return MetricsService(session)


def test_get_funnel_metrics_empty(metrics_service: MetricsService) -> None:
    start = date.today() - timedelta(days=30)
    end = date.today()
    metrics = metrics_service.get_funnel_metrics(start, end)

    assert len(metrics) == 7
    for m in metrics:
        assert m["count"] == 0


def test_get_funnel_metrics_with_data(session: Session, metrics_service: MetricsService) -> None:
    # Setup data
    scraped_at = datetime.now(timezone.utc) - timedelta(days=5)
    job = Job(
        title="Software Engineer",
        company="Tech Corp",
        source="linkedin",
        url="http://example.com/1",
        url_hash="hash1",
        description="description",
        scraped_at=scraped_at,
        status=JobStatus.APPLIED,
        scored_at=scraped_at,
    )
    session.add(job)
    session.flush()

    app = Application(
        job_id=job.id,
        applied_at=scraped_at,
        status=ApplicationStatus.SCREENING,
    )
    session.add(app)
    session.commit()

    start = date.today() - timedelta(days=30)
    end = date.today()
    metrics = metrics_service.get_funnel_metrics(start, end)

    counts = {m["stage"]: m["count"] for m in metrics}
    assert counts["1. Ingested"] == 1
    assert counts["2. Scored"] == 1
    assert counts["3. Queued"] == 1
    assert counts["4. Applied"] == 1
    assert counts["5. Screening"] == 1
    assert counts["6. Interview"] == 0


def test_get_source_metrics(session: Session, metrics_service: MetricsService) -> None:
    scraped_at = datetime.now(timezone.utc) - timedelta(days=2)
    job1 = Job(
        title="Title 1",
        company="Co 1",
        source="linkedin",
        url="url1",
        url_hash="h1",
        description="d",
        scraped_at=scraped_at,
        tier=JobTier.A,
    )
    job2 = Job(
        title="Title 2",
        company="Co 2",
        source="indeed",
        url="url2",
        url_hash="h2",
        description="d",
        scraped_at=scraped_at,
        tier=JobTier.B,
    )
    session.add_all([job1, job2])
    session.commit()

    start = date.today() - timedelta(days=7)
    end = date.today()
    metrics = metrics_service.get_source_metrics(start, end)

    assert len(metrics) == 2
    sources = [m["source"] for m in metrics]
    assert "linkedin" in sources
    assert "indeed" in sources

    linkedin = next(m for m in metrics if m["source"] == "linkedin")
    assert linkedin["ingested"] == 1
    assert linkedin["tier_a_pct"] == 100.0


def test_get_llm_cost_metrics(session: Session, metrics_service: MetricsService) -> None:
    called_at = datetime.now(timezone.utc) - timedelta(hours=5)
    call1 = LLMCall(
        model="claude-3-opus",
        purpose=LLMPurpose.SCORING,
        cost_usd=0.05,
        called_at=called_at,
        success=True,
    )
    call2 = LLMCall(
        model="claude-3-haiku",
        purpose=LLMPurpose.COVER_LETTER,
        cost_usd=0.01,
        called_at=called_at,
        success=True,
    )
    session.add_all([call1, call2])
    session.commit()

    start = date.today() - timedelta(days=1)
    end = date.today()
    metrics = metrics_service.get_llm_cost_metrics(start, end)

    assert metrics["total_cost_usd"] == 0.06
    assert metrics["purpose_breakdown"][LLMPurpose.SCORING] == 0.05
    assert metrics["purpose_breakdown"][LLMPurpose.COVER_LETTER] == 0.01
    assert len(metrics["daily_trend"]) == 1


def test_get_system_health(session: Session, metrics_service: MetricsService) -> None:
    sh = SourceHealth(
        source_name="linkedin",
        state=SourceState.OPEN,
        failure_count=5,
        last_failure_at=datetime.now(timezone.utc),
    )
    session.add(sh)

    # Add a job to test last_ingest
    job = Job(
        title="T",
        company="C",
        source="indeed",
        url="u",
        url_hash="h",
        description="d",
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()

    health = metrics_service.get_system_health()
    assert len(health) == 2

    linkedin = next(h for h in health if h["source"] == "linkedin")
    assert linkedin["state"] == SourceState.OPEN
    assert linkedin["failures"] == 5

    indeed = next(h for h in health if h["source"] == "indeed")
    assert indeed["state"] == SourceState.CLOSED
    assert indeed["last_ingest"] is not None
