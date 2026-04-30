import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import select, and_, func, text, case
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
                self.session.add(contact)

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
                self.session.add(contact)

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
                    self.session.add(contact)

            self.session.flush()

    def mark_discarded(self, message_id: uuid.UUID) -> None:
        """
        Marks a message as discarded.

        Args:
            message_id (uuid.UUID): The ID of the message.
        """
        message = self.get(message_id)
        if message:
            message.status = OutreachMessageStatus.DISCARDED
            self.session.flush()

    def update_body(self, message_id: uuid.UUID, body: str) -> None:
        """
        Updates the body of a message and marks it as edited by the user.

        Args:
            message_id (uuid.UUID): The ID of the message.
            body (str): The new body text.
        """
        message = self.get(message_id)
        if message:
            if message.body != body:
                message.body = body
                message.body_edited_by_user = True
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

    def list_due_for_followup(self, today: datetime | None = None) -> Sequence[OutreachMessage]:
        """
        Lists messages that are due for follow-up (sent 7-10 days ago).
        Only returns if the contact has exactly ONE sent message (2-touch policy).

        Args:
            today (datetime | None): The reference timestamp. Defaults to now.

        Returns:
            Sequence[OutreachMessage]: A sequence of messages due for follow-up.
        """
        ref_date = today or datetime.now(timezone.utc)
        start_date = ref_date - timedelta(days=10)
        end_date = ref_date - timedelta(days=7)

        # Contacts who have exactly one sent or ghosted message (to respect 2-touch policy)
        one_touch_stmt = (
            select(OutreachMessage.contact_id)
            .where(
                OutreachMessage.status.in_(
                    [OutreachMessageStatus.SENT, OutreachMessageStatus.GHOSTED]
                )
            )
            .group_by(OutreachMessage.contact_id)
            .having(func.count(OutreachMessage.id) == 1)
        )

        # Contacts who haven't replied to ANY message
        replied_contacts_stmt = select(OutreachMessage.contact_id).where(
            OutreachMessage.status == OutreachMessageStatus.REPLIED
        )

        stmt = select(OutreachMessage).where(
            and_(
                OutreachMessage.status == OutreachMessageStatus.SENT,
                func.date(OutreachMessage.sent_at) >= start_date.date(),
                func.date(OutreachMessage.sent_at) <= end_date.date(),
                OutreachMessage.contact_id.in_(one_touch_stmt),
                OutreachMessage.contact_id.not_in(replied_contacts_stmt),
            )
        )
        return self.session.scalars(stmt).all()

    def list_ghosted_messages(self, today: datetime | None = None) -> Sequence[OutreachMessage]:
        """
        Lists messages that are sent and haven't received a reply for more than 21 days.

        Args:
            today (datetime | None): The reference timestamp. Defaults to now.

        Returns:
            Sequence[OutreachMessage]: A sequence of messages that are ghosted.
        """
        ref_date = today or datetime.now(timezone.utc)
        threshold_date = ref_date - timedelta(days=21)

        stmt = select(OutreachMessage).where(
            and_(
                OutreachMessage.status == OutreachMessageStatus.SENT,
                func.date(OutreachMessage.sent_at) < threshold_date.date(),
            )
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
            .where(func.date(OutreachMessage.sent_at) <= threshold_date.date())
        )

        return self.session.scalars(stmt).all()

    def get_stats(self, start_date: datetime) -> dict[str, Any]:
        """
        Returns detailed outreach statistics since a given start date.

        Args:
            start_date (datetime): The start date for statistics.

        Returns:
            dict[str, Any]: Dictionary with outreach stats.
        """
        # Sent messages count
        sent_stmt = select(func.count(OutreachMessage.id)).where(
            and_(
                OutreachMessage.status != OutreachMessageStatus.DRAFT,
                OutreachMessage.sent_at >= start_date,
            )
        )
        total_sent = self.session.scalar(sent_stmt) or 0

        # Replied messages count
        replied_stmt = select(func.count(OutreachMessage.id)).where(
            and_(
                OutreachMessage.status == OutreachMessageStatus.REPLIED,
                OutreachMessage.sent_at >= start_date,
            )
        )
        total_replied = self.session.scalar(replied_stmt) or 0

        # Global response rate
        response_rate = (total_replied / total_sent) if total_sent > 0 else 0.0

        # Breakdown by template_type
        # SQLAlchemy doesn't support the count(case...) easily with labels in all dialects,
        # so let's do it with a list comprehension and more explicit counting.
        template_rows = self.session.execute(
            select(
                OutreachMessage.template_type,
                func.count(OutreachMessage.id).label("sent"),
                func.sum(
                    case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
                ).label("replied"),
            )
            .where(
                and_(
                    OutreachMessage.status != OutreachMessageStatus.DRAFT,
                    OutreachMessage.sent_at >= start_date,
                )
            )
            .group_by(OutreachMessage.template_type)
        ).all()

        template_stats = [
            {
                "template_type": row.template_type,
                "sent": int(row.sent),
                "replied": int(row.replied or 0),
                "rate": (float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
            }
            for row in template_rows
        ]

        # Breakdown by market
        market_rows = self.session.execute(
            select(
                OutreachContact.market,
                func.count(OutreachMessage.id).label("sent"),
                func.sum(
                    case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
                ).label("replied"),
            )
            .join(OutreachContact, OutreachMessage.contact_id == OutreachContact.id)
            .where(
                and_(
                    OutreachMessage.status != OutreachMessageStatus.DRAFT,
                    OutreachMessage.sent_at >= start_date,
                )
            )
            .group_by(OutreachContact.market)
        ).all()

        market_stats = [
            {
                "market": row.market,
                "sent": int(row.sent),
                "replied": int(row.replied or 0),
                "rate": (float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
            }
            for row in market_rows
        ]

        # Breakdown by quality_score (binned: 1-2, 3-4, 5)
        quality_score_case = case(
            (OutreachContact.quality_score >= 5, "5"),
            (OutreachContact.quality_score >= 3, "3-4"),
            else_="1-2",
        ).label("score_bin")

        quality_rows = self.session.execute(
            select(
                quality_score_case,
                func.count(OutreachMessage.id).label("sent"),
                func.sum(
                    case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
                ).label("replied"),
            )
            .join(OutreachContact, OutreachMessage.contact_id == OutreachContact.id)
            .where(
                and_(
                    OutreachMessage.status != OutreachMessageStatus.DRAFT,
                    OutreachMessage.sent_at >= start_date,
                )
            )
            .group_by(text("score_bin"))
        ).all()

        quality_stats = [
            {
                "score_bin": row.score_bin,
                "sent": int(row.sent),
                "replied": int(row.replied or 0),
                "rate": (float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
            }
            for row in quality_rows
        ]

        # Mean response time (seconds)
        response_time_stmt = select(
            func.avg(
                func.julianday(OutreachMessage.replied_at) - func.julianday(OutreachMessage.sent_at)
            )
            * 86400
        ).where(
            and_(
                OutreachMessage.status == OutreachMessageStatus.REPLIED,
                OutreachMessage.sent_at >= start_date,
            )
        )

        if self.session.bind and self.session.bind.dialect.name == "postgresql":
            response_time_stmt = select(
                func.avg(
                    func.extract("epoch", OutreachMessage.replied_at)
                    - func.extract("epoch", OutreachMessage.sent_at)
                )
            ).where(
                and_(
                    OutreachMessage.status == OutreachMessageStatus.REPLIED,
                    OutreachMessage.sent_at >= start_date,
                )
            )

        mean_response_time = self.session.scalar(response_time_stmt)

        # Message status counts (all time or since start_date? usually all active messages)
        status_counts_rows = self.session.execute(
            select(OutreachMessage.status, func.count(OutreachMessage.id))
            .where(OutreachMessage.status != OutreachMessageStatus.DISCARDED)
            .group_by(OutreachMessage.status)
        ).all()
        status_counts = {row[0]: row[1] for row in status_counts_rows}

        return {
            "total_sent": total_sent,
            "total_replied": total_replied,
            "response_rate": response_rate,
            "template_stats": template_stats,
            "market_stats": market_stats,
            "quality_stats": quality_stats,
            "mean_response_time": float(mean_response_time or 0),
            "status_counts": status_counts,
        }
