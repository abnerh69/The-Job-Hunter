import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from jobhunter.__main__ import app
from jobhunter.db.models import Job, NotificationSent
from jobhunter.db.enums import JobTier, JobStatus
from jobhunter.notify.base import NotificationResult
from datetime import datetime, timezone

runner = CliRunner()


@pytest.fixture
def mock_notifier_instance():
    mock_inst = MagicMock()
    mock_inst.is_enabled.return_value = True
    mock_inst.send = AsyncMock(return_value=NotificationResult(success=True, duration_ms=100))
    mock_inst.name = "telegram"
    return mock_inst


@pytest.mark.integration
def test_notify_dispatch_e2e(session, mock_notifier_instance):
    # Setup: Create some Tier-A jobs
    job1 = Job(
        source="test",
        url="http://test1.com",
        url_hash="hash1",
        title="Software Engineer",
        company="Tech Corp",
        description="We are hiring",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
    )
    job2 = Job(
        source="test",
        url="http://test2.com",
        url_hash="hash2",
        title="Senior Dev",
        company="Soft Inc",
        description="Python expert",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
    )
    session.add_all([job1, job2])
    session.commit()

    # 1. First dispatch: should send 2 notifications
    # We need to patch get_session in __main__ to use our test session
    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        with patch(
            "jobhunter.notify.dispatcher.TelegramNotifier", return_value=mock_notifier_instance
        ):
            result = runner.invoke(app, ["notify", "dispatch"])
            assert result.exit_code == 0
            assert "Total Pending" in result.output

            sent_count = (
                session.query(NotificationSent)
                .filter(NotificationSent.channel == "telegram")
                .count()
            )
            assert sent_count == 2

    # 2. Second dispatch: should send 0 notifications (idempotency)
    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        with patch(
            "jobhunter.notify.dispatcher.TelegramNotifier", return_value=mock_notifier_instance
        ):
            result = runner.invoke(app, ["notify", "dispatch"])
            assert result.exit_code == 0
            sent_count = (
                session.query(NotificationSent)
                .filter(NotificationSent.channel == "telegram")
                .count()
            )
            assert sent_count == 2  # Still 2


@pytest.mark.integration
def test_notify_digest_preview_vs_send(session):
    # Mocking EmailNotifier
    with patch("jobhunter.notify.digest.EmailNotifier") as mock_email_cls:
        mock_email = mock_email_cls.return_value
        mock_email.send = AsyncMock(return_value=NotificationResult(success=True, duration_ms=50))
        mock_email.is_enabled.return_value = True

        # Preview
        with patch("jobhunter.__main__.get_session") as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = session
            result = runner.invoke(app, ["notify", "digest"])
            assert result.exit_code == 0
            assert "Subject: Weekly Job Hunt Summary" in result.output
            assert "NOTE: Use --send to actually deliver the email." in result.output
            mock_email.send.assert_not_called()

            # Send
            result = runner.invoke(app, ["notify", "digest", "--send"])
            assert result.exit_code == 0
            assert "Successfully sent weekly digest" in result.output
            mock_email.send.assert_called_once()


@pytest.mark.integration
def test_notify_status(session, mock_notifier_instance):
    # Trigger some notifications to have data in status
    n1 = NotificationSent(
        channel="telegram", dedup_key="test1", success=True, sent_at=datetime.now(timezone.utc)
    )
    n2 = NotificationSent(
        channel="email",
        dedup_key="test2",
        success=False,
        error="SMTP Error",
        sent_at=datetime.now(timezone.utc),
    )
    session.add_all([n1, n2])
    session.commit()

    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        result = runner.invoke(app, ["notify", "status"])
        assert result.exit_code == 0
        assert "Notification Channels Status" in result.output
        assert "Recent Notification Attempts" in result.output
        assert "telegram" in result.output
        assert "email" in result.output
        assert "FAILED" in result.output
        # Check for failures breakdown
        assert "Count" in result.output
        assert "email" in result.output


@pytest.mark.integration
def test_notify_test_command(mock_notifier_instance):
    with patch("jobhunter.__main__.get_notifier_cls") as mock_get_cls:
        mock_get_cls.return_value = lambda: mock_notifier_instance
        result = runner.invoke(
            app, ["notify", "test", "--channel", "telegram", "--message", "hello world"]
        )
        assert result.exit_code == 0
        assert "Successfully sent message to telegram" in result.output
        mock_notifier_instance.send.assert_called_once()
        args, _ = mock_notifier_instance.send.call_args
        assert args[0].body_text == "hello world"
