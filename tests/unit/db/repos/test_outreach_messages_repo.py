from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.base import Base
from jobhunter.db.enums import OutreachMessageStatus, OutreachStatus, OutreachTemplateType
from jobhunter.db.models import OutreachContact, OutreachMessage
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo


@pytest.fixture(autouse=True)
def setup_test_db(db_session: Session) -> None:
    """Ensures all tables are created for the test."""
    Base.metadata.create_all(bind=db_session.get_bind())


@pytest.fixture
def contact(db_session: Session) -> OutreachContact:
    """Fixture for an outreach contact."""
    contact = OutreachContact(
        name="Test Contact",
        linkedin_url="https://linkedin.com/in/test",
        status=OutreachStatus.NEW,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


@pytest.fixture
def repo(db_session: Session) -> OutreachMessageRepo:
    """Fixture for OutreachMessageRepo."""
    return OutreachMessageRepo(db_session)


def test_create_draft(repo: OutreachMessageRepo, contact: OutreachContact) -> None:
    """Tests creating a message draft."""
    draft = repo.create_draft(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Hello test body",
        subject="Test Subject",
    )

    assert draft.id is not None
    assert draft.contact_id == contact.id
    assert draft.status == OutreachMessageStatus.DRAFT
    assert draft.body == "Hello test body"
    assert draft.subject == "Test Subject"
    assert draft.template_type == OutreachTemplateType.A_INHOUSE


def test_create_draft_policy_enforcement(
    repo: OutreachMessageRepo, contact: OutreachContact
) -> None:
    """Tests "2 toques" policy enforcement in create_draft."""
    # Create and mark sent 2 messages
    m1 = repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B1")
    repo.mark_sent(m1.id)
    m2 = repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B2")
    repo.mark_sent(m2.id)

    # Third attempt should fail
    with pytest.raises(ValueError, match="Maximum of 2 outreach attempts reached"):
        repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B3")

    # If one is replied, we should be able to create more (policy is about non-response)
    # Actually the current logic says: if reply_count == 0 and sent_count >= 2: raise
    # So let's mark one as replied.
    repo.mark_replied(m1.id)
    # Now it should work
    repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B4")


def test_mark_sent(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests marking a message as sent and updating contact status."""
    draft = repo.create_draft(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body",
    )

    sent_at = datetime.now(timezone.utc)
    repo.mark_sent(draft.id, sent_at=sent_at)

    # Verify message update
    db_session.refresh(draft)
    assert draft.status == OutreachMessageStatus.SENT
    # SQLite doesn't store timezone info, so we compare without tzinfo if needed
    assert draft.sent_at is not None
    if draft.sent_at.tzinfo is None and sent_at.tzinfo is not None:
        assert draft.sent_at == sent_at.replace(tzinfo=None)
    else:
        assert draft.sent_at == sent_at

    # Verify contact update
    db_session.refresh(contact)
    assert contact.status == OutreachStatus.CONTACTED
    assert contact.first_contacted_at is not None
    assert contact.last_contacted_at is not None
    if contact.first_contacted_at.tzinfo is None and sent_at.tzinfo is not None:
        assert contact.first_contacted_at == sent_at.replace(tzinfo=None)
        assert contact.last_contacted_at == sent_at.replace(tzinfo=None)
    else:
        assert contact.first_contacted_at == sent_at
        assert contact.last_contacted_at == sent_at
    assert contact.contact_count == 1


def test_mark_replied(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests marking a message as replied and updating contact status."""
    draft = repo.create_draft(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body",
    )
    repo.mark_sent(draft.id)

    replied_at = datetime.now(timezone.utc)
    repo.mark_replied(draft.id, replied_at=replied_at)

    db_session.refresh(draft)
    assert draft.status == OutreachMessageStatus.REPLIED
    # SQLite doesn't store timezone info
    assert draft.replied_at is not None
    if draft.replied_at.tzinfo is None and replied_at.tzinfo is not None:
        assert draft.replied_at == replied_at.replace(tzinfo=None)
    else:
        assert draft.replied_at == replied_at

    db_session.refresh(contact)
    assert contact.status == OutreachStatus.REPLIED


def test_mark_ghosted(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests marking a message as ghosted."""
    draft = repo.create_draft(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body",
    )
    repo.mark_sent(draft.id)

    repo.mark_ghosted(draft.id)

    db_session.refresh(draft)
    assert draft.status == OutreachMessageStatus.GHOSTED

    db_session.refresh(contact)
    assert contact.status == OutreachStatus.GHOSTED


def test_cascade_delete(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests that deleting a contact deletes its messages."""
    repo.create_draft(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Body",
    )

    db_session.delete(contact)
    db_session.commit()

    stmt = select(OutreachMessage).where(OutreachMessage.contact_id == contact.id)
    messages = db_session.scalars(stmt).all()
    assert len(messages) == 0


def test_list_pending_followups(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests listing pending follow-ups with refined logic."""
    now = datetime.now(timezone.utc)
    old_date = now - timedelta(days=10)
    older_date = now - timedelta(days=15)
    recent_date = now - timedelta(days=2)

    # Multiple messages for same contact: only latest should be returned
    m1_old = repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B1_OLD")
    repo.mark_sent(m1_old.id, sent_at=older_date)
    db_session.commit()

    m1_latest = repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B1_LATEST")
    repo.mark_sent(m1_latest.id, sent_at=old_date)
    db_session.commit()

    # Another contact with recent message
    contact2 = OutreachContact(name="C2", linkedin_url="L2")
    db_session.add(contact2)
    db_session.commit()
    m2 = repo.create_draft(contact2.id, OutreachTemplateType.A_INHOUSE, "B2")
    repo.mark_sent(m2.id, sent_at=recent_date)
    db_session.commit()

    # Another contact with old message but already replied
    contact3 = OutreachContact(name="C3", linkedin_url="L3")
    db_session.add(contact3)
    db_session.commit()
    m3 = repo.create_draft(contact3.id, OutreachTemplateType.A_INHOUSE, "B3")
    repo.mark_sent(m3.id, sent_at=older_date)
    repo.mark_replied(m3.id)
    db_session.commit()

    pending = repo.list_pending_followups(today=now, days_threshold=7)

    assert len(pending) == 1
    assert pending[0].id == m1_latest.id


def test_list_by_contact(
    repo: OutreachMessageRepo, contact: OutreachContact, db_session: Session
) -> None:
    """Tests listing messages by contact."""
    repo.create_draft(contact.id, OutreachTemplateType.A_INHOUSE, "B1")
    # Small sleep or manual timestamp adjustment might be needed for SQLite if created_at is identical
    # But let's try just committing and seeing if it works, otherwise we'll force timestamps.
    db_session.commit()

    m2 = repo.create_draft(contact.id, OutreachTemplateType.B_BOUTIQUE, "B2")
    m2.created_at = datetime.now(timezone.utc) + timedelta(seconds=1)
    db_session.commit()

    messages = repo.list_by_contact(contact.id)
    assert len(messages) == 2
    assert messages[0].body == "B2"  # Newest first
    assert messages[1].body == "B1"
