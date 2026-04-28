import pytest
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from jobhunter.db.models import OutreachContact
from jobhunter.db.session import get_session
from jobhunter.db.enums import OutreachMarket, OutreachStatus


def test_create_outreach_contact() -> None:
    """
    Smoke test to verify that an OutreachContact can be created and persisted.
    """
    with get_session() as session:
        new_contact = OutreachContact(
            name="John Doe",
            company="Tech Inc",
            role="Technical Recruiter",
            linkedin_url="https://www.linkedin.com/in/johndoe",
            email="john@example.com",
            market=OutreachMarket.GERMANY,
            specialty_stack="python_ai",
            quality_score=5,
            status=OutreachStatus.NEW,
            notes="Met at a conference",
        )
        session.add(new_contact)
        session.commit()

        # Query the contact back
        contact = session.query(OutreachContact).filter_by(name="John Doe").first()
        assert contact is not None
        assert contact.company == "Tech Inc"
        assert contact.role == "Technical Recruiter"
        assert contact.linkedin_url == "https://www.linkedin.com/in/johndoe"
        assert contact.market == OutreachMarket.GERMANY
        assert contact.status == OutreachStatus.NEW
        assert contact.contact_count == 0


def test_outreach_contact_unique_linkedin_url() -> None:
    """
    Verify the UNIQUE constraint on linkedin_url.
    """
    with get_session() as session:
        # Create first contact
        contact1 = OutreachContact(
            name="Alice",
            linkedin_url="https://www.linkedin.com/in/alice",
        )
        session.add(contact1)
        session.commit()

        # Attempt to create second contact with same linkedin_url
        contact2 = OutreachContact(
            name="Alice Duplicate",
            linkedin_url="https://www.linkedin.com/in/alice",
        )
        session.add(contact2)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_outreach_contact_null_linkedin_url_allowed_multiple_times() -> None:
    """
    Verify that multiple contacts can have NULL linkedin_url.
    """
    with get_session() as session:
        contact1 = OutreachContact(name="No LinkedIn 1", linkedin_url=None)
        contact2 = OutreachContact(name="No LinkedIn 2", linkedin_url=None)
        session.add(contact1)
        session.add(contact2)
        session.commit()

        # Verify both exist
        contacts = session.query(OutreachContact).filter(OutreachContact.linkedin_url.is_(None)).all()
        assert len(contacts) >= 2
        names = [c.name for c in contacts]
        assert "No LinkedIn 1" in names
        assert "No LinkedIn 2" in names


def test_outreach_contact_followup_index_and_ordering() -> None:
    """
    Verify that we can query contacts pending follow-up.
    """
    with get_session() as session:
        now = datetime.now()
        c1 = OutreachContact(
            name="Needs Followup 1",
            status=OutreachStatus.CONTACTED,
            last_contacted_at=now,
        )
        c2 = OutreachContact(
            name="Needs Followup 2",
            status=OutreachStatus.CONTACTED,
            last_contacted_at=now,
        )
        session.add_all([c1, c2])
        session.commit()

        # Query pending follow-ups
        pending = (
            session.query(OutreachContact)
            .filter(OutreachContact.status == OutreachStatus.CONTACTED)
            .order_by(OutreachContact.last_contacted_at.asc())
            .all()
        )
        assert len(pending) >= 2
        assert "Needs Followup 1" in [c.name for c in pending]
        assert "Needs Followup 2" in [c.name for c in pending]
