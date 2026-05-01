from datetime import date

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import EmailMatchStatus
from jobhunter.db.models import EmailMessage


class MatcherMetrics(BaseModel):
    """Metrics for the email matcher precision and recall."""

    total_processed: int
    auto_matched: int
    ai_matched: int
    user_confirmed: int
    user_rejected: int
    precision: float
    recall: float


def get_matcher_metrics(session: Session, start_date: date, end_date: date) -> MatcherMetrics:
    """
    Calculates precision and recall for the email matcher.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        MatcherMetrics: The aggregated matcher metrics.
    """
    stmt = (
        select(EmailMessage.match_status, func.count(EmailMessage.id))
        .where(
            and_(
                func.date(EmailMessage.processed_at) >= start_date,
                func.date(EmailMessage.processed_at) <= end_date,
            )
        )
        .group_by(EmailMessage.match_status)
    )
    rows = session.execute(stmt).all()
    counts = {row[0]: row[1] for row in rows}

    total_processed = sum(counts.values())
    auto_matched = counts.get(EmailMatchStatus.AUTO_MATCHED, 0)
    ai_matched = counts.get(EmailMatchStatus.AI_MATCHED, 0)
    user_confirmed = counts.get(EmailMatchStatus.USER_CONFIRMED, 0)
    user_rejected = counts.get(EmailMatchStatus.USER_REJECTED, 0)

    # Precision: proportion of automated matches that were correct (confirmed)
    # Note: this is a simplification since unconfirmed matches are not necessarily wrong.
    # But if it was rejected, it was definitely wrong.
    total_automated_matches = auto_matched + ai_matched + user_confirmed + user_rejected
    precision = (
        (user_confirmed + auto_matched + ai_matched) / total_automated_matches
        if total_automated_matches > 0
        else 0.0
    )

    # Recall: proportion of actual matches that were found
    # This is harder to calculate without knowing the "missed" matches.
    # For now, let's just return a placeholder or use a different metric.
    recall = 0.0

    return MatcherMetrics(
        total_processed=total_processed,
        auto_matched=auto_matched,
        ai_matched=ai_matched,
        user_confirmed=user_confirmed,
        user_rejected=user_rejected,
        precision=precision,
        recall=recall,
    )
