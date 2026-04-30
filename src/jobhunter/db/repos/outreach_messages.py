import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from jobhunter.db.enums import OutreachMessageStatus, OutreachStatus, OutreachTemplateType
from jobhunter.db.models import OutreachContact, OutreachMessage
from jobhunter.db.repos.base import BaseRepo


class OutreachMessageRepo(BaseRepo[OutreachMessage]):
    """
    Repository for OutreachMessage model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the OutreachMessageRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(OutreachMessage, session)

    def create_draft(
        self,
        contact_id: uuid.UUID,
        template_type: OutreachTemplateType,
        body: str,
        subject: str | None = None,
        template_version: str | None = None,
        research_notes: str | None = None,
        model_used: str | None = None,
        cost_usd: Decimal | float | None = None,
        parent_message_id: uuid.UUID | None = None,
    ) -> OutreachMessage:
        """
        Creates a new outreach message draft.

        Args:
            contact_id (uuid.UUID): The ID of the contact.
            template_type (OutreachTemplateType): The type of template used.
            body (str): The body of the message.
            subject (str | None): The subject of the message.
            template_version (str | None): The version of the template used.
            research_notes (str | None): Research notes used to generate the message.
            model_used (str | None): The LLM model used to generate the message.
            cost_usd (Decimal | float | None): The cost of the LLM call.
            parent_message_id (uuid.UUID | None): The ID of the parent message if this is a follow-up.

        Returns:
            OutreachMessage: The created message draft.

        Raises:
            ValueError: If the contact already has 2 or more sent messages without a reply.
        """
        # "Política 2 toques": maximum 2 messages per contact without response.
        stmt = select(func.count(OutreachMessage.id)).where(
            and_(
                OutreachMessage.contact_id == contact_id,
                OutreachMessage.status.in_(
                    [OutreachMessageStatus.SENT, OutreachMessageStatus.GHOSTED]
                ),
            )
        )
        sent_count = self.session.scalar(stmt) or 0

        # Check if there are any replies for this contact
        reply_stmt = select(func.count(OutreachMessage.id)).where(
            and_(
                OutreachMessage.contact_id == contact_id,
                OutreachMessage.status == OutreachMessageStatus.REPLIED,
            )
        )
        reply_count = self.session.scalar(reply_stmt) or 0

        if reply_count == 0 and sent_count >= 2:
            raise ValueError("Maximum of 2 outreach attempts reached without a reply.")

        message = OutreachMessage(
            contact_id=contact_id,
            template_type=template_type,
            template_version=template_version,
            subject=subject,
            body=body,
            research_notes=research_notes,
            model_used=model_used,
            cost_usd=cost_usd,
            status=OutreachMessageStatus.DRAFT,
            parent_message_id=parent_message_id,
        )
        self.session.add(message)
        self.session.flush()
        return message

    def mark_sent(self, message_id: uuid.UUID, sent_at: datetime | None = None) -> None:
        """
        Marks a message as sent and updates the contact status.

        Args:
            message_id (uuid.UUID): The ID of the message.
            sent_at (datetime | None): The timestamp when the message was sent.
        """
        message = self.get(message_id)
        if message:
            now = sent_at or datetime.now(timezone.utc)
            message.status = OutreachMessageStatus.SENT
            message.sent_at = now

            contact = self.session.get(OutreachContact, message.contact_id)
            if contact:
                if contact.first_contacted_at is None:
                    contact.first_contacted_at = now
                contact.last_contacted_at = now
                contact.contact_count = (contact.contact_count or 0) + 1
                contact.status = OutreachStatus.CONTACTED

            self.session.flush()

    def mark_replied(self, message_id: uuid.UUID, replied_at: datetime | None = None) -> None:
        """
        Marks a message as replied and updates the contact status.

        Args:
            message_id (uuid.UUID): The ID of the message.
            replied_at (datetime | None): The timestamp when the reply was received.
        """
        message = self.get(message_id)
        if message:
            now = replied_at or datetime.now(timezone.utc)
            message.status = OutreachMessageStatus.REPLIED
            message.replied_at = now

            contact = self.session.get(OutreachContact, message.contact_id)
            if contact:
                contact.status = OutreachStatus.REPLIED

            self.session.flush()

    def mark_ghosted(self, message_id: uuid.UUID) -> None:
        """
        Marks a message as ghosted and updates the contact status if applicable.

        Args:
            message_id (uuid.UUID): The ID of the message.
        """
        message = self.get(message_id)
        if message:
            message.status = OutreachMessageStatus.GHOSTED

            # Check if there are ANY sent messages for this contact that are not ghosted/discarded/replied
            stmt = select(OutreachMessage).where(
                and_(
                    OutreachMessage.contact_id == message.contact_id,
                    OutreachMessage.status == OutreachMessageStatus.SENT,
                    OutreachMessage.id != message_id,
                )
            )
            other_active_messages = self.session.scalars(stmt).all()

            if not other_active_messages:
                contact = self.session.get(OutreachContact, message.contact_id)
                if contact and contact.status == OutreachStatus.CONTACTED:
                    contact.status = OutreachStatus.GHOSTED

            self.session.flush()

    def list_by_contact(self, contact_id: uuid.UUID) -> Sequence[OutreachMessage]:
        """
        Lists all messages for a specific contact.

        Args:
            contact_id (uuid.UUID): The ID of the contact.

        Returns:
            Sequence[OutreachMessage]: A sequence of messages for the contact.
        """
        stmt = (
            select(OutreachMessage)
            .where(OutreachMessage.contact_id == contact_id)
            .order_by(OutreachMessage.created_at.desc())
        )
        return self.session.scalars(stmt).all()

    def list_pending_followups(
        self, today: datetime | None = None, days_threshold: int = 7
    ) -> Sequence[OutreachMessage]:
        """
        Lists messages that are sent and haven't received a reply within the threshold.
        Returns only the latest message per contact to avoid redundant follow-ups.

        Args:
            today (datetime | None): The reference timestamp.
            days_threshold (int): The number of days after which a follow-up is pending.

        Returns:
            Sequence[OutreachMessage]: A sequence of messages pending follow-up.
        """
        ref_date = today or datetime.now(timezone.utc)
        threshold_date = ref_date - timedelta(days=days_threshold)

        # First, find the latest sent message for each contact that doesn't have a reply.
        # We also need to filter out contacts who have ALREADY replied to ANY message.

        # Contacts who have replied:
        replied_contacts_stmt = select(OutreachMessage.contact_id).where(
            OutreachMessage.status == OutreachMessageStatus.REPLIED
        )

        # Subquery for the latest message per contact
        latest_msg_subq = (
            select(
                OutreachMessage.contact_id,
                func.max(OutreachMessage.sent_at).label("latest_sent_at"),
            )
            .where(
                and_(
                    OutreachMessage.status == OutreachMessageStatus.SENT,
                    OutreachMessage.contact_id.not_in(replied_contacts_stmt),
                )
            )
            .group_by(OutreachMessage.contact_id)
            .subquery()
        )

        stmt = (
            select(OutreachMessage)
            .join(
                latest_msg_subq,
                and_(
                    OutreachMessage.contact_id == latest_msg_subq.c.contact_id,
                    OutreachMessage.sent_at == latest_msg_subq.c.latest_sent_at,
                ),
            )
            .where(OutreachMessage.sent_at <= threshold_date)
        )

        return self.session.scalars(stmt).all()
