from datetime import date
from typing import List

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job


class TierCount(BaseModel):
    """Counts for a specific job tier."""

    tier: JobTier
    count: int


class TierDistribution(BaseModel):
    """Distribution of jobs across tiers."""

    distribution: List[TierCount]


class SourcePerformance(BaseModel):
    """Performance metrics for a job source."""

    source: str
    ingested: int
    tier_a_pct: float
    applied: int
    response_rate: float


class FalseReject(BaseModel):
    """A job that was rejected by the system but manually promoted/applied."""

    job_id: str
    title: str
    company: str
    fit_score: int | None
    status: str


def get_tier_distribution(session: Session, start_date: date, end_date: date) -> TierDistribution:
    """
    Calculates the distribution of jobs across tiers.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        TierDistribution: The distribution of jobs across tiers.
    """
    stmt = (
        select(Job.tier, func.count(Job.id))
        .where(
            and_(
                func.date(Job.scraped_at) >= start_date,
                func.date(Job.scraped_at) <= end_date,
                Job.tier.is_not(None),
            )
        )
        .group_by(Job.tier)
    )
    rows = session.execute(stmt).all()
    return TierDistribution(distribution=[TierCount(tier=row[0], count=row[1]) for row in rows])


def get_source_performance(
    session: Session, start_date: date, end_date: date
) -> List[SourcePerformance]:
    """
    Calculates performance metrics per job source.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        List[SourcePerformance]: A list of performance metrics per source.
    """
    sources_stmt = select(Job.source).distinct()
    sources = session.scalars(sources_stmt).all()

    results = []
    for source in sources:
        # Total ingested
        ingested = (
            session.scalar(
                select(func.count(Job.id)).where(
                    and_(
                        Job.source == source,
                        func.date(Job.scraped_at) >= start_date,
                        func.date(Job.scraped_at) <= end_date,
                    )
                )
            )
            or 0
        )

        # Tier A
        tier_a = (
            session.scalar(
                select(func.count(Job.id)).where(
                    and_(
                        Job.source == source,
                        Job.tier == JobTier.A,
                        func.date(Job.scraped_at) >= start_date,
                        func.date(Job.scraped_at) <= end_date,
                    )
                )
            )
            or 0
        )

        # Applied
        applied = (
            session.scalar(
                select(func.count(Application.id))
                .join(Job)
                .where(
                    and_(
                        Job.source == source,
                        func.date(Application.applied_at) >= start_date,
                        func.date(Application.applied_at) <= end_date,
                    )
                )
            )
            or 0
        )

        # Response rate
        responded = (
            session.scalar(
                select(func.count(Application.id))
                .join(Job)
                .where(
                    and_(
                        Job.source == source,
                        Application.status.notin_(
                            [
                                ApplicationStatus.APPLIED,
                                ApplicationStatus.GHOSTED,
                                ApplicationStatus.WITHDRAWN,
                            ]
                        ),
                        func.date(Application.applied_at) >= start_date,
                        func.date(Application.applied_at) <= end_date,
                    )
                )
            )
            or 0
        )

        results.append(
            SourcePerformance(
                source=source,
                ingested=ingested,
                tier_a_pct=(tier_a / ingested * 100) if ingested > 0 else 0,
                applied=applied,
                response_rate=(responded / applied * 100) if applied > 0 else 0,
            )
        )

    return sorted(results, key=lambda x: x.ingested, reverse=True)


def get_false_rejects(session: Session, start_date: date, end_date: date) -> List[FalseReject]:
    """
    Identifies "false rejects" - jobs marked as REJECT but manually applied or queued.

    Args:
        session: SQLAlchemy session.
        start_date: Start of the period.
        end_date: End of the period.

    Returns:
        List[FalseReject]: A list of potential false rejects.
    """
    stmt = select(Job).where(
        and_(
            Job.tier == JobTier.REJECT,
            Job.status.in_([JobStatus.APPLIED, JobStatus.QUEUED, JobStatus.MANUAL_REVIEW]),
            func.date(Job.scraped_at) >= start_date,
            func.date(Job.scraped_at) <= end_date,
        )
    )
    rows = session.scalars(stmt).all()
    return [
        FalseReject(
            job_id=str(row.id),
            title=row.title,
            company=row.company,
            fit_score=row.fit_score,
            status=row.status,
        )
        for row in rows
    ]
