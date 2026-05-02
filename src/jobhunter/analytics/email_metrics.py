from datetime import date, datetime, timezone
from typing import Dict, List, Any

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import EmailMatchStatus, LLMPurpose
from jobhunter.db.models import EmailMessage, LLMCall


class MatcherMetrics(BaseModel):
    """Metrics for the email matcher precision and recall."""

    total_processed: int
    auto_matched: int
    ai_matched: int
    unmatched: int
    ignored_marketing: int
    user_confirmed: int
    user_rejected: int
    precision: float
    recall: float
    match_rate: float
    ai_cost_usd: float
    top_domains: List[Dict[str, Any]]


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
    # Base query for EmailMessages in the period
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
    unmatched = counts.get(EmailMatchStatus.UNMATCHED, 0)
    ignored_marketing = counts.get(EmailMatchStatus.IGNORED_MARKETING, 0)
    user_confirmed = counts.get(EmailMatchStatus.USER_CONFIRMED, 0)
    user_rejected = counts.get(EmailMatchStatus.USER_REJECTED, 0)

    # Precision: count(user_confirmed) / (count(user_confirmed) + count(user_rejected))
    # We only count those that were actually reviewed by the user.
    reviewed_matches = user_confirmed + user_rejected
    precision = user_confirmed / reviewed_matches if reviewed_matches > 0 else 0.0

    # Match rate: (auto + ai + confirmed + rejected) / total
    # Excluding ignored_marketing from both? Or just total?
    # AC says % auto_matched, % ai_matched, % unmatched, % ignored_marketing.
    total_non_marketing = total_processed - ignored_marketing
    total_matches = auto_matched + ai_matched + user_confirmed + user_rejected
    match_rate = total_matches / total_non_marketing if total_non_marketing > 0 else 0.0

    # Recall: proportion of actual matches that were found
    # This is harder to calculate without knowing the "missed" matches.
    # For now, let's keep it as 0.0 or a placeholder.
    recall = 0.0

    # AI Cost accumulated
    start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
    cost_stmt = select(func.sum(LLMCall.cost_usd)).where(
        and_(
            LLMCall.purpose == LLMPurpose.EMAIL_MATCH,
            LLMCall.called_at >= start_dt,
            LLMCall.called_at <= end_dt,
        )
    )
    ai_cost_usd = float(session.scalar(cost_stmt) or 0.0)

    # Top domains
    domain_stmt = (
        select(EmailMessage.from_domain, func.count(EmailMessage.id))
        .where(
            and_(
                func.date(EmailMessage.processed_at) >= start_date,
                func.date(EmailMessage.processed_at) <= end_date,
            )
        )
        .group_by(EmailMessage.from_domain)
        .order_by(func.count(EmailMessage.id).desc())
        .limit(5)
    )
    domain_rows = session.execute(domain_stmt).all()
    top_domains = [{"domain": row[0], "count": row[1]} for row in domain_rows]

    return MatcherMetrics(
        total_processed=total_processed,
        auto_matched=auto_matched,
        ai_matched=ai_matched,
        unmatched=unmatched,
        ignored_marketing=ignored_marketing,
        user_confirmed=user_confirmed,
        user_rejected=user_rejected,
        precision=precision,
        recall=recall,
        match_rate=match_rate,
        ai_cost_usd=ai_cost_usd,
        top_domains=top_domains,
    )
