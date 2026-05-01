from datetime import datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics.regression_detector import check_metrics
from jobhunter.db.enums import ApplicationStatus, JobTier, OutreachMessageStatus
from jobhunter.db.models import Application, Job, NotificationSent, OutreachContact, OutreachMessage
from datetime import timedelta


def test_check_metrics_regression_tier_a(session: Session) -> None:
    """Test detection of regression in Tier A rate."""
    now = datetime.now(timezone.utc)

    # Baseline: 4 weeks ago. 10 jobs, 5 Tier A (50%)
    # current_start is now - 7 days. baseline_end is current_start.
    # baseline_start is current_start - 28 days = now - 35 days.
    # To be safe, we use now - 10 days for baseline.
    baseline_time = now - timedelta(days=10)
    for i in range(10):
        job = Job(
            title=f"Job {i}",
            company="Co",
            url=f"u{i}",
            url_hash=f"h{i}",
            source="s",
            description="d",
            scraped_at=baseline_time,
            tier=JobTier.A if i < 5 else JobTier.REJECT,
        )
        session.add(job)

    # Current: last week. 10 jobs, 1 Tier A (10%)
    current_start = now - timedelta(days=3)
    for i in range(10, 20):
        job = Job(
            title=f"Job {i}",
            company="Co",
            url=f"u{i}",
            url_hash=f"h{i}",
            source="s",
            description="d",
            scraped_at=current_start,
            tier=JobTier.A if i < 11 else JobTier.REJECT,
        )
        session.add(job)

    session.commit()

    report = check_metrics(session)
    tier_a_metric = next(m for m in report.metrics if m.name == "Tier A Rate")

    assert tier_a_metric.baseline_value == 50.0
    assert tier_a_metric.current_value == 10.0
    assert tier_a_metric.change_pct == -80.0
    assert tier_a_metric.is_regression is True


def test_check_metrics_anomaly_response_rate(session: Session) -> None:
    """Test detection of upward anomaly in Response Rate."""
    now = datetime.now(timezone.utc)

    # Baseline: 10 apps, 1 response (10%)
    baseline_time = now - timedelta(days=10)
    for i in range(10):
        job = Job(
            title="T", company="C", url=f"bu{i}", url_hash=f"bh{i}", source="s", description="d"
        )
        session.add(job)
        session.flush()
        app = Application(
            job_id=job.id,
            applied_at=baseline_time,
            status=ApplicationStatus.INTERVIEW_1 if i == 0 else ApplicationStatus.APPLIED,
        )
        session.add(app)

    # Current: 2 apps, 2 responses (100%)
    current_start = now - timedelta(days=3)
    for i in range(10, 12):
        job = Job(
            title="T", company="C", url=f"cu{i}", url_hash=f"ch{i}", source="s", description="d"
        )
        session.add(job)
        session.flush()
        app = Application(job_id=job.id, applied_at=current_start, status=ApplicationStatus.OFFER)
        session.add(app)

    session.commit()

    report = check_metrics(session)
    metric = next(m for m in report.metrics if m.name == "Response Rate")

    assert metric.baseline_value == 10.0
    assert metric.current_value == 100.0
    assert metric.change_pct == 900.0
    assert metric.is_anomaly is True


def test_check_metrics_outreach_response(session: Session) -> None:
    """Test Outreach Response Rate calculation."""
    now = datetime.now(timezone.utc)

    contact = OutreachContact(name="C")
    session.add(contact)
    session.flush()

    # Baseline: 2 sent, 0 replied
    baseline_time = now - timedelta(days=10)
    for i in range(2):
        msg = OutreachMessage(
            contact_id=contact.id,
            template_type="A",
            body="b",
            status=OutreachMessageStatus.SENT,
            sent_at=baseline_time,
        )
        session.add(msg)

    # Current: 1 sent, 1 replied
    msg = OutreachMessage(
        contact_id=contact.id,
        template_type="A",
        body="b",
        status=OutreachMessageStatus.REPLIED,
        sent_at=now - timedelta(days=2),
    )
    session.add(msg)

    session.commit()

    report = check_metrics(session)
    metric = next(m for m in report.metrics if m.name == "Outreach Response Rate")

    assert metric.baseline_value == 0.0
    assert metric.current_value == 100.0
    assert metric.is_anomaly is True


def test_pipeline_success_rate_heartbeats(session: Session) -> None:
    """Test Pipeline Success Rate using heartbeat records."""
    now = datetime.now(timezone.utc)

    # Baseline: 10 attempts, 10 success
    baseline_time = now - timedelta(days=10)
    for i in range(10):
        ns = NotificationSent(
            channel="heartbeat",
            dedup_key=f"pipeline-cycle-b-{i}",
            success=True,
            sent_at=baseline_time,
        )
        session.add(ns)

    # Current: 10 attempts, 5 success
    for i in range(10):
        ns = NotificationSent(
            channel="heartbeat",
            dedup_key=f"pipeline-cycle-c-{i}",
            success=(i < 5),
            sent_at=now - timedelta(days=2),
        )
        session.add(ns)

    session.commit()

    report = check_metrics(session)
    metric = next(m for m in report.metrics if m.name == "Pipeline Success Rate")

    assert metric.baseline_value == 100.0
    assert metric.current_value == 50.0
    assert metric.is_regression is True
