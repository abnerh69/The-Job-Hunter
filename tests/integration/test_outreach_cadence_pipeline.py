import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from jobhunter.db.enums import OutreachMessageStatus, OutreachStatus, OutreachTemplateType
from jobhunter.db.models import OutreachContact, OutreachMessage
from jobhunter.notify.base import NotificationResult
from jobhunter.pipeline import run_followup_checks


@pytest.mark.asyncio
async def test_run_followup_checks_with_outreach(session: Session) -> None:
    """
    Tests the run_followup_checks orchestrator including outreach logic.
    """
    now = datetime.now(timezone.utc)

    # 1. Outreach contact needing follow-up (8 days ago)
    c1 = OutreachContact(
        name="Due Followup",
        linkedin_url="https://linkedin.com/in/c1",
        status=OutreachStatus.CONTACTED,
    )
    session.add(c1)
    session.flush()
    m1 = OutreachMessage(
        contact_id=c1.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body 1",
        status=OutreachMessageStatus.SENT,
        sent_at=now - timedelta(days=8),
    )
    session.add(m1)

    # 2. Outreach contact ghosted (22 days ago)
    c2 = OutreachContact(
        name="Ghosted Contact",
        linkedin_url="https://linkedin.com/in/c2",
        status=OutreachStatus.CONTACTED,
    )
    session.add(c2)
    session.flush()
    m2 = OutreachMessage(
        contact_id=c2.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body 2",
        status=OutreachMessageStatus.SENT,
        sent_at=now - timedelta(days=22),
    )
    session.add(m2)

    # 3. Outreach contact recent (2 days ago)
    c3 = OutreachContact(
        name="Recent Contact",
        linkedin_url="https://linkedin.com/in/c3",
        status=OutreachStatus.CONTACTED,
    )
    session.add(c3)
    session.flush()
    m3 = OutreachMessage(
        contact_id=c3.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body 3",
        status=OutreachMessageStatus.SENT,
        sent_at=now - timedelta(days=2),
    )
    session.add(m3)

    session.commit()

    # Mock TelegramNotifier
    with patch("jobhunter.pipeline.TelegramNotifier") as mock_notifier_cls:
        mock_notifier = MagicMock()
        mock_notifier.is_enabled.return_value = True

        future: asyncio.Future[NotificationResult] = asyncio.Future()
        future.set_result(NotificationResult(success=True, duration_ms=10))
        mock_notifier.send.return_value = future

        mock_notifier_cls.return_value = mock_notifier

        # Run checks
        report = await run_followup_checks(session)

    # Verify report metrics
    assert report.pending_outreach_count == 1
    assert report.outreach_ghosted_count == 1
    assert report.notification_sent is True
    assert len(report.errors) == 0

    # Verify database state
    session.expire_all()

    # c1 still contacted, but message is still sent (follow-up is just a notification)
    # Actually mark_ghosted was called for c2's message

    c2_db = session.get(OutreachContact, c2.id)
    assert c2_db is not None
    assert c2_db.status == OutreachStatus.GHOSTED
    m2_db = session.get(OutreachMessage, m2.id)
    assert m2_db is not None
    assert m2_db.status == OutreachMessageStatus.GHOSTED

    c1_db = session.get(OutreachContact, c1.id)
    assert c1_db is not None
    assert c1_db.status == OutreachStatus.CONTACTED
    m1_db = session.get(OutreachMessage, m1.id)
    assert m1_db is not None
    assert m1_db.status == OutreachMessageStatus.SENT
