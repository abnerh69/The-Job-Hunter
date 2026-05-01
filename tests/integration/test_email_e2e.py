import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.orm import Session
from telegram import Update, CallbackQuery, Message

from jobhunter.db.enums import ApplicationStatus, EmailMatchStatus
from jobhunter.db.models import Application, EmailMessage, Job
from jobhunter.email.orchestrator import run_email_poll_and_suggest
from jobhunter.email.schemas import GmailMessageDetail


@pytest.mark.asyncio
async def test_email_e2e_flow(session: Session) -> None:
    # 1. Setup: Create a job and an application
    job = Job(
        source="linkedin",
        url="https://example.com/job1",
        url_hash="hash1",
        title="Software Engineer",
        company="TechCorp",
        description="We are looking for a dev.",
        status="applied",
    )
    session.add(job)
    session.flush()

    app_record = Application(
        job_id=job.id, status=ApplicationStatus.APPLIED, contact_email="recruiter@techcorp.com"
    )
    session.add(app_record)
    session.flush()
    session.commit()

    # 2. Mock Gmail and Telegram
    with (
        patch("jobhunter.email.orchestrator.GoogleOAuthHandler") as mock_auth,
        patch("jobhunter.email.orchestrator.GmailClient") as mock_gmail,
        patch("jobhunter.email.orchestrator.TelegramNotifier") as mock_notifier,
        patch("jobhunter.email.matcher.AnthropicLLMClient"),
    ):
        mock_auth.return_value.list_authenticated_emails.return_value = ["me@gmail.com"]

        # Simulate an incoming interview invite email
        msg_summary = MagicMock(spec=GmailMessageDetail)
        msg_summary.id = "msg123"
        msg_summary.subject = "Interview Invitation"
        msg_summary.thread_id = "thread123"
        msg_summary.received_at = datetime.now(timezone.utc)
        msg_summary.from_email = "recruiter@techcorp.com"
        msg_summary.snippet = "We would like to invite you for an interview..."
        msg_summary.body_text = "Dear candidate, we would like to schedule an interview for the Software Engineer position."
        msg_summary.body_html = "<p>Dear candidate, we would like to schedule an interview for the Software Engineer position.</p>"

        mock_gmail_instance = mock_gmail.return_value
        mock_gmail_instance.list_messages = AsyncMock(return_value=[msg_summary])

        mock_gmail_instance.get_message = AsyncMock(return_value=msg_summary)

        # Mock Telegram buttons and callback processing
        mock_notifier_instance = mock_notifier.return_value
        mock_notifier_instance.send_with_buttons = AsyncMock(return_value=MagicMock(success=True))
        mock_notifier_instance.is_enabled.return_value = True
        mock_notifier_instance.process_callback_updates = AsyncMock(return_value=0)

        # 3. Run the orchestrator
        report = await run_email_poll_and_suggest(session)

        assert report["new_emails"] == 1
        assert report["suggestions"] == 1

        # Verify email was recorded and matched
        email_msg = session.query(EmailMessage).filter_by(gmail_message_id="msg123").first()
        assert email_msg is not None
        assert email_msg.match_status == EmailMatchStatus.AUTO_MATCHED
        assert email_msg.matched_application_id == app_record.id
        assert email_msg.suggested_status_change is not None
        assert email_msg.suggested_status_change.get("status") == ApplicationStatus.SCREENING

        # 4. Simulate Telegram "Approve" Callback
        # Setup the callback update
        callback_query = MagicMock(spec=CallbackQuery)
        callback_query.id = "query_id"
        callback_query.data = f"approve:{email_msg.id}"

        message = MagicMock(spec=Message)
        message.message_id = 1
        message.chat_id = 12345
        message.text_markdown_v2 = "Suggestion message"
        callback_query.message = message

        update = MagicMock(spec=Update)
        update.callback_query = callback_query

        mock_notifier_instance.bot = AsyncMock()
        mock_notifier_instance.get_updates = AsyncMock(return_value=[update])

        from jobhunter.notify.telegram import TelegramNotifier

        real_notifier = TelegramNotifier()

        with patch.object(real_notifier, "_get_settings") as mock_settings:
            mock_settings.return_value = MagicMock()

            # Mock the bot methods called during handle
            bot = AsyncMock()
            await real_notifier._handle_callback(bot, update, session)

            # Verify Application status was updated
            session.refresh(app_record)
            assert app_record.status == ApplicationStatus.SCREENING

            # Verify EmailMessage status updated to confirmed
            session.refresh(email_msg)
            assert str(email_msg.match_status) == str(EmailMatchStatus.USER_CONFIRMED)


@pytest.mark.asyncio
async def test_email_marketing_exclusion(session: Session) -> None:
    # 1. Setup
    with (
        patch("jobhunter.email.orchestrator.GoogleOAuthHandler") as mock_auth,
        patch("jobhunter.email.orchestrator.GmailClient") as mock_gmail,
    ):
        mock_auth.return_value.list_authenticated_emails.return_value = ["me@gmail.com"]

        # Simulate a marketing email
        msg_summary = MagicMock(spec=GmailMessageDetail)
        msg_summary.id = "msg_mkt"
        msg_summary.subject = "Weekly Newsletter"
        msg_summary.thread_id = "thread_mkt"
        msg_summary.received_at = datetime.now(timezone.utc)
        msg_summary.from_email = "newsletter@marketing.com"
        msg_summary.snippet = "Check out our latest deals"
        msg_summary.body_text = "Unsubscribe here."
        msg_summary.body_html = "<p>Unsubscribe here.</p>"

        mock_gmail_instance = mock_gmail.return_value
        mock_gmail_instance.list_messages = AsyncMock(return_value=[msg_summary])
        mock_gmail_instance.get_message = AsyncMock(return_value=msg_summary)

        # 2. Run
        await run_email_poll_and_suggest(session)

        # Verify it was marked as marketing and no suggestion was created
        email_msg = session.query(EmailMessage).filter_by(gmail_message_id="msg_mkt").first()
        assert email_msg is not None
        assert email_msg.match_status == EmailMatchStatus.IGNORED_MARKETING
        assert email_msg.suggested_status_change is None


@pytest.mark.asyncio
async def test_email_idempotency(session: Session) -> None:
    # Record an email already
    email_msg = EmailMessage(
        gmail_message_id="msg_dup",
        received_at=datetime.now(timezone.utc),
        from_email="test@test.com",
        body_hash="hash",
        match_status=EmailMatchStatus.UNMATCHED,
    )
    session.add(email_msg)
    session.commit()

    with (
        patch("jobhunter.email.orchestrator.GoogleOAuthHandler") as mock_auth,
        patch("jobhunter.email.orchestrator.GmailClient") as mock_gmail,
    ):
        mock_auth.return_value.list_authenticated_emails.return_value = ["me@gmail.com"]

        msg_summary = MagicMock()
        msg_summary.id = "msg_dup"

        mock_gmail_instance = mock_gmail.return_value
        mock_gmail_instance.list_messages = AsyncMock(return_value=[msg_summary])

        # Run
        report = await run_email_poll_and_suggest(session)

        # Should not be processed again
        assert report["new_emails"] == 0
