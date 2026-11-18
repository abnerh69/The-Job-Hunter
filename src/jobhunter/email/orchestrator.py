import hashlib
import structlog
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from typing import List, Any

from jobhunter.auth.google import GoogleOAuthHandler
from jobhunter.config import Settings
from jobhunter.db.repos.email_messages import EmailMessageRepo
from jobhunter.db.repos.oauth_tokens import OAuthTokenRepo
from jobhunter.email.gmail_client import GmailClient
from jobhunter.email.matcher import match_email
from jobhunter.llm.base import LLMClient
from jobhunter.notify.telegram import TelegramNotifier, Button
from jobhunter.email.suggester import suggest_state_changes, SuggestionStatus, StateSuggestion
from jobhunter.db.models import EmailMessage
from jobhunter.notify.templates import render

logger = structlog.get_logger(__name__)


async def _poll_and_record_emails(
    session: Session,
    gmail_client: GmailClient,
    email_repo: EmailMessageRepo,
    llm_client: LLMClient,
) -> int:
    """
    Polls Gmail for new messages and records them in the database.
    Returns the number of new messages processed.
    """
    # newer_than:1h -from:me
    query = "newer_than:1h -from:me"
    try:
        messages = await gmail_client.list_messages(query=query)
    except Exception as e:
        logger.error("failed_to_list_gmail_messages", error=str(e))
        return 0

    new_count = 0
    for msg_summary in messages:
        if email_repo.find_by_gmail_id(msg_summary.id):
            continue

        logger.info("processing_new_email", gmail_id=msg_summary.id, subject=msg_summary.subject)

        try:
            # Get full message
            email_detail = await gmail_client.get_message(msg_summary.id)

            # Hash body
            body = email_detail.body_text or email_detail.body_html or ""
            body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

            # Record email
            email_record = email_repo.record(
                gmail_message_id=email_detail.id,
                received_at=email_detail.received_at,
                from_email=email_detail.from_email,
                body_hash=body_hash,
                gmail_thread_id=email_detail.thread_id,
                subject=email_detail.subject,
                snippet=email_detail.snippet,
            )
            session.flush()  # Ensure it has an ID

            # Match email
            match_result = await match_email(email_detail, session, llm_client)

            # Update match
            email_repo.update_match(
                message_id=email_record.id,
                match_status=match_result.match_status,
                matched_application_id=match_result.application_id,
                matched_outreach_message_id=match_result.outreach_message_id,
                confidence=match_result.confidence,
                reasoning=match_result.reasoning,
                suggestion=match_result.suggested_change,
            )

            new_count += 1
        except Exception as e:
            logger.error("failed_to_process_email", gmail_id=msg_summary.id, error=str(e))
            continue

    return new_count


async def _process_suggestions_and_notify(
    session: Session,
    suggestions: List[StateSuggestion],
    notifier: TelegramNotifier,
) -> None:
    """
    Processes suggestions, applying auto-changes and notifying for pending ones.
    Implements anti-spam grouping.
    """
    pending_suggestions = [s for s in suggestions if s.status == SuggestionStatus.PENDING]

    if not pending_suggestions:
        return

    # Anti-spam check: if > 5 pending in last hour (including current ones)
    # Actually, the requirement says "Si 'tormenta' de emails (>5 sugerencias en 1 hora), agrupar en una sola notificación"
    # We can check how many were generated in the last hour.

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    # Since we just generated 'pending_suggestions', let's see if we should group them.
    # For simplicity, if this single run has > 5 suggestions, we group them.
    # OR if there were many recent ones.

    # Let's count how many EmailMessages have a pending suggestion in the last hour.
    from sqlalchemy import select, func

    recent_pending_count = (
        session.scalar(
            select(func.count(EmailMessage.id)).where(
                EmailMessage.processed_at >= one_hour_ago,
                EmailMessage.suggested_status_change["suggestion_status"].as_string()
                == SuggestionStatus.PENDING.value,
            )
        )
        or 0
    )

    if recent_pending_count > 5:
        logger.info("anti_spam_grouping_triggered", count=len(pending_suggestions))

        body = render("notifications/email_match_summary.md", {"suggestions": pending_suggestions})
        from jobhunter.notify.base import NotificationMessage

        msg = NotificationMessage(
            channel="telegram", body_text=body, metadata={"type": "email_match_summary"}
        )
        await notifier.send(msg)
    else:
        for suggestion in pending_suggestions:
            body = render("notifications/email_match_suggestion.md", {"suggestion": suggestion})
            from jobhunter.notify.base import NotificationMessage

            msg = NotificationMessage(
                channel="telegram",
                body_text=body,
                metadata={"type": "email_match_suggestion", "email_id": str(suggestion.email_id)},
            )

            buttons = [
                Button(text="✅ Approve", callback_data=f"approve:{suggestion.email_id}"),
                Button(text="❌ Reject", callback_data=f"reject:{suggestion.email_id}"),
                Button(text="ℹ️ Context", callback_data=f"context:{suggestion.email_id}"),
            ]

            await notifier.send_with_buttons(msg, buttons)


async def run_email_poll_and_suggest(session: Session) -> dict[str, Any]:
    """
    Main orchestrator for email polling, matching, and suggestions.
    """
    settings = Settings()  # type: ignore[call-arg]
    auth_handler = GoogleOAuthHandler(session, settings)
    token_repo = OAuthTokenRepo(session)
    email_repo = EmailMessageRepo(session)
    from jobhunter.llm.factory import create_llm_client

    llm_client = create_llm_client(settings)
    notifier = TelegramNotifier()

    emails = auth_handler.list_authenticated_emails()
    if not emails:
        logger.info("no_authenticated_emails_found")
        return {"processed_accounts": 0, "new_emails": 0, "suggestions": 0}

    total_new = 0
    for email in emails:
        logger.info("polling_gmail_account", email=email)
        gmail_client = GmailClient(token_repo, email, settings)
        new_count = await _poll_and_record_emails(session, gmail_client, email_repo, llm_client)
        total_new += new_count

    # Suggest changes and notify
    suggestions = await suggest_state_changes(session)
    await _process_suggestions_and_notify(session, suggestions, notifier)

    # Process callbacks
    callback_count = await notifier.process_callback_updates(session)

    return {
        "processed_accounts": len(emails),
        "new_emails": total_new,
        "suggestions": len(suggestions),
        "callbacks_processed": callback_count,
    }
