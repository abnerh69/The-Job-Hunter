from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict

import structlog
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job
from jobhunter.scoring.scorer import JobScorer

logger = structlog.get_logger(__name__)


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
    original_reject_reason: Optional[str] = None
    manual_promotion_reason: Optional[str] = None


class MissedOpportunity(BaseModel):
    """A job that was rejected but is a candidate for re-scoring."""

    job_id: str
    title: str
    company: str
    red_flags: List[str]
    fit_score: int | None


class RescoreReport(BaseModel):
    """Report for a job re-scoring operation."""

    job_id: str
    title: str
    company: str
    old_tier: JobTier
    new_tier: JobTier
    improved: bool


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
            original_reject_reason=row.score_data.get("recommendation", {}).get("reason_short")
            if row.score_data
            else None,
            manual_promotion_reason=row.manually_promoted_reason,
        )
        for row in rows
    ]


def get_false_rejects_detailed(
    session: Session, limit: int = 50, days: int = 60
) -> List[FalseReject]:
    """
    Retrieves jobs marked as REJECT that were manually promoted in the last N days.

    Args:
        session: SQLAlchemy session.
        limit: Maximum number of jobs to return.
        days: Number of days to look back.

    Returns:
        List[FalseReject]: List of detailed false rejects.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(Job)
        .where(
            and_(
                Job.tier == JobTier.REJECT,
                Job.manually_promoted_at >= since,
            )
        )
        .limit(limit)
    )
    rows = session.scalars(stmt).all()
    return [
        FalseReject(
            job_id=str(row.id),
            title=row.title,
            company=row.company,
            fit_score=row.fit_score,
            status=row.status,
            original_reject_reason=row.score_data.get("recommendation", {}).get("reason_short")
            if row.score_data
            else None,
            manual_promotion_reason=row.manually_promoted_reason,
        )
        for row in rows
    ]


def get_missed_opportunities(
    session: Session, limit: int = 50, days: int = 60
) -> List[MissedOpportunity]:
    """
    Heuristic: Identifying jobs where the red flag that marked them as REJECT is now less common.
    Calculates red flag frequencies in the population (recent vs historical).

    Args:
        session: SQLAlchemy session.
        limit: Maximum number of jobs to return.
        days: Number of days to look back.

    Returns:
        List[MissedOpportunity]: Candidates for re-scoring.
    """
    now = datetime.now(timezone.utc)
    historical_since = now - timedelta(days=days)
    recent_since = now - timedelta(days=min(7, days // 2))

    def get_flag_frequencies(since_dt: datetime) -> Dict[str, float]:
        stmt = select(Job.score_data).where(
            and_(Job.tier == JobTier.REJECT, Job.scraped_at >= since_dt)
        )
        all_data = session.scalars(stmt).all()
        total_jobs = len(all_data)
        if total_jobs == 0:
            return {}

        counts: Dict[str, int] = {}
        for data in all_data:
            if data and "red_flags" in data:
                for flag in data["red_flags"]:
                    counts[flag] = counts.get(flag, 0) + 1

        return {flag: count / total_jobs for flag, count in counts.items()}

    historical_freq = get_flag_frequencies(historical_since)
    recent_freq = get_flag_frequencies(recent_since)

    # Flags that are becoming "less common" (recent frequency < historical frequency)
    declining_flags = {
        flag
        for flag, h_f in historical_freq.items()
        if recent_freq.get(flag, 0) < h_f * 0.8  # 20% drop threshold
    }

    if not declining_flags:
        # Fallback to recently rejected with high scores
        stmt = (
            select(Job)
            .where(and_(Job.tier == JobTier.REJECT, Job.scraped_at >= historical_since))
            .order_by(Job.fit_score.desc())
            .limit(limit)
        )
        rows = session.scalars(stmt).all()
    else:
        # Find jobs with declining flags
        stmt = (
            select(Job)
            .where(
                and_(
                    Job.tier == JobTier.REJECT,
                    Job.manually_promoted_at.is_(None),
                    Job.scraped_at >= historical_since,
                )
            )
            .order_by(Job.fit_score.desc())
            .limit(limit * 2)  # Get more to filter
        )
        all_rejected = session.scalars(stmt).all()
        candidates = []
        for job in all_rejected:
            job_flags = set(job.score_data.get("red_flags", []) if job.score_data else [])
            if job_flags.intersection(declining_flags):
                candidates.append(job)

        rows = candidates[:limit]

    return [
        MissedOpportunity(
            job_id=str(row.id),
            title=row.title,
            company=row.company,
            red_flags=row.score_data.get("red_flags", []) if row.score_data else [],
            fit_score=row.fit_score,
        )
        for row in rows
    ]


async def rescore_suspicious_jobs(
    session: Session, scorer: JobScorer, jobs: List[Job], confirm: bool = False
) -> List[RescoreReport]:
    """
    Re-scores a list of suspicious jobs and updates their tier if it improves.

    Args:
        session: SQLAlchemy session.
        scorer: JobScorer instance.
        jobs: List of Job models to rescore.
        confirm: If True, only reports but does not persist.

    Returns:
        List[RescoreReport]: Summary of rescoring results.
    """
    reports = []
    for job in jobs:
        old_tier = job.tier or JobTier.REJECT
        try:
            outcome = await scorer.score(job, session=session)
            new_tier = JobTier.REJECT
            if outcome.result.valid:
                from jobhunter.scoring.schema import ScoringResult

                if isinstance(outcome.result, ScoringResult):
                    new_tier = JobTier(outcome.result.tier.value)

            improved = new_tier in [JobTier.A, JobTier.B, JobTier.C] and old_tier == JobTier.REJECT

            if improved and not confirm:
                job.tier = new_tier
                job.score_data = outcome.result.model_dump()
                job.score_model = outcome.model
                job.score_version = outcome.prompt_version
                job.scored_at = datetime.now(timezone.utc)
                # If it's no longer REJECT, update status too
                if new_tier in (JobTier.A, JobTier.B):
                    job.status = JobStatus.QUEUED
                elif new_tier == JobTier.C:
                    job.status = JobStatus.MANUAL_REVIEW

            reports.append(
                RescoreReport(
                    job_id=str(job.id),
                    title=job.title,
                    company=job.company,
                    old_tier=old_tier,
                    new_tier=new_tier,
                    improved=improved,
                )
            )
        except Exception as e:
            logger.error("rescore_failed", job_id=str(job.id), error=str(e))

    if not confirm:
        session.commit()

    return reports
