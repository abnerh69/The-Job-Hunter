import hashlib
from datetime import timedelta, datetime, timezone
import asyncio
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job, ApplicationEvent
from jobhunter.pipeline import run_followup_checks
from jobhunter.notify.base import NotificationResult


@pytest.mark.asyncio
async def test_run_followup_checks(session: Session) -> None:
    """
    Tests the run_followup_checks orchestrator.
    """
    # Setup: Create a job
    url = "https://example.com/job1"
    url_hash = hashlib.sha256(url.encode()).hexdigest()

    job = Job(
        source="manual",
        source_id="test-123",
        title="Software Engineer",
        company="Test Corp",
        url=url,
        url_hash=url_hash,
        description="A test job",
        tier=JobTier.A,
        status=JobStatus.APPLIED,
    )
    session.add(job)
    session.flush()

    # Application 1: Needs follow-up (8 days ago)
    app_followup = Application(
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(timezone.utc) - timedelta(days=8),
        status_updated_at=datetime.now(timezone.utc) - timedelta(days=8),
        cv_variant="standard",
        application_method="web",
    )
    session.add(app_followup)

    # Application 2: Ghosted (22 days ago)
    app_ghosted = Application(
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(timezone.utc) - timedelta(days=22),
        status_updated_at=datetime.now(timezone.utc) - timedelta(days=22),
        cv_variant="standard",
        application_method="web",
    )
    session.add(app_ghosted)

    # Application 3: Recent (2 days ago) - Should not be touched
    app_recent = Application(
        job_id=job.id,
        status=ApplicationStatus.APPLIED,
        applied_at=datetime.now(timezone.utc) - timedelta(days=2),
        status_updated_at=datetime.now(timezone.utc) - timedelta(days=2),
        cv_variant="standard",
        application_method="web",
    )
    session.add(app_recent)

    session.commit()

    # Mock TelegramNotifier to avoid "Unauthorized" error in CI
    with patch("jobhunter.pipeline.TelegramNotifier") as mock_notifier_cls:
        mock_notifier = MagicMock()
        mock_notifier.is_enabled.return_value = True

        # We must return a future/coroutine because it is awaited
        future: asyncio.Future[NotificationResult] = asyncio.Future()
        future.set_result(NotificationResult(success=True, duration_ms=10))
        mock_notifier.send.return_value = future

        mock_notifier_cls.return_value = mock_notifier

        # Run the checks
        report = await run_followup_checks(session)

    # Verify report
    assert report.pending_followups_count == 1
    assert report.ghosted_marked_count == 1
    assert len(report.errors) == 0
    assert report.notification_sent is True

    # Verify Application 2 was transitioned to GHOSTED
    session.expire_all()
    updated_ghosted = session.get(Application, app_ghosted.id)
    assert updated_ghosted is not None
    assert updated_ghosted.status == ApplicationStatus.GHOSTED

    # Verify Application 1 is still APPLIED
    updated_followup = session.get(Application, app_followup.id)
    assert updated_followup is not None
    assert updated_followup.status == ApplicationStatus.APPLIED

    # Verify Application 3 is still APPLIED
    updated_recent = session.get(Application, app_recent.id)
    assert updated_recent is not None
    assert updated_recent.status == ApplicationStatus.APPLIED

    # Verify an event was created for the ghosted transition
    stmt = select(ApplicationEvent).where(ApplicationEvent.application_id == app_ghosted.id)
    events = session.scalars(stmt).all()
    assert len(events) >= 1
    # Check if any event has the new status GHOSTED
    assert any(
        e.event_data is not None and str(e.event_data.get("new_status")).endswith("ghosted")
        for e in events
    )
