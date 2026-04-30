import structlog
from uuid import UUID
from pydantic import BaseModel
from enum import StrEnum
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import select

from jobhunter.db.enums import (
    ApplicationStatus,
    EmailMatchStatus,
    OutreachMessageStatus,
)
from jobhunter.db.models import Application, EmailMessage, OutreachMessage

logger = structlog.get_logger(__name__)


class SuggestionStatus(StrEnum):
    """Status of a state change suggestion."""

    PENDING = "pending"
    AUTO_APPLIED = "auto_applied"
    IGNORED = "ignored"


class StateSuggestion(BaseModel):
    """Represents a suggested state change for an application or outreach message."""

    email_id: UUID
    application_id: UUID | None = None
    outreach_message_id: UUID | None = None
    current_state: str
    suggested_state: str
    confidence: float
    email_snippet: str | None = None
    reasoning: str | None = None
    status: SuggestionStatus


def _is_positive_transition(current_state: str, suggested_state: str) -> bool:
    """
    Checks if a state transition is considered positive and safe for auto-application.

    Positive transitions:
    - APPLIED -> SCREENING
    - SCREENING -> INTERVIEW_1
    - SENT -> REPLIED (for outreach)
    """
    positive_map: dict[str, list[str]] = {
        ApplicationStatus.APPLIED: [ApplicationStatus.SCREENING],
        ApplicationStatus.SCREENING: [ApplicationStatus.INTERVIEW_1],
        OutreachMessageStatus.SENT: [OutreachMessageStatus.REPLIED],
    }
    return suggested_state in positive_map.get(current_state, [])


def _requires_confirmation(suggestion: StateSuggestion, match_status: EmailMatchStatus) -> bool:
    """
    Determines if a suggested state change requires human confirmation.

    Conservative policy:
    - ALWAYS require confirmation for REJECTED or OFFER.
    - Require confirmation if confidence < 0.9.
    - Require confirmation if match_status is AI_MATCHED.
    - Require confirmation if the transition is not considered 'positive'.
    """
    # Conservative policy for critical statuses
    if suggestion.suggested_state in [ApplicationStatus.REJECTED, ApplicationStatus.OFFER]:
        return True

    # Threshold check
    if suggestion.confidence < 0.9:
        return True

    # Match type check (AI matched is considered less certain than Heuristic)
    if match_status != EmailMatchStatus.AUTO_MATCHED:
        return True

    # Transition safety check
    if not _is_positive_transition(suggestion.current_state, suggestion.suggested_state):
        return True

    return False


async def suggest_state_changes(session: Session) -> list[StateSuggestion]:
    """
    Processes recently matched emails and suggests state changes.

    This function:
    1. Queries matched emails with confidence >= 0.7.
    2. Filters out already processed suggestions.
    3. Determines if changes should be auto-applied or require confirmation.
    4. Persists the results and returns the suggestions.
    """
    stmt = select(EmailMessage).where(
        EmailMessage.match_status.in_([EmailMatchStatus.AUTO_MATCHED, EmailMatchStatus.AI_MATCHED]),
        EmailMessage.match_confidence >= 0.7,
    )

    emails = session.scalars(stmt).all()
    suggestions: list[StateSuggestion] = []

    for email in emails:
        meta = email.suggested_status_change or {}
        if meta.get("suggester_processed"):
            continue

        suggested_state = meta.get("status")
        if not suggested_state:
            continue

        current_state = "unknown"
        target_obj: Any = None

        if email.matched_application_id:
            target_obj = session.get(Application, email.matched_application_id)
            if target_obj:
                current_state = target_obj.status
        elif email.matched_outreach_message_id:
            target_obj = session.get(OutreachMessage, email.matched_outreach_message_id)
            if target_obj:
                current_state = target_obj.status

        if not target_obj:
            continue

        suggestion = StateSuggestion(
            email_id=email.id,
            application_id=email.matched_application_id,
            outreach_message_id=email.matched_outreach_message_id,
            current_state=current_state,
            suggested_state=suggested_state,
            confidence=email.match_confidence or 0.0,
            email_snippet=email.snippet,
            reasoning=email.match_reasoning,
            status=SuggestionStatus.PENDING,
        )

        # Decide if we can auto-apply
        if not _requires_confirmation(suggestion, email.match_status):
            suggestion.status = SuggestionStatus.AUTO_APPLIED

            # Apply the change
            target_obj.status = suggested_state
            # Use _transition_note for auditing (picked up by ApplicationEvent listener)
            setattr(
                target_obj, "_transition_note", f"Auto-applied from email: {email.gmail_message_id}"
            )

            logger.info(
                "state_change_auto_applied",
                email_id=str(email.id),
                target_id=str(target_obj.id),
                new_status=suggested_state,
            )
        else:
            logger.info(
                "state_change_requires_confirmation",
                email_id=str(email.id),
                target_id=str(target_obj.id),
                suggested_status=suggested_state,
                confidence=suggestion.confidence,
            )

        # Persist the decision in the email message
        new_meta = dict(meta)
        new_meta["suggester_processed"] = True
        new_meta["suggestion_status"] = suggestion.status
        email.suggested_status_change = new_meta

        suggestions.append(suggestion)

    if suggestions:
        session.commit()

    return suggestions
