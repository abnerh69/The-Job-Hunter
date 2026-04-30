from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from jobhunter.db.base import Base
from jobhunter.db.enums import OutreachStatus, OutreachTemplateType
from jobhunter.db.models import OutreachContact
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo


@pytest.fixture(autouse=True)
def setup_test_db(db_session: Session) -> None:
    """Ensures all tables are created for the test."""
    Base.metadata.create_all(bind=db_session.get_bind())


@pytest.fixture
def repo(db_session: Session) -> OutreachMessageRepo:
    """Fixture for OutreachMessageRepo."""
    return OutreachMessageRepo(db_session)


def create_contact(db_session: Session, name: str) -> OutreachContact:
    """Helper to create a contact."""
    contact = OutreachContact(
        name=name,
        linkedin_url=f"https://linkedin.com/in/{name.replace(' ', '').lower()}",
        status=OutreachStatus.NEW,
    )
    db_session.add(contact)
    db_session.commit()
    return contact


def test_list_due_for_followup_window(repo: OutreachMessageRepo, db_session: Session) -> None:
    """Tests that list_due_for_followup respects the 7-10 days window."""
    now = datetime.now(timezone.utc)

    # 8 days ago -> Should be included
    c1 = create_contact(db_session, "Due 8d")
    m1 = repo.create_draft(c1.id, OutreachTemplateType.A_INHOUSE, "Body 1")
    repo.mark_sent(m1.id, sent_at=now - timedelta(days=8))

    # 6 days ago -> Too recent
    c2 = create_contact(db_session, "Recent 6d")
    m2 = repo.create_draft(c2.id, OutreachTemplateType.A_INHOUSE, "Body 2")
    repo.mark_sent(m2.id, sent_at=now - timedelta(days=6))

    # 11 days ago -> Too old
    c3 = create_contact(db_session, "Old 11d")
    m3 = repo.create_draft(c3.id, OutreachTemplateType.A_INHOUSE, "Body 3")
    repo.mark_sent(m3.id, sent_at=now - timedelta(days=11))

    db_session.commit()

    due = repo.list_due_for_followup(today=now)
    assert len(due) == 1
    assert due[0].contact_id == c1.id


def test_list_due_for_followup_2_touch_policy(
    repo: OutreachMessageRepo, db_session: Session
) -> None:
    """Tests that list_due_for_followup respects the 2-touch policy."""
    now = datetime.now(timezone.utc)

    # Contact with 1 message sent 8 days ago -> Should be included
    c1 = create_contact(db_session, "One Touch")
    m1 = repo.create_draft(c1.id, OutreachTemplateType.A_INHOUSE, "Body 1")
    repo.mark_sent(m1.id, sent_at=now - timedelta(days=8))

    # Contact with 2 messages sent (latest 8 days ago) -> Should NOT be included
    c2 = create_contact(db_session, "Two Touches")
    m2a = repo.create_draft(c2.id, OutreachTemplateType.A_INHOUSE, "Body 2a")
    repo.mark_sent(m2a.id, sent_at=now - timedelta(days=15))
    m2b = repo.create_draft(c2.id, OutreachTemplateType.D_FOLLOWUP, "Body 2b")
    repo.mark_sent(m2b.id, sent_at=now - timedelta(days=8))

    db_session.commit()

    due = repo.list_due_for_followup(today=now)
    assert len(due) == 1
    assert due[0].contact_id == c1.id


def test_list_ghosted_messages(repo: OutreachMessageRepo, db_session: Session) -> None:
    """Tests that list_ghosted_messages finds messages older than 21 days."""
    now = datetime.now(timezone.utc)

    # 22 days ago -> Should be ghosted
    c1 = create_contact(db_session, "Ghost 22d")
    m1 = repo.create_draft(c1.id, OutreachTemplateType.A_INHOUSE, "Body 1")
    repo.mark_sent(m1.id, sent_at=now - timedelta(days=22))

    # 20 days ago -> Not yet ghosted
    c2 = create_contact(db_session, "Active 20d")
    m2 = repo.create_draft(c2.id, OutreachTemplateType.A_INHOUSE, "Body 2")
    repo.mark_sent(m2.id, sent_at=now - timedelta(days=20))

    db_session.commit()

    ghosted = repo.list_ghosted_messages(today=now)
    assert len(ghosted) == 1
    assert ghosted[0].id == m1.id
