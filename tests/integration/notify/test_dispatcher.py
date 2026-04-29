import uuid
import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.orm import Session

from jobhunter.db.enums import JobTier, JobStatus
from jobhunter.db.models import Job, NotificationSent
from jobhunter.notify.dispatcher import dispatch_tier_a_notifications
from jobhunter.notify.base import NotificationResult


@pytest.fixture
def mock_telegram_notifier():
    with patch("jobhunter.notify.dispatcher.TelegramNotifier") as mock_cls:
        notifier = mock_cls.return_value
        notifier.is_enabled.return_value = True
        notifier.send = AsyncMock()
        notifier.send.return_value = NotificationResult(
            success=True, provider_message_id="msg123", duration_ms=10
        )
        yield notifier


@pytest.fixture
def sample_jobs(session: Session):
    # Clear any existing data to avoid conflicts
    session.query(NotificationSent).delete()
    session.query(Job).delete()
    session.commit()

    # 3 Tier A jobs
    jobs = [
        Job(
            id=uuid.uuid4(),
            source="test",
            url=f"http://example.com/{i}",
            url_hash=f"hash{i}",
            title=f"Tier A Job {i}",
            company="Test Co",
            description="High match",
            tier=JobTier.A,
            status=JobStatus.SCORED,
        )
        for i in range(3)
    ]
    # 1 Tier B job (should be ignored)
    jobs.append(
        Job(
            id=uuid.uuid4(),
            source="test",
            url="http://example.com/b",
            url_hash="hashb",
            title="Tier B Job",
            company="Test Co",
            description="Medium match",
            tier=JobTier.B,
            status=JobStatus.SCORED,
        )
    )
    session.add_all(jobs)
    session.commit()
    return jobs


@pytest.mark.asyncio
async def test_dispatch_tier_a_success(session: Session, sample_jobs, mock_telegram_notifier):
    # Act
    report = await dispatch_tier_a_notifications(session)

    # Assert
    assert report.total_pending == 3
    assert report.success_count == 3
    assert report.failure_count == 0
    assert mock_telegram_notifier.send.call_count == 3

    # Verify database records
    sent_notifications = session.query(NotificationSent).all()
    assert len(sent_notifications) == 3
    for notification in sent_notifications:
        assert notification.channel == "telegram"
        assert notification.success is True
        assert notification.dedup_key.startswith("tier_a:")


@pytest.mark.asyncio
async def test_dispatch_tier_a_idempotency(session: Session, sample_jobs, mock_telegram_notifier):
    # First run
    await dispatch_tier_a_notifications(session)
    assert mock_telegram_notifier.send.call_count == 3

    # Second run
    report = await dispatch_tier_a_notifications(session)
    assert report.total_pending == 0
    assert report.success_count == 0
    assert mock_telegram_notifier.send.call_count == 3  # Still 3 from first run


@pytest.mark.asyncio
async def test_dispatch_tier_a_no_retry_on_failure(session: Session, sample_jobs, mock_telegram_notifier):
    # Make one fail
    mock_telegram_notifier.send.side_effect = [
        NotificationResult(success=False, error="Rate limited", duration_ms=10),
        NotificationResult(success=True, provider_message_id="msg2", duration_ms=10),
        NotificationResult(success=True, provider_message_id="msg3", duration_ms=10),
    ]

    # First run
    report = await dispatch_tier_a_notifications(session)
    assert report.total_pending == 3
    assert report.success_count == 2
    assert report.failure_count == 1
    assert mock_telegram_notifier.send.call_count == 3

    # Second run
    # Should be 0 pending because the failed one was already recorded in notifications_sent
    # Reset side_effect for second run to avoid StopAsyncIteration
    mock_telegram_notifier.send.side_effect = None
    mock_telegram_notifier.send.return_value = NotificationResult(
        success=True, provider_message_id="never_called", duration_ms=0
    )

    # We clear the session and its transaction to ensure a fresh start for the next call
    session.expire_all()

    report = await dispatch_tier_a_notifications(session)
    assert report.total_pending == 0
    assert report.success_count == 0
    assert mock_telegram_notifier.send.call_count == 3


@pytest.mark.asyncio
async def test_dispatch_tier_a_disabled_notifier(session: Session, sample_jobs, mock_telegram_notifier):
    # Disable notifier
    mock_telegram_notifier.is_enabled.return_value = False

    # Act
    report = await dispatch_tier_a_notifications(session)

    # Assert
    assert report.total_pending == 3
    assert report.success_count == 0
    assert report.failure_count == 0
    assert mock_telegram_notifier.send.call_count == 0

    # No database records
    assert session.query(NotificationSent).count() == 0


@pytest.mark.asyncio
async def test_dispatch_tier_a_exception_handling(session: Session, sample_jobs, mock_telegram_notifier):
    # One call raises an exception
    mock_telegram_notifier.send.side_effect = [
        NotificationResult(success=True, provider_message_id="msg1", duration_ms=10),
        Exception("Crashed!"),
        NotificationResult(success=True, provider_message_id="msg3", duration_ms=10),
    ]

    # Act
    report = await dispatch_tier_a_notifications(session)

    # Assert
    assert report.total_pending == 3
    assert report.success_count == 2
    assert report.failure_count == 1
    assert any("Crashed!" in err for err in report.errors)

    # The exception should be recorded as a failure
    failed_notif = (
        session.query(NotificationSent).filter(NotificationSent.success.is_(False)).first()
    )
    assert failed_notif is not None
    assert "Crashed!" in failed_notif.error
