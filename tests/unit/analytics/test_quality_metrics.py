from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import quality_metrics
from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job


def test_get_tier_distribution(session: Session) -> None:
    job1 = Job(
        title="Job 1",
        company="Co 1",
        source="S1",
        url="url1",
        url_hash="h1",
        description="description",
        tier=JobTier.A,
        scraped_at=datetime.now(timezone.utc),
    )
    job2 = Job(
        title="Job 2",
        company="Co 2",
        source="S2",
        url="url2",
        url_hash="h2",
        description="description",
        tier=JobTier.B,
        scraped_at=datetime.now(timezone.utc),
    )
    session.add_all([job1, job2])
    session.commit()

    today = date.today()
    result = quality_metrics.get_tier_distribution(session, today, today)

    tiers = {item.tier: item.count for item in result.distribution}
    assert tiers[JobTier.A] == 1
    assert tiers[JobTier.B] == 1


def test_get_source_performance(session: Session) -> None:
    job = Job(
        title="Job",
        company="Co",
        source="LinkedIn",
        url="url",
        url_hash="h",
        description="description",
        tier=JobTier.A,
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.flush()

    app = Application(
        job_id=job.id,
        applied_at=datetime.now(timezone.utc),
        status=ApplicationStatus.SCREENING,
    )
    session.add(app)
    session.commit()

    today = date.today()
    results = quality_metrics.get_source_performance(session, today, today)

    assert len(results) == 1
    assert results[0].source == "LinkedIn"
    assert results[0].ingested == 1
    assert results[0].applied == 1
    assert results[0].response_rate == 100.0


def test_get_false_rejects(session: Session) -> None:
    job = Job(
        title="False Reject",
        company="Co",
        source="S1",
        url="url",
        url_hash="h",
        description="description",
        tier=JobTier.REJECT,
        status=JobStatus.APPLIED,
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()

    today = date.today()
    results = quality_metrics.get_false_rejects(session, today, today)
    assert len(results) == 1
    assert results[0].title == "False Reject"
