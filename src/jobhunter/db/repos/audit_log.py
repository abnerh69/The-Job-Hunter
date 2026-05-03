import uuid
from datetime import datetime
from typing import Any, Sequence

from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from jobhunter.db.enums import AuditEventType
from jobhunter.db.models import AuditLog
from jobhunter.db.repos.base import BaseRepo


class AuditLogRepo(BaseRepo[AuditLog]):
    """
    Repository for interacting with the 'audit_log' table.
    """

    def __init__(self, session: Session):
        super().__init__(AuditLog, session)

    def record(
        self,
        event_type: AuditEventType,
        actor: str,
        action: str,
        target_entity: str | None = None,
        target_id: uuid.UUID | None = None,
        event_metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """
        Records a new audit log entry.
        """
        log_entry = AuditLog(
            event_type=event_type,
            actor=actor,
            action=action,
            target_entity=target_entity,
            target_id=target_id,
            event_metadata=event_metadata,
            ip_address=ip_address,
        )
        return self.create(log_entry)

    def query(
        self,
        event_type: AuditEventType | None = None,
        actor: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> Sequence[AuditLog]:
        """
        Queries audit logs with optional filters.
        """
        stmt = select(AuditLog)
        if event_type:
            stmt = stmt.where(AuditLog.event_type == event_type)
        if actor:
            stmt = stmt.where(AuditLog.actor == actor)
        if since:
            stmt = stmt.where(AuditLog.created_at >= since)

        stmt = stmt.order_by(desc(AuditLog.created_at)).limit(limit)
        return self.session.scalars(stmt).all()
