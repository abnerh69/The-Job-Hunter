from typing import Sequence
from sqlalchemy.orm import Session
from jobhunter.db.enums import AuditEventType
from jobhunter.db.models import AuditLog
from jobhunter.db.repos.audit_log import AuditLogRepo


def test_record_audit_log(session: Session) -> None:
    repo = AuditLogRepo(session)
    log = repo.record(
        event_type=AuditEventType.LOGIN,
        actor="test_user",
        action="login_attempt",
        ip_address="127.0.0.1",
        event_metadata={"test": "data"},
    )
    session.commit()

    assert log.id is not None
    assert log.actor == "test_user"
    assert log.event_type == AuditEventType.LOGIN
    assert log.event_metadata == {"test": "data"}


def test_query_audit_logs(session: Session) -> None:
    repo = AuditLogRepo(session)
    repo.record(AuditEventType.LOGIN, "user1", "action1")
    repo.record(AuditEventType.LOGOUT, "user1", "action2")
    repo.record(AuditEventType.LOGIN, "user2", "action3")
    session.commit()

    # Filter by event type
    login_logs: Sequence[AuditLog] = repo.query(event_type=AuditEventType.LOGIN)
    assert len(login_logs) == 2

    # Filter by actor
    user2_logs: Sequence[AuditLog] = repo.query(actor="user2")
    assert len(user2_logs) == 1
    assert user2_logs[0].action == "action3"

    # Filter by since
    logs: Sequence[AuditLog] = repo.query(limit=10)
    assert len(logs) == 3
