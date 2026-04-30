from datetime import datetime, timezone
from typing import Any, Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import IntegrityError

from jobhunter.db.base import Base
from jobhunter.db.enums import EmailMatchStatus
from jobhunter.db.models import Application, EmailMessage, Job, OutreachContact, OutreachMessage
from jobhunter.db.repos.email_messages import EmailMessageRepo


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")

    # SQLite doesn't enforce CHECK constraints by default, but SQLAlchemy does for some.
    # However, for testing CHECK constraints in SQLite we need to enable them.
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: Any, connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA ignore_check_constraints=OFF")
        cursor.close()

    Base.metadata.create_all(engine)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()
    yield session
    session.close()


def test_record_email_message(session: Session) -> None:
    repo = EmailMessageRepo(session)
    now = datetime.now(timezone.utc)

    msg = repo.record(
        gmail_message_id="msg123",
        received_at=now,
        from_email="recruiter@example.com",
        body_hash="hash123",
        subject="Interview Request",
        snippet="Hi Jules, we'd like to invite you...",
    )

    assert msg.id is not None
    assert msg.gmail_message_id == "msg123"
    assert msg.from_domain == "example.com"
    assert msg.match_status == EmailMatchStatus.UNMATCHED


def test_find_by_gmail_id(session: Session) -> None:
    repo = EmailMessageRepo(session)
    now = datetime.now(timezone.utc)

    repo.record(
        gmail_message_id="unique_id", received_at=now, from_email="test@test.com", body_hash="hash"
    )

    found = repo.find_by_gmail_id("unique_id")
    assert found is not None
    assert found.gmail_message_id == "unique_id"

    not_found = repo.find_by_gmail_id("missing")
    assert not_found is None


def test_idempotency_duplicate_gmail_id(session: Session) -> None:
    repo = EmailMessageRepo(session)
    now = datetime.now(timezone.utc)

    repo.record(
        gmail_message_id="dup", received_at=now, from_email="test@test.com", body_hash="hash"
    )

    with pytest.raises(IntegrityError):
        repo.record(
            gmail_message_id="dup",
            received_at=now,
            from_email="other@test.com",
            body_hash="other_hash",
        )
        session.commit()


def test_check_constraint_only_one_match(session: Session) -> None:
    # Setup dependencies
    job = Job(
        source="test", url="test", url_hash="test", title="test", company="test", description="test"
    )
    session.add(job)
    session.flush()

    app = Application(job_id=job.id)
    session.add(app)

    contact = OutreachContact(name="test")
    session.add(contact)
    session.flush()

    outreach = OutreachMessage(contact_id=contact.id, template_type="A_inhouse", body="test")
    session.add(outreach)
    session.flush()

    now = datetime.now(timezone.utc)

    # Should fail if both are set
    with pytest.raises(IntegrityError):
        msg = EmailMessage(
            gmail_message_id="both",
            received_at=now,
            from_email="test@test.com",
            body_hash="hash",
            matched_application_id=app.id,
            matched_outreach_message_id=outreach.id,
        )
        session.add(msg)
        session.commit()


def test_list_unmatched(session: Session) -> None:
    repo = EmailMessageRepo(session)
    now = datetime.now(timezone.utc)

    repo.record("id1", now, "test@test.com", "h1")
    repo.record("id2", now, "test@test.com", "h2")

    msg3 = repo.record("id3", now, "test@test.com", "h3")
    repo.update_match(msg3.id, EmailMatchStatus.AUTO_MATCHED)

    unmatched = repo.list_unmatched()
    assert len(unmatched) == 2
    assert all(m.match_status == EmailMatchStatus.UNMATCHED for m in unmatched)


def test_update_match_and_user_confirmations(session: Session) -> None:
    repo = EmailMessageRepo(session)
    now = datetime.now(timezone.utc)

    msg = repo.record("msg1", now, "test@test.com", "h1")

    # Update match
    repo.update_match(
        msg.id, EmailMatchStatus.AI_MATCHED, confidence=0.95, reasoning="Matched by AI"
    )

    updated = repo.get(msg.id)
    assert updated is not None
    assert updated.match_status == EmailMatchStatus.AI_MATCHED
    assert updated.match_confidence == 0.95

    # User confirmed
    repo.mark_user_confirmed(msg.id)
    updated_confirmed = repo.get(msg.id)
    assert updated_confirmed is not None
    assert updated_confirmed.match_status == EmailMatchStatus.USER_CONFIRMED

    # User rejected
    repo.mark_user_rejected(msg.id)
    updated_rejected = repo.get(msg.id)
    assert updated_rejected is not None
    assert updated_rejected.match_status == EmailMatchStatus.USER_REJECTED
