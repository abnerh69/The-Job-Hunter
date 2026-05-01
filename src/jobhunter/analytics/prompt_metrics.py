from datetime import date
from typing import List

from pydantic import BaseModel
from sqlalchemy import and_, func, select, case
from sqlalchemy.orm import Session

from jobhunter.db.models import Job, LLMCall


class PromptPerformance(BaseModel):
    """Performance metrics for a specific prompt version."""

    prompt_version: str
    purpose: str
    total_calls: int
    success_rate: float
    avg_cost: float
    outcomes: dict[str, int]


def get_prompt_performance(
    session: Session, start_date: date, end_date: date
) -> List[PromptPerformance]:
    """
    Aggregates outcomes and performance metrics by prompt version.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        List[PromptPerformance]: A list of performance metrics per prompt version.
    """
    stmt = (
        select(
            LLMCall.prompt_version,
            LLMCall.purpose,
            func.count(LLMCall.id).label("total_calls"),
            func.sum(case((LLMCall.success, 1), else_=0)).label("successful_calls"),
            func.avg(LLMCall.cost_usd).label("avg_cost"),
        )
        .where(
            and_(
                func.date(LLMCall.called_at) >= start_date,
                func.date(LLMCall.called_at) <= end_date,
                LLMCall.prompt_version.is_not(None),
            )
        )
        .group_by(LLMCall.prompt_version, LLMCall.purpose)
    )

    rows = session.execute(stmt).all()
    results = []

    for row in rows:
        prompt_version = row.prompt_version
        purpose = row.purpose

        outcomes = {}
        # If purpose is scoring, we can look at tier distribution for this version
        if purpose == "scoring":
            tier_stmt = (
                select(Job.tier, func.count(Job.id))
                .where(Job.score_version == prompt_version)
                .group_by(Job.tier)
            )
            tier_rows = session.execute(tier_stmt).all()
            outcomes = {str(r[0]): int(r[1]) for r in tier_rows}

        results.append(
            PromptPerformance(
                prompt_version=prompt_version,
                purpose=purpose,
                total_calls=int(row.total_calls),
                success_rate=(float(row.successful_calls) / float(row.total_calls))
                if row.total_calls > 0
                else 0.0,
                avg_cost=float(row.avg_cost or 0.0),
                outcomes=outcomes,
            )
        )

    return results
