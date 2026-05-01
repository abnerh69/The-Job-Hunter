from datetime import date
from typing import Dict, List

from pydantic import BaseModel
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobTier
from jobhunter.db.models import Application, Job, LLMCall


class CostTrendItem(BaseModel):
    """Daily cost trend item."""

    day: date
    cost: float


class LLMCostBreakdown(BaseModel):
    """Breakdown of LLM costs."""

    total_cost_usd: float
    purpose_breakdown: Dict[str, float]
    daily_trend: List[CostTrendItem]


class CostPerOutcome(BaseModel):
    """Cost per specific recruitment outcome."""

    outcome: str
    cost: float


def get_llm_costs(session: Session, start_date: date, end_date: date) -> LLMCostBreakdown:
    """
    Aggregates LLM cost and usage metrics.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        LLMCostBreakdown: The aggregated cost metrics.
    """
    # Total cost
    total_cost_stmt = select(func.sum(LLMCall.cost_usd)).where(
        and_(
            func.date(LLMCall.called_at) >= start_date,
            func.date(LLMCall.called_at) <= end_date,
        )
    )
    total_cost = float(session.scalar(total_cost_stmt) or 0.0)

    # Breakdown by purpose
    purpose_stmt = (
        select(LLMCall.purpose, func.sum(LLMCall.cost_usd))
        .where(
            and_(
                func.date(LLMCall.called_at) >= start_date,
                func.date(LLMCall.called_at) <= end_date,
            )
        )
        .group_by(LLMCall.purpose)
    )
    purpose_rows = session.execute(purpose_stmt).all()
    purpose_breakdown = {row[0]: float(row[1] or 0.0) for row in purpose_rows}

    # Daily trend
    daily_stmt = (
        select(func.date(LLMCall.called_at).label("day"), func.sum(LLMCall.cost_usd))
        .where(
            and_(
                func.date(LLMCall.called_at) >= start_date,
                func.date(LLMCall.called_at) <= end_date,
            )
        )
        .group_by(text("day"))
        .order_by(text("day"))
    )
    daily_rows = session.execute(daily_stmt).all()
    daily_trend = [
        CostTrendItem(
            day=row[0] if isinstance(row[0], date) else date.fromisoformat(row[0]),
            cost=float(row[1] or 0.0),
        )
        for row in daily_rows
    ]

    return LLMCostBreakdown(
        total_cost_usd=total_cost,
        purpose_breakdown=purpose_breakdown,
        daily_trend=daily_trend,
    )


def get_cost_per_outcome(
    session: Session, start_date: date, end_date: date
) -> List[CostPerOutcome]:
    """
    Calculates cost per specific recruitment outcome (e.g., cost per application, cost per tier-A).

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        List[CostPerOutcome]: A list of costs per outcome.
    """
    # Total cost in period
    total_cost_stmt = select(func.sum(LLMCall.cost_usd)).where(
        and_(
            func.date(LLMCall.called_at) >= start_date,
            func.date(LLMCall.called_at) <= end_date,
        )
    )
    total_cost = float(session.scalar(total_cost_stmt) or 0.0)

    # Outcomes in period
    tier_a_stmt = select(func.count(Job.id)).where(
        and_(
            Job.tier == JobTier.A,
            func.date(Job.scraped_at) >= start_date,
            func.date(Job.scraped_at) <= end_date,
        )
    )
    tier_a_count = session.scalar(tier_a_stmt) or 0

    applied_stmt = select(func.count(Application.id)).where(
        and_(
            func.date(Application.applied_at) >= start_date,
            func.date(Application.applied_at) <= end_date,
        )
    )
    applied_count = session.scalar(applied_stmt) or 0

    interview_stmt = select(func.count(Application.id)).where(
        and_(
            Application.status.in_(
                [
                    ApplicationStatus.INTERVIEW_1,
                    ApplicationStatus.INTERVIEW_N,
                    ApplicationStatus.OFFER,
                ]
            ),
            func.date(Application.applied_at) >= start_date,
            func.date(Application.applied_at) <= end_date,
        )
    )
    interview_count = session.scalar(interview_stmt) or 0

    results = []
    if tier_a_count > 0:
        results.append(
            CostPerOutcome(outcome="Cost per Tier-A Job", cost=total_cost / tier_a_count)
        )
    if applied_count > 0:
        results.append(
            CostPerOutcome(outcome="Cost per Application", cost=total_cost / applied_count)
        )
    if interview_count > 0:
        results.append(
            CostPerOutcome(outcome="Cost per Interview", cost=total_cost / interview_count)
        )

    return results
