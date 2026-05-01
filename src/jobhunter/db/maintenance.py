"""
Database maintenance tasks for Job Hunter EU.
"""

import structlog
from datetime import datetime, timedelta
from sqlalchemy import delete, text
from sqlalchemy.orm import Session
from jobhunter.db.models import FailedLoginAttempt

logger = structlog.get_logger(__name__)


def purge_old_security_logs(session: Session, days: int = 30) -> int:
    """
    Deletes security logs (failed login attempts) older than specified days.

    Args:
        session (Session): The SQLAlchemy session.
        days (int): Number of days to keep logs.

    Returns:
        int: Number of deleted rows.
    """
    cutoff = datetime.now() - timedelta(days=days)
    logger.info("Purging old security logs", cutoff=cutoff.isoformat())

    stmt = delete(FailedLoginAttempt).where(FailedLoginAttempt.attempted_at < cutoff)
    result = session.execute(stmt)
    session.commit()

    # result.rowcount can be -1 or None depending on the dialect and DBAPI
    # but for DELETE on SQLite/Postgres it should be available.
    # We use getattr to satisfy mypy's strictness with Result types
    rowcount = getattr(result, "rowcount", 0)
    deleted_count = int(rowcount) if rowcount is not None else 0
    logger.info("Successfully purged old security logs", deleted_count=deleted_count)
    return deleted_count


def refresh_weekly_metrics(session: Session) -> None:
    """
    Refreshes the 'weekly_metrics' materialized view concurrently.

    Args:
        session (Session): The SQLAlchemy session to use for the execution.
    """
    if session.bind and session.bind.dialect.name != "postgresql":
        logger.info("Skipping weekly_metrics refresh on non-postgresql dialect")
        return

    logger.info("Refreshing weekly_metrics materialized view")
    try:
        session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY weekly_metrics"))
        session.commit()
        logger.info("Successfully refreshed weekly_metrics materialized view")
    except Exception as e:
        session.rollback()
        logger.error("Failed to refresh weekly_metrics materialized view", error=str(e))
        raise
