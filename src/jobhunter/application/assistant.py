"""
Orchestrator for the application assistant.

This module coordinates the different components of the application assistant:
CV variant recommendation, cover letter generation, ATS keyword extraction,
and CV tweak suggestions.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple, Optional
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.application.ats_keywords import ATSKeywordsResult, extract_ats_keywords
from jobhunter.application.cover_letter import CoverLetterResult, generate_cover_letter
from jobhunter.application.cv import load_cv
from jobhunter.application.cv_tweaks import CVTweaksResult, suggest_cv_tweaks
from jobhunter.application.variant_selector import VariantRecommendation, recommend_cv_variant
from jobhunter.config import Settings
from jobhunter.db.models import Application, Job
from jobhunter.llm.anthropic_client import AnthropicLLMClient

logger = structlog.get_logger(__name__)


class JobNotAssistableError(Exception):
    """Exception raised when a job is not in a tier that allows assistance."""

    def __init__(self, job_id: UUID, tier: Optional[str]):
        self.job_id = job_id
        self.tier = tier
        super().__init__(f"Job {job_id} with tier '{tier}' is not assistable. Must be 'A' or 'B'.")


class ApplicationPackage(BaseModel):
    """
    Complete package of assistance results for a job application.
    """

    job_id: UUID
    cv_variant: VariantRecommendation
    cover_letter: Optional[CoverLetterResult] = None
    ats_keywords: ATSKeywordsResult
    cv_tweaks: CVTweaksResult
    total_cost_usd: float
    total_duration_ms: int
    estimated_apply_time_min: int


# In-memory cache for ApplicationPackage
# Maps job_id to (ApplicationPackage, expiration_time)
_CACHE: Dict[UUID, Tuple[ApplicationPackage, datetime]] = {}
_CACHE_TTL = timedelta(hours=1)


async def assist_application(
    session: Session,
    job_id: UUID,
    llm_client: AnthropicLLMClient,
    settings: Optional[Settings] = None,
    no_letter: bool = False,
    cv_variant_override: Optional[str] = None,
) -> ApplicationPackage:
    """
    Orchestrates the application assistance process for a specific job.

    Args:
        session: Database session.
        job_id: ID of the job to assist.
        llm_client: LLM client for API calls.
        settings: Application settings.
        no_letter: If True, skips cover letter generation.
        cv_variant_override: If provided, uses this variant instead of recommending one.

    Returns:
        An ApplicationPackage containing all generated components.

    Raises:
        JobNotAssistableError: If the job tier is not 'A' or 'B'.
        ValueError: If the job is not found in the database.
    """
    now = datetime.now(timezone.utc)

    # 1. Check Cache
    if job_id in _CACHE:
        package, expiration = _CACHE[job_id]
        if now < expiration:
            logger.info("assistant_cache_hit", job_id=str(job_id))
            return package
        else:
            del _CACHE[job_id]

    if settings is None:
        settings = Settings()  # type: ignore[call-arg]

    # 2. Fetch Job
    job = session.get(Job, job_id)
    if not job:
        raise ValueError(f"Job with ID {job_id} not found.")

    # 3. Validate Tier
    if job.tier not in {"A", "B"}:
        raise JobNotAssistableError(job_id, job.tier)

    logger.info("assistant_started", job_id=str(job_id), tier=job.tier)
    start_time = time.perf_counter()

    # 4. Step 1: Recommend CV and Load it (Fast, synchronous)
    if cv_variant_override:
        cv_recommendation = VariantRecommendation(
            variant_name=cv_variant_override,
            confidence=1.0,
            reasoning="Variant explicitly requested via override.",
        )
    else:
        cv_recommendation = recommend_cv_variant(job)

    cv_variant = load_cv(cv_recommendation.variant_name, settings=settings)

    # 5. Parallel Execution
    # We run Cover Letter generation and (ATS Keywords -> CV Tweaks) in parallel

    async def get_keywords_and_tweaks() -> Tuple[ATSKeywordsResult, CVTweaksResult]:
        keywords = await extract_ats_keywords(
            job=job,
            llm_client=llm_client,
            cv_variant=cv_variant,
            session=session,
        )
        tweaks = await suggest_cv_tweaks(
            job=job,
            cv_variant=cv_variant,
            ats_keywords=keywords,
            llm_client=llm_client,
            session=session,
        )
        return keywords, tweaks

    # Launch cover letter and (keywords+tweaks) in parallel
    if no_letter:
        ats_keywords, cv_tweaks = await get_keywords_and_tweaks()
        cover_letter = None
    else:
        # We use explicit variables for clarity and to help mypy inference
        keywords_tweaks_task = get_keywords_and_tweaks()
        cover_letter_task = generate_cover_letter(
            job=job,
            cv_variant=cv_variant,
            llm_client=llm_client,
            model=settings.COVER_LETTER_MODEL,
            session=session,
        )
        (ats_keywords, cv_tweaks), cover_letter = await asyncio.gather(
            keywords_tweaks_task, cover_letter_task
        )

    # 6. Calculate Totals
    end_time = time.perf_counter()
    duration_ms = int((end_time - start_time) * 1000)
    total_cost = ats_keywords.cost_usd + cv_tweaks.cost_usd
    if cover_letter:
        total_cost += cover_letter.cost_usd

    # 7. Estimated Apply Time Heuristic
    # Baseline 8 min, +1 min per tweak, -2 min if all keywords are present
    estimated_time = 8
    estimated_time += len(cv_tweaks.tweaks)

    all_keywords = ats_keywords.must_have + ats_keywords.nice_to_have
    if all_keywords and all(kw.present_in_cv for kw in all_keywords):
        estimated_time -= 2

    # Ensure at least 1 minute
    estimated_time = max(1, estimated_time)

    # 8. Create Package
    package = ApplicationPackage(
        job_id=job_id,
        cv_variant=cv_recommendation,
        cover_letter=cover_letter,
        ats_keywords=ats_keywords,
        cv_tweaks=cv_tweaks,
        total_cost_usd=total_cost,
        total_duration_ms=duration_ms,
        estimated_apply_time_min=estimated_time,
    )

    # 9. Persistence (redundant but explicit as per requirements)
    # generate_cover_letter already does this if session is passed,
    # but we ensure it here to be explicit in the orchestrator.
    if cover_letter:
        stmt = select(Application).where(Application.job_id == job_id)
        app = session.execute(stmt).scalar_one_or_none()
        if app:
            app.cover_letter_text = cover_letter.text
            app.cover_letter_model = cover_letter.model
            logger.info("assistant_persisted_to_app", job_id=str(job_id), app_id=str(app.id))

    # Persist assistant data in Job.score_data for cross-command CLI usage
    # We use reassignment to ensure SQLAlchemy tracks the change in the JSONB column
    new_score_data = dict(job.score_data or {})

    assistant_cache = {
        "cv_variant": cv_recommendation.variant_name,
        "estimated_apply_time_min": estimated_time,
    }
    if cover_letter:
        assistant_cache["cover_letter_text"] = cover_letter.text
        assistant_cache["cover_letter_model"] = cover_letter.model

    new_score_data["assistant_cache"] = assistant_cache
    job.score_data = new_score_data
    session.commit()

    # 10. Cache and Return
    _CACHE[job_id] = (package, now + _CACHE_TTL)

    logger.info(
        "assistant_completed",
        job_id=str(job_id),
        duration_ms=duration_ms,
        cost_usd=total_cost,
    )

    return package


def clear_assistant_cache(job_id: Optional[UUID] = None) -> None:
    """
    Clears the assistant cache.

    Args:
        job_id: If provided, only clears the cache for that specific job.
               If None, clears the entire cache.
    """
    if job_id:
        _CACHE.pop(job_id, None)
    else:
        _CACHE.clear()
