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
from jobhunter.db.models import Job, JobProfileScore
from jobhunter.db.repos.candidate_profile import CandidateProfileRepo
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

    # Fetch active profiles
    profile_repo = CandidateProfileRepo(session)
    active_profiles = profile_repo.list_active()
    if not active_profiles:
        logger.warning("no_active_profiles_found_skipping_scoring")
        return ScoringBatchReport()

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
                prompt_version_override = variant if variant != "default" else None

                best_tier = None
                for profile in active_profiles:
                    outcome = await scorer.score(
                        job,
                        profile=profile,
                        session=session,
                        prompt_version_override=prompt_version_override,
                    )

                    if not dry_run:
                        # Persist to job_profile_scores
                        profile_score = JobProfileScore(
                            job_id=job.id,
                            profile_id=profile.id,
                            fit_score=outcome.result.fit_score
                            if isinstance(outcome.result, ScoringResult)
                            else None,
                            tier=JobTier(outcome.result.tier.value)
                            if isinstance(outcome.result, ScoringResult)
                            else None,
                            score_data=outcome.result.model_dump(),
                            scored_at=datetime.now(timezone.utc),
                            scored_with_prompt_version=outcome.prompt_version,
                        )
                        session.add(profile_score)

                        # Logic to determine global Job state based on the best fit
                        if isinstance(outcome.result, ScoringResult):
                            current_tier = outcome.result.tier
                            if best_tier is None or _tier_priority(current_tier) > _tier_priority(
                                best_tier
                            ):
                                best_tier = current_tier

                    # Update report
                    if isinstance(outcome.result, ScoringResult):
                        tier_key = outcome.result.tier.value
                        report.tier_distribution[tier_key] = (
                            report.tier_distribution.get(tier_key, 0) + 1
                        )
                    else:
                        report.tier_distribution["INVALID"] = (
                            report.tier_distribution.get("INVALID", 0) + 1
                        )

                    report.total_cost_usd += outcome.cost_usd

                if not dry_run:
                    job.scored_at = datetime.now(timezone.utc)
                    if best_tier:
                        if best_tier in (Tier.A, Tier.B):
                            job.status = JobStatus.QUEUED
                        elif best_tier == Tier.C:
                            job.status = JobStatus.MANUAL_REVIEW
                        elif best_tier == Tier.REJECT:
                            job.status = JobStatus.REJECTED
                    else:
                        job.status = JobStatus.ARCHIVED

                report.success_count += 1

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


def _tier_priority(tier: Tier) -> int:
    """Helper to determine priority of tiers for status transition."""
    priorities = {
        Tier.A: 4,
        Tier.B: 3,
        Tier.C: 2,
        Tier.REJECT: 1,
    }
    return priorities.get(tier, 0)


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

    # Fetch active profiles
    profile_repo = CandidateProfileRepo(session)
    active_profiles = profile_repo.list_active()
    if not active_profiles:
        logger.warning("no_active_profiles_found_skipping_rescoring")
        return ScoringBatchReport()

    async def score_job_task(job: Job) -> None:
        async with semaphore:
            try:
                # Remove old scores if any
                for old_score in job.profile_scores:
                    session.delete(old_score)

                best_tier = None
                for profile in active_profiles:
                    outcome = await scorer.score(job, profile=profile, session=session)

                    # Update job
                    profile_score = JobProfileScore(
                        job_id=job.id,
                        profile_id=profile.id,
                        fit_score=outcome.result.fit_score
                        if isinstance(outcome.result, ScoringResult)
                        else None,
                        tier=JobTier(outcome.result.tier.value)
                        if isinstance(outcome.result, ScoringResult)
                        else None,
                        score_data=outcome.result.model_dump(),
                        scored_at=datetime.now(timezone.utc),
                        scored_with_prompt_version=outcome.prompt_version,
                    )
                    session.add(profile_score)

                    if isinstance(outcome.result, ScoringResult):
                        current_tier = outcome.result.tier
                        if best_tier is None or _tier_priority(current_tier) > _tier_priority(
                            best_tier
                        ):
                            best_tier = current_tier

                        tier_key = outcome.result.tier.value
                        report.tier_distribution[tier_key] = (
                            report.tier_distribution.get(tier_key, 0) + 1
                        )
                    else:
                        report.tier_distribution["INVALID"] = (
                            report.tier_distribution.get("INVALID", 0) + 1
                        )

                    report.total_cost_usd += outcome.cost_usd

                job.scored_at = datetime.now(timezone.utc)
                if best_tier:
                    if best_tier in (Tier.A, Tier.B):
                        job.status = JobStatus.QUEUED
                    elif best_tier == Tier.C:
                        job.status = JobStatus.MANUAL_REVIEW
                    elif best_tier == Tier.REJECT:
                        job.status = JobStatus.REJECTED
                else:
                    job.status = JobStatus.ARCHIVED

                report.success_count += 1

            except Exception as e:
                logger.error("rescoring_failed", job_id=str(job.id), error=str(e))
                report.failed_count += 1

    await asyncio.gather(*(score_job_task(job) for job in jobs))
    session.commit()

    report.duration_seconds = asyncio.get_event_loop().time() - start_time
    return report
