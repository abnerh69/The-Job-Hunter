from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.models import Application, Job
from jobhunter.db.enums import ApplicationStatus, JobStatus


import pytest

def test_weekly_metrics_materialized_view(session: Session) -> None:
    """
    Test that the weekly_metrics materialized view correctly aggregates data.
    """
    if session.bind and session.bind.dialect.name != "postgresql":
        pytest.skip("Materialized view tests only supported on PostgreSQL")
    # 1. Seed dummy data
    job = Job(
        title="Software Engineer",
        company="Tech Corp",
        url="https://example.com/job1",
        url_hash="hash1",
        source="manual",
        description="A job description",
        status=JobStatus.APPLIED,
    )
    session.add(job)
    session.flush()

    # Application 1: Last week, reached interview, has salary
    last_week = datetime.now() - timedelta(days=7)
    app1 = Application(
        job_id=job.id,
        applied_at=last_week,
        status=ApplicationStatus.INTERVIEW_1,
        salary_offered_max=100000,
    )

    # Application 2: This week, just applied
    app2 = Application(
        job_id=job.id,
        applied_at=datetime.now(),
        status=ApplicationStatus.APPLIED,
    )

    # Application 3: This week, got offer
    app3 = Application(
        job_id=job.id,
        applied_at=datetime.now(),
        status=ApplicationStatus.OFFER,
        salary_offered_max=120000,
    )

    session.add_all([app1, app2, app3])
    session.commit()

    # 2. Refresh the materialized view
    refresh_weekly_metrics(session)

    # 3. Query the view
    result = session.execute(text("SELECT * FROM weekly_metrics ORDER BY week ASC")).fetchall()

    # 4. Assert results
    # We expect 2 rows (last week and this week)
    assert len(result) >= 2

    # Check the latest week (this week)
    # The columns are: week, apps_sent, apps_with_response, interviews, offers, avg_offer_max
    this_week_row = result[-1]
    assert this_week_row.apps_sent == 2
    assert this_week_row.apps_with_response == 1  # only app3 (OFFER) counts, app2 (APPLIED) doesn't
    assert this_week_row.interviews == 1  # app3 (OFFER)
    assert this_week_row.offers == 1  # app3
    assert float(this_week_row.avg_offer_max) == 120000.0

    # Check the previous week
    last_week_row = result[-2]
    assert last_week_row.apps_sent == 1
    assert last_week_row.apps_with_response == 1  # app1 (INTERVIEW_1)
    assert last_week_row.interviews == 1  # app1
    assert last_week_row.offers == 0
    assert last_week_row.avg_offer_max is None
