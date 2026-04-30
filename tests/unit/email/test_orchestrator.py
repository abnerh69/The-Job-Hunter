import pytest
from unittest.mock import AsyncMock, patch
from jobhunter.email.orchestrator import run_email_poll_and_suggest
from jobhunter.email.suggester import StateSuggestion, SuggestionStatus
from uuid import uuid4
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_run_email_poll_and_suggest_no_emails(session: Session) -> None:
    with patch("jobhunter.email.orchestrator.GoogleOAuthHandler") as mock_auth:
        mock_auth.return_value.list_authenticated_emails.return_value = []

        result = await run_email_poll_and_suggest(session)

        assert result["processed_accounts"] == 0
        assert result["new_emails"] == 0


@pytest.mark.asyncio
async def test_run_email_poll_and_suggest_with_emails(session: Session) -> None:
    with (
        patch("jobhunter.email.orchestrator.GoogleOAuthHandler") as mock_auth,
        patch("jobhunter.email.orchestrator.GmailClient") as mock_gmail,
        patch("jobhunter.email.orchestrator.EmailMessageRepo"),
        patch("jobhunter.email.orchestrator.suggest_state_changes") as mock_suggest,
        patch("jobhunter.email.orchestrator.TelegramNotifier") as mock_notifier,
    ):
        mock_auth.return_value.list_authenticated_emails.return_value = ["test@gmail.com"]

        # Mock _poll_and_record_emails internal behavior by making GmailClient return messages
        mock_gmail_instance = mock_gmail.return_value
        mock_gmail_instance.list_messages = AsyncMock(return_value=[])

        mock_suggest.return_value = [
            StateSuggestion(
                email_id=uuid4(),
                current_state="applied",
                suggested_state="screening",
                confidence=0.95,
                status=SuggestionStatus.AUTO_APPLIED,
            )
        ]

        mock_notifier_instance = mock_notifier.return_value
        mock_notifier_instance.process_callback_updates = AsyncMock(return_value=1)

        result = await run_email_poll_and_suggest(session)

        assert result["processed_accounts"] == 1
        assert result["suggestions"] == 1
        assert result["callbacks_processed"] == 1
