import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.enums import EmailMatchStatus
from jobhunter.db.models import EmailMessage
from jobhunter.db.repos.base import BaseRepo


class EmailMessageRepo(BaseRepo[EmailMessage]):
    """
    Repository for EmailMessage model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the EmailMessageRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(EmailMessage, session)

    def record(
        self,
        gmail_message_id: str,
        received_at: datetime,
        from_email: str,
        body_hash: str,
        **kwargs: Any,
    ) -> EmailMessage:
        """
        Records a new email message.

        Args:
            gmail_message_id (str): The unique ID of the message in Gmail.
            received_at (datetime): The timestamp when the email was received.
            from_email (str): The sender's email address.
            body_hash (str): SHA256 hash of the full body.
            **kwargs (Any): Additional fields for the email message.

        Returns:
            EmailMessage: The recorded email message.
        """
        # Extract domain if not provided
        if "from_domain" not in kwargs and "@" in from_email:
            kwargs["from_domain"] = from_email.split("@")[-1]

        email_msg = EmailMessage(
            gmail_message_id=gmail_message_id,
            received_at=received_at,
            from_email=from_email,
            body_hash=body_hash,
            **kwargs,
        )
        return self.create(email_msg)

    def find_by_gmail_id(self, gmail_id: str) -> EmailMessage | None:
        """
        Finds an email message by its Gmail ID.

        Args:
            gmail_id (str): The Gmail ID to search for.

        Returns:
            EmailMessage | None: The found email message or None.
        """
        stmt = select(EmailMessage).where(EmailMessage.gmail_message_id == gmail_id)
        return self.session.scalar(stmt)

    def list_unmatched(self, limit: int = 100) -> Sequence[EmailMessage]:
        """
        Lists email messages that haven't been matched yet.

        Args:
            limit (int): Maximum number of records to return.

        Returns:
            Sequence[EmailMessage]: A sequence of unmatched email messages.
        """
        stmt = (
            select(EmailMessage)
            .where(EmailMessage.match_status == EmailMatchStatus.UNMATCHED)
            .order_by(EmailMessage.received_at.desc())
            .limit(limit)
        )
        return self.session.scalars(stmt).all()

    def update_match(
        self,
        message_id: uuid.UUID,
        match_status: EmailMatchStatus,
        matched_application_id: uuid.UUID | None = None,
        matched_outreach_message_id: uuid.UUID | None = None,
        confidence: float | None = None,
        reasoning: str | None = None,
        suggestion: dict[str, Any] | None = None,
    ) -> EmailMessage | None:
        """
        Updates the match information for an email message.

        Args:
            message_id (uuid.UUID): The ID of the email message.
            match_status (EmailMatchStatus): The new match status.
            matched_application_id (uuid.UUID | None): The ID of the matched application.
            matched_outreach_message_id (uuid.UUID | None): The ID of the matched outreach message.
            confidence (float | None): Match confidence score.
            reasoning (str | None): Reasoning for the match.
            suggestion (dict[str, Any] | None): Suggested status change.

        Returns:
            EmailMessage | None: The updated email message if found.
        """
        update_fields: dict[str, Any] = {
            "match_status": match_status,
            "match_confidence": confidence,
            "match_reasoning": reasoning,
            "suggested_status_change": suggestion,
        }
        if matched_application_id:
            update_fields["matched_application_id"] = matched_application_id
        if matched_outreach_message_id:
            update_fields["matched_outreach_message_id"] = matched_outreach_message_id

        return self.update(message_id, **update_fields)

    def mark_user_confirmed(self, message_id: uuid.UUID) -> EmailMessage | None:
        """
        Marks a match as confirmed by the user.

        Args:
            message_id (uuid.UUID): The ID of the email message.

        Returns:
            EmailMessage | None: The updated email message if found.
        """
        return self.update(message_id, match_status=EmailMatchStatus.USER_CONFIRMED)

    def mark_user_rejected(self, message_id: uuid.UUID) -> EmailMessage | None:
        """
        Marks a match as rejected by the user.

        Args:
            message_id (uuid.UUID): The ID of the email message.

        Returns:
            EmailMessage | None: The updated email message if found.
        """
        return self.update(message_id, match_status=EmailMatchStatus.USER_REJECTED)
