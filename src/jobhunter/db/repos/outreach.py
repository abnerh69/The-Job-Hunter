import uuid
from datetime import date, datetime, timedelta
from typing import Any, Sequence

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import Session, selectinload

from jobhunter.db.enums import OutreachMarket, OutreachStatus
from jobhunter.db.models import OutreachContact
from jobhunter.db.repos.base import BaseRepo


class OutreachRepo(BaseRepo[OutreachContact]):
    """
    Repository for OutreachContact model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the OutreachRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(OutreachContact, session)

    def find_by_linkedin_url(self, url: str) -> OutreachContact | None:
        """
        Finds an outreach contact by their LinkedIn URL.

        Args:
            url (str): The LinkedIn URL of the contact.

        Returns:
            OutreachContact | None: The contact if found, None otherwise.
        """
        stmt = select(OutreachContact).where(OutreachContact.linkedin_url == url)
        return self.session.scalar(stmt)

    def list_due_for_followup(self, today: date) -> Sequence[OutreachContact]:
        """
        Lists outreach contacts due for a follow-up.
        Criteria: status='contacted' AND last_contacted_at <= today - 7 days.

        Args:
            today (date): The reference date for the follow-up check.

        Returns:
            Sequence[OutreachContact]: A sequence of contacts due for follow-up.
        """
        threshold_date = today - timedelta(days=7)
        stmt = select(OutreachContact).where(
            and_(
                OutreachContact.status == OutreachStatus.CONTACTED,
                func.date(OutreachContact.last_contacted_at) <= threshold_date,
            )
        )
        return self.session.scalars(stmt).all()

    def list_contacts(
        self,
        statuses: list[OutreachStatus] | None = None,
        markets: list[OutreachMarket] | None = None,
        stacks: list[str] | None = None,
        due_for_followup: bool = False,
        today: date | None = None,
    ) -> Sequence[OutreachContact]:
        """
        Lists outreach contacts with optional filtering.

        Args:
            statuses (list[OutreachStatus] | None): Filter by status.
            markets (list[OutreachMarket] | None): Filter by market.
            stacks (list[str] | None): Filter by specialty stack keywords.
            due_for_followup (bool): If True, only returns contacts due for follow-up.
            today (date | None): The reference date for follow-up check. Defaults to today.

        Returns:
            Sequence[OutreachContact]: A sequence of contacts matching the filters.
        """
        stmt = select(OutreachContact).options(selectinload(OutreachContact.messages))

        if statuses:
            stmt = stmt.where(OutreachContact.status.in_(statuses))

        if markets:
            stmt = stmt.where(OutreachContact.market.in_(markets))

        if stacks:
            stack_filters = [OutreachContact.specialty_stack.ilike(f"%{s}%") for s in stacks]
            stmt = stmt.where(or_(*stack_filters))

        if due_for_followup:
            ref_date = today or date.today()
            threshold_date = ref_date - timedelta(days=7)
            stmt = stmt.where(
                and_(
                    OutreachContact.status == OutreachStatus.CONTACTED,
                    func.date(OutreachContact.last_contacted_at) <= threshold_date,
                )
            )

        # Order by quality score DESC, then name
        stmt = stmt.order_by(
            OutreachContact.quality_score.desc().nulls_last(), OutreachContact.name
        )

        return self.session.scalars(stmt).all()

    def get_outreach_metrics(self, today: date | None = None) -> dict[str, int]:
        """
        Returns metrics for outreach contacts.

        Args:
            today (date | None): Reference date for follow-up. Defaults to today.

        Returns:
            dict[str, int]: Dictionary with counts by status and pending follow-ups.
        """
        ref_date = today or date.today()
        threshold_date = ref_date - timedelta(days=7)

        # Count by status
        status_stmt = select(OutreachContact.status, func.count(OutreachContact.id)).group_by(
            OutreachContact.status
        )
        status_counts: dict[str, int] = {
            str(row[0]): int(row[1]) for row in self.session.execute(status_stmt).all()
        }

        # Count pending follow-ups
        followup_stmt = select(func.count(OutreachContact.id)).where(
            and_(
                OutreachContact.status == OutreachStatus.CONTACTED,
                func.date(OutreachContact.last_contacted_at) <= threshold_date,
            )
        )
        pending_followups = self.session.scalar(followup_stmt) or 0

        metrics = {
            "total": sum(status_counts.values()),
            "pending_followups": pending_followups,
        }

        # Ensure all statuses are present in the metrics
        for status in OutreachStatus:
            metrics[f"status_{status.value}"] = status_counts.get(status, 0)

        return metrics

    def mark_contacted(self, contact_id: uuid.UUID) -> None:
        """
        Marks a contact as contacted, updating the status, timestamp and count.

        Args:
            contact_id (uuid.UUID): The ID of the contact to mark as contacted.
        """
        contact = self.get(contact_id)
        if contact:
            now = datetime.now()
            if contact.first_contacted_at is None:
                contact.first_contacted_at = now
            contact.last_contacted_at = now
            contact.contact_count += 1
            contact.status = OutreachStatus.CONTACTED
            self.session.flush()

    def process_import_batch(self, contacts_data: list[dict[str, Any]]) -> tuple[int, int, int]:
        """
        Processes a batch of parsed contacts, handles deduplication, and persists new ones.

        Args:
            contacts_data: List of normalized contact dictionaries.

        Returns:
            tuple[int, int, int]: (imported, skipped, failed)
        """
        imported = 0
        skipped = 0
        failed = 0
        seen_urls: set[str] = set()

        for data in contacts_data:
            url = data.get("linkedin_url")
            if not url:
                failed += 1
                continue

            if url in seen_urls:
                skipped += 1
                continue

            existing = self.find_by_linkedin_url(url)
            if existing:
                skipped += 1
                continue

            try:
                seen_urls.add(url)
                contact = OutreachContact(
                    name=data.get("name", "Unknown"),
                    company=data.get("company"),
                    role=data.get("role"),
                    linkedin_url=url,
                    email=data.get("email"),
                    market=data.get("market"),
                    specialty_stack=data.get("specialty_stack"),
                    quality_score=data.get("quality_score"),
                    notes=data.get("notes"),
                )
                self.session.add(contact)
                imported += 1
            except Exception as e:
                import structlog

                logger = structlog.get_logger(__name__)
                logger.error("failed_to_add_contact", url=url, error=str(e))
                failed += 1

        self.session.flush()
        return imported, skipped, failed

    def bulk_import_from_csv(self, path: str) -> tuple[int, int]:
        """
        Legacy bulk import method, now a wrapper around process_import_batch.
        Kept for backward compatibility with existing tests and dashboard.
        """
        from jobhunter.outreach.linkedin_csv import LinkedInCSVParser

        try:
            with open(path, mode="r", encoding="utf-8") as f:
                content = f.read()
                contacts_data = LinkedInCSVParser.parse(content)
                imported, skipped, _failed = self.process_import_batch(contacts_data)
                return imported, skipped
        except FileNotFoundError:
            raise IOError(f"File not found: {path}")
        except Exception as e:
            raise Exception(f"Error parsing CSV: {str(e)}")

    def list_warmest_contacts(self, limit: int = 5) -> Sequence[OutreachContact]:
        """
        Lists top warmest contacts.
        Criteria: status='warm' or status='replied', ordered by last_contacted_at DESC.

        Args:
            limit (int): Maximum number of contacts to return.

        Returns:
            Sequence[OutreachContact]: Top warmest contacts.
        """
        stmt = (
            select(OutreachContact)
            .where(OutreachContact.status.in_([OutreachStatus.WARM, OutreachStatus.REPLIED]))
            .order_by(OutreachContact.last_contacted_at.desc().nulls_last())
            .limit(limit)
        )
        return self.session.scalars(stmt).all()
