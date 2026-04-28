import csv
import uuid
from datetime import date, datetime, timedelta
from typing import Sequence

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from jobhunter.db.enums import OutreachStatus
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

    def bulk_import_from_csv(self, path: str) -> tuple[int, int]:
        """
        Bulk imports outreach contacts from a CSV file.
        Skips duplicates based on linkedin_url.

        Args:
            path (str): The path to the CSV file.

        Returns:
            tuple[int, int]: A tuple of (imported_count, skipped_duplicates_count).

        Raises:
            IOError: If the file cannot be read.
            csv.Error: If the CSV is malformed.
        """
        imported = 0
        duplicates = 0
        seen_urls: set[str] = set()

        try:
            with open(path, mode="r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    linkedin_url = row.get("linkedin_url")
                    if not linkedin_url:
                        continue

                    # Check for duplicate in this batch or DB
                    if linkedin_url in seen_urls:
                        duplicates += 1
                        continue

                    existing = self.find_by_linkedin_url(linkedin_url)
                    if existing:
                        duplicates += 1
                        continue

                    seen_urls.add(linkedin_url)
                    contact = OutreachContact(
                        name=row.get("name", "Unknown"),
                        company=row.get("company"),
                        role=row.get("role"),
                        linkedin_url=linkedin_url,
                        email=row.get("email"),
                        market=row.get("market"),
                        specialty_stack=row.get("specialty_stack"),
                        notes=row.get("notes"),
                    )

                    # Optional: handle quality_score if present in CSV
                    if row.get("quality_score"):
                        try:
                            contact.quality_score = int(row["quality_score"])
                        except ValueError:
                            pass

                    self.session.add(contact)
                    imported += 1

                self.session.flush()
        except FileNotFoundError:
            raise IOError(f"File not found: {path}")
        except Exception as e:
            # Re-raise as csv.Error if it looks like a parsing error
            if isinstance(e, csv.Error):
                raise
            raise csv.Error(f"Error parsing CSV: {str(e)}")

        return imported, duplicates
