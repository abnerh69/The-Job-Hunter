import uuid
from typing import Generator
import pytest
from sqlalchemy import create_engine, exc
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.db.base import Base
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.notify.base import NotificationResult


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()
    yield session
    session.close()


def test_record_sent(session: Session) -> None:
    repo = NotificationsRepo(session)
    result = NotificationResult(success=True, provider_message_id="msg-123", duration_ms=100)

    notification = repo.record_sent(
        channel="telegram", dedup_key="job-1", job_id=uuid.uuid4(), result=result
    )

    assert notification.id is not None
    assert notification.channel == "telegram"
    assert notification.dedup_key == "job-1"
    assert notification.success is True
    assert notification.provider_message_id == "msg-123"


def test_was_sent(session: Session) -> None:
    repo = NotificationsRepo(session)
    channel = "email"
    key = "daily-digest-2024-01-01"

    # Not sent yet
    assert repo.was_sent(channel, key) is False

    # Record success
    repo.record_sent(
        channel=channel,
        dedup_key=key,
        job_id=None,
        result=NotificationResult(success=True, duration_ms=50),
    )
    assert repo.was_sent(channel, key) is True

    # Record failure with different key
    repo.record_sent(
        channel=channel,
        dedup_key="other-key",
        job_id=None,
        result=NotificationResult(success=False, duration_ms=50),
    )
    assert repo.was_sent(channel, "other-key") is False


def test_idempotency_constraint(session: Session) -> None:
    repo = NotificationsRepo(session)
    channel = "telegram"
    key = "unique-key"

    repo.record_sent(
        channel=channel,
        dedup_key=key,
        job_id=None,
        result=NotificationResult(success=True, duration_ms=50),
    )
    session.commit()

    # Second attempt with same channel and key should raise IntegrityError
    # because of the UNIQUE constraint on (channel, dedup_key)
    with pytest.raises(exc.IntegrityError):
        repo.record_sent(
            channel=channel,
            dedup_key=key,
            job_id=None,
            result=NotificationResult(success=True, duration_ms=50),
        )
        session.commit()


def test_failures_in_last(session: Session) -> None:
    repo = NotificationsRepo(session)

    # Successes don't count
    repo.record_sent("ch1", "k1", None, NotificationResult(success=True, duration_ms=10))
    # Failures count
    repo.record_sent(
        "ch1", "k2", None, NotificationResult(success=False, error="err", duration_ms=10)
    )
    repo.record_sent(
        "ch1", "k3", None, NotificationResult(success=False, error="err", duration_ms=10)
    )

    assert repo.failures_in_last(1) == 2
    assert repo.failures_in_last(0) == 0  # technically if it was 0 hours ago, but let's say 1
