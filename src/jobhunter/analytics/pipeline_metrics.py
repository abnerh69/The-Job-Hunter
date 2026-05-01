from datetime import date, datetime, timedelta
from typing import List

from pydantic import BaseModel
from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobStatus
from jobhunter.db.models import Application, Job


class FunnelStage(BaseModel):
    """Represents a single stage in the recruitment funnel."""

    stage: str
    count: int


class FunnelResult(BaseModel):
    """Contains all stages of the recruitment funnel."""

    stages: List[FunnelStage]


class WeeklyTrend(BaseModel):
    """Weekly metrics for temporal trend analysis."""

    week: date
    apps_sent: int
    apps_with_response: int = 0
    interviews: int = 0
    offers: int = 0
    response_rate: float = 0.0


def get_funnel_metrics(session: Session, start_date: date, end_date: date) -> FunnelResult:
    """
    Calculates the recruitment funnel metrics for a given period.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        FunnelResult: The aggregated funnel metrics.
    """
    # Ingested: jobs scraped in period
    ingested_stmt = select(func.count(Job.id)).where(
        and_(
            func.date(Job.scraped_at) >= start_date,
            func.date(Job.scraped_at) <= end_date,
        )
    )
    ingested_count = session.scalar(ingested_stmt) or 0

    # Scored: jobs scored in period
    scored_stmt = select(func.count(Job.id)).where(
        and_(
            Job.scored_at.is_not(None),
            func.date(Job.scored_at) >= start_date,
            func.date(Job.scored_at) <= end_date,
        )
    )
    scored_count = session.scalar(scored_stmt) or 0

    # Queued: jobs that reached QUEUED status in period
    queued_stmt = select(func.count(Job.id)).where(
        and_(
            Job.status.in_([JobStatus.QUEUED, JobStatus.APPLIED, JobStatus.MANUAL_REVIEW]),
            func.date(Job.scraped_at) >= start_date,
            func.date(Job.scraped_at) <= end_date,
        )
    )
    queued_count = session.scalar(queued_stmt) or 0

    # Applied: applications created in period
    applied_stmt = select(func.count(Application.id)).where(
        and_(
            func.date(Application.applied_at) >= start_date,
            func.date(Application.applied_at) <= end_date,
        )
    )
    applied_count = session.scalar(applied_stmt) or 0

    # Screening: apps that reached screening or further
    screening_stmt = select(func.count(Application.id)).where(
        and_(
            Application.status.in_(
                [
                    ApplicationStatus.SCREENING,
                    ApplicationStatus.INTERVIEW_1,
                    ApplicationStatus.INTERVIEW_N,
                    ApplicationStatus.OFFER,
                ]
            ),
            func.date(Application.applied_at) >= start_date,
            func.date(Application.applied_at) <= end_date,
        )
    )
    screening_count = session.scalar(screening_stmt) or 0

    # Interview: apps that reached interview 1 or further
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

    # Offer: apps that reached offer
    offer_stmt = select(func.count(Application.id)).where(
        and_(
            Application.status == ApplicationStatus.OFFER,
            func.date(Application.applied_at) >= start_date,
            func.date(Application.applied_at) <= end_date,
        )
    )
    offer_count = session.scalar(offer_stmt) or 0

    return FunnelResult(
        stages=[
            FunnelStage(stage="1. Ingested", count=ingested_count),
            FunnelStage(stage="2. Scored", count=scored_count),
            FunnelStage(stage="3. Queued", count=queued_count),
            FunnelStage(stage="4. Applied", count=applied_count),
            FunnelStage(stage="5. Screening", count=screening_count),
            FunnelStage(stage="6. Interview", count=interview_count),
            FunnelStage(stage="7. Offer", count=offer_count),
        ]
    )


def get_weekly_trends(session: Session, weeks: int = 8) -> List[WeeklyTrend]:
    """
    Retrieves weekly trends from the weekly_metrics materialized view or fallback logic.

    Args:
        session: SQLAlchemy session.
        weeks: Number of weeks to retrieve.

    Returns:
        List[WeeklyTrend]: A list of weekly metrics.
    """
    is_postgres = session.bind.dialect.name == "postgresql" if session.bind else False

    if is_postgres:
        try:
            stmt_text = text(
                "SELECT * FROM weekly_metrics ORDER BY week DESC LIMIT :limit"
            ).bindparams(limit=weeks)
            rows = session.execute(stmt_text).fetchall()
            return [
                WeeklyTrend(
                    week=row.week,
                    apps_sent=row.apps_sent,
                    apps_with_response=row.apps_with_response,
                    interviews=row.interviews,
                    offers=row.offers,
                    response_rate=(row.apps_with_response / row.apps_sent * 100)
                    if row.apps_sent > 0
                    else 0.0,
                )
                for row in rows
            ]
        except Exception:
            # Fallback to calculation if view fails
            pass

    # Manual calculation (simplified)
    end_date = date.today()
    start_date = end_date - timedelta(weeks=weeks)

    if is_postgres:
        stmt_select = select(
            func.date_trunc("week", Application.applied_at).label("week"),
            func.count(Application.id).label("apps_sent"),
        ).where(func.date(Application.applied_at) >= start_date)
    else:
        # SQLite version of date_trunc to week (Monday start)
        stmt_select = select(
            func.date(Application.applied_at, "weekday 0", "-6 days").label("week"),
            func.count(Application.id).label("apps_sent"),
        ).where(func.date(Application.applied_at) >= start_date)

    stmt_select = stmt_select.group_by(text("week")).order_by(text("week DESC"))

    rows = session.execute(stmt_select).all()
    return [
        WeeklyTrend(
            week=row.week
            if isinstance(row.week, (date, datetime))
            else date.fromisoformat(row.week),
            apps_sent=row.apps_sent,
            response_rate=0.0,
        )
        for row in rows
    ]
