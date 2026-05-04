from sqlalchemy.orm import Session
from jobhunter.db.enums import AuditEventType
from jobhunter.audit.decorator import audit_logged, set_audit_context
from jobhunter.db.repos.audit_log import AuditLogRepo


def test_audit_logged_decorator(session: Session) -> None:
    # Set context
    set_audit_context("test_actor", "1.2.3.4")

    @audit_logged(AuditEventType.DATA_MUTATION, "test_action")
    def my_mutating_function(arg1: str, secret_param: str = "hidden") -> str:
        return f"result_{arg1}"

    # Call decorated function
    result = my_mutating_function("val1", secret_param="visible_but_redacted")

    assert result == "result_val1"

    # Verify log entry
    repo = AuditLogRepo(session)
    logs = repo.query(actor="test_actor")
    assert len(logs) == 1
    log = logs[0]
    assert log.event_type == AuditEventType.DATA_MUTATION
    assert log.action == "test_action"
    assert log.ip_address == "1.2.3.4"
    if log.event_metadata:
        assert log.event_metadata["arg1"] == "val1"
        assert log.event_metadata["secret_param"] == "[REDACTED]"
