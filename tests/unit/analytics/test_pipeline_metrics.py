from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import pipeline_metrics
from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job


def test_get_funnel_metrics(session: Session) -> None:
    # Seed data
    job1 = Job(
        title="Software Engineer",
        company="Tech Corp",
        source="LinkedIn",
        url="http://tech.corp/job1",
        url_hash="hash1",
        description="description",
        scraped_at=datetime.now(timezone.utc),
        status=JobStatus.QUEUED,
        tier=JobTier.A,
        scored_at=datetime.now(timezone.utc),
    )
    session.add(job1)
    session.flush()

    app1 = Application(
        job_id=job1.id,
        applied_at=datetime.now(timezone.utc),
        status=ApplicationStatus.APPLIED,
    )
    session.add(app1)
    session.commit()

    today = date.today()
    result = pipeline_metrics.get_funnel_metrics(session, today, today)

    assert len(result.stages) == 7
    # Ingested, Scored, Queued, Applied
    stages_dict = {s.stage: s.count for s in result.stages}
    assert stages_dict["1. Ingested"] == 1
    assert stages_dict["2. Scored"] == 1
    assert stages_dict["3. Queued"] == 1
    assert stages_dict["4. Applied"] == 1
    assert stages_dict["5. Screening"] == 0


def test_get_weekly_trends_fallback(session: Session) -> None:
    # Seed data
    job = Job(
        title="Software Engineer",
        company="Tech Corp",
        source="LinkedIn",
        url="http://tech.corp/job",
        url_hash="hash",
        description="description",
    )
    session.add(job)
    session.flush()

    app = Application(
        job_id=job.id,
        applied_at=datetime.now(timezone.utc),
        status=ApplicationStatus.APPLIED,
    )
    session.add(app)
    session.commit()

    # On SQLite it should use fallback
    result = pipeline_metrics.get_weekly_trends(session, weeks=1)
    assert len(result) >= 1
    assert result[0].apps_sent == 1
