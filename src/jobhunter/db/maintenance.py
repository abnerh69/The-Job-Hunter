"""
Database maintenance tasks for Job Hunter EU.
"""

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = structlog.get_logger(__name__)


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
