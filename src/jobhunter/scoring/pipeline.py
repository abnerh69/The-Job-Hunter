"""
Orchestration of job scoring in batches.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job
from jobhunter.scoring.errors import ScoringError
from jobhunter.scoring.schema import ScoringResult, Tier
from jobhunter.scoring.scorer import JobScorer
from jobhunter.analytics.ab_testing import select_variant

logger = structlog.get_logger(__name__)


class ScoringBatchReport(BaseModel):
    """
    Report for a scoring batch operation.
    """

    model_config = ConfigDict(extra="forbid")

    total_processed: int = 0
    success_count: int = 0
    failed_count: int = 0
    tier_distribution: Dict[str, int] = {}
    total_cost_usd: float = 0.0
    duration_seconds: float = 0.0


async def score_pending_jobs(
    session: Session,
    scorer: JobScorer,
    limit: int = 100,
    concurrency: int = 5,
    dry_run: bool = False,
) -> ScoringBatchReport:
    """
    Scores jobs in 'new' status.

    Args:
        session: The SQLAlchemy session.
        scorer: The JobScorer instance to use.
        limit: Maximum number of jobs to process.
        concurrency: Maximum number of concurrent scoring operations.
        dry_run: If True, do not persist changes to the database.

    Returns:
        A ScoringBatchReport summarizing the results.
    """
    start_time = asyncio.get_event_loop().time()

    # Fetch pending jobs
    stmt = (
        select(Job).where(Job.status == JobStatus.NEW).order_by(Job.scraped_at.asc()).limit(limit)
    )
    jobs = session.scalars(stmt).all()

    if not jobs:
        return ScoringBatchReport()

    report = ScoringBatchReport()
    report.total_processed = len(jobs)

    semaphore = asyncio.Semaphore(concurrency)

    async def score_job_task(job: Job) -> None:
        async with semaphore:
            try:
                # A/B test logic: select prompt version
                variant = select_variant(session, "scoring_prompt", job.id)
                # If variant is not 'default', override the scorer's prompt version
                # This allows the test to control which prompt version is used for each job

                # Note: We need a way to pass the variant to the scorer without changing its state
                # for other concurrent tasks.
                # Let's adjust scorer.score to accept an optional prompt_version override.

                # We still pass session to scorer.score to track LLM cost and check budget
                outcome = await scorer.score(
                    job,
                    session=session,
                    prompt_version_override=variant if variant != "default" else None,
                )

                if not dry_run:
                    # Apply changes to job
                    job.scored_at = datetime.now(timezone.utc)
                    job.score_model = outcome.model
                    job.score_version = outcome.prompt_version
                    job.score_data = outcome.result.model_dump()

                    if isinstance(outcome.result, ScoringResult):
                        job.fit_score = outcome.result.fit_score
                        job.tier = JobTier(outcome.result.tier.value)

                        # State transition logic
                        if outcome.result.tier in (Tier.A, Tier.B):
                            job.status = JobStatus.QUEUED
                        elif outcome.result.tier == Tier.C:
                            job.status = JobStatus.MANUAL_REVIEW
                        elif outcome.result.tier == Tier.REJECT:
                            job.status = JobStatus.REJECTED
                    else:
                        # InvalidScoringResponse
                        job.status = JobStatus.ARCHIVED

                # Update report regardless of dry_run
                if isinstance(outcome.result, ScoringResult):
                    tier_key = outcome.result.tier.value
                    report.tier_distribution[tier_key] = (
                        report.tier_distribution.get(tier_key, 0) + 1
                    )
                else:
                    report.tier_distribution["INVALID"] = (
                        report.tier_distribution.get("INVALID", 0) + 1
                    )

                report.success_count += 1
                report.total_cost_usd += outcome.cost_usd

            except ScoringError as e:
                logger.error("job_scoring_failed", job_id=str(job.id), error=str(e))
                report.failed_count += 1
            except Exception as e:
                logger.exception(
                    "unexpected_error_during_scoring", job_id=str(job.id), error=str(e)
                )
                report.failed_count += 1

    # Run tasks in parallel
    await asyncio.gather(*(score_job_task(job) for job in jobs))

    # Finalize session
    if not dry_run:
        session.commit()
    else:
        # Rollback any changes (including recorded LLM calls for this session)
        session.rollback()

    report.duration_seconds = asyncio.get_event_loop().time() - start_time
    return report


async def rescore_jobs(
    session: Session,
    scorer: JobScorer,
    filters: Dict[str, Any],
    limit: int = 100,
    concurrency: int = 5,
) -> ScoringBatchReport:
    """
    Re-scores jobs based on filters.

    Args:
        session: The SQLAlchemy session.
        scorer: The JobScorer instance to use.
        filters: Dictionary of filters to apply to the job selection.
        limit: Maximum number of jobs to process.
        concurrency: Maximum number of concurrent scoring operations.

    Returns:
        A ScoringBatchReport summarizing the results.
    """
    start_time = asyncio.get_event_loop().time()

    stmt = select(Job)
    for key, value in filters.items():
        stmt = stmt.where(getattr(Job, key) == value)

    stmt = stmt.limit(limit)
    jobs = session.scalars(stmt).all()

    if not jobs:
        return ScoringBatchReport()

    report = ScoringBatchReport()
    report.total_processed = len(jobs)

    semaphore = asyncio.Semaphore(concurrency)

    async def score_job_task(job: Job) -> None:
        async with semaphore:
            try:
                outcome = await scorer.score(job, session=session)

                # Update job
                job.scored_at = datetime.now(timezone.utc)
                job.score_model = outcome.model
                job.score_version = outcome.prompt_version
                job.score_data = outcome.result.model_dump()

                if isinstance(outcome.result, ScoringResult):
                    job.fit_score = outcome.result.fit_score
                    job.tier = JobTier(outcome.result.tier.value)

                    # In rescore, we also update status if it changed drastically?
                    if outcome.result.tier in (Tier.A, Tier.B):
                        job.status = JobStatus.QUEUED
                    elif outcome.result.tier == Tier.C:
                        job.status = JobStatus.MANUAL_REVIEW
                    elif outcome.result.tier == Tier.REJECT:
                        job.status = JobStatus.REJECTED

                    tier_key = outcome.result.tier.value
                    report.tier_distribution[tier_key] = (
                        report.tier_distribution.get(tier_key, 0) + 1
                    )
                else:
                    job.status = JobStatus.ARCHIVED
                    report.tier_distribution["INVALID"] = (
                        report.tier_distribution.get("INVALID", 0) + 1
                    )

                report.success_count += 1
                report.total_cost_usd += outcome.cost_usd

            except Exception as e:
                logger.error("rescoring_failed", job_id=str(job.id), error=str(e))
                report.failed_count += 1

    await asyncio.gather(*(score_job_task(job) for job in jobs))
    session.commit()

    report.duration_seconds = asyncio.get_event_loop().time() - start_time
    return report
