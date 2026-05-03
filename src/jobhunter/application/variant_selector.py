"""
Logic for recommending the most suitable CV variant for a given job.

This module provides a deterministic heuristic to choose between available CV variants
based on job details and variant metadata, with an LLM fallback for ambiguous cases.
"""

import json
import uuid
from typing import Sequence

import structlog
from pydantic import BaseModel, Field

from jobhunter.application import NoCVVariantsAvailableError
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import CVVariant, Job
from jobhunter.llm.anthropic_client import AnthropicLLMClient

logger = structlog.get_logger(__name__)


class VariantRecommendation(BaseModel):
    """
    Recommendation for a CV variant.

    Attributes:
        variant_name: The name of the recommended CV variant.
        variant_id: The ID of the recommended CV variant.
        confidence: Confidence score of the recommendation [0, 1].
        reasoning: Explanation for why this variant was recommended.
    """

    variant_name: str
    variant_id: uuid.UUID | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def _keyword_match_score(variant: CVVariant, job: Job) -> float:
    """
    Calculates a heuristic score for a variant based on keyword matching.

    Score is the ratio of matched keywords from variant metadata to total keywords.
    """
    keywords: set[str] = set()
    if variant.target_role_keywords:
        keywords.update(kw.lower() for kw in variant.target_role_keywords)
    if variant.target_stack:
        keywords.update(kw.lower() for kw in variant.target_stack)

    if not keywords:
        return 0.0

    text = f"{job.title} {job.description}".lower()
    matches = sum(kw in text for kw in keywords)

    return float(matches) / len(keywords)


async def _llm_disambiguate(
    job: Job, variants: Sequence[CVVariant], llm_client: AnthropicLLMClient
) -> VariantRecommendation | None:
    """
    Uses LLM to select the best variant when heuristics are ambiguous.
    """
    # Use Sonnet as requested (claude-3-5-sonnet-20241022)
    model = "claude-3-5-sonnet-20241022"

    variant_info = []
    for v in variants:
        variant_info.append(
            {
                "name": v.name,
                "summary": v.summary[:500] if v.summary else "",
                "keywords": v.target_role_keywords or [],
                "stack": v.target_stack or [],
            }
        )

    system_prompt = (
        "You are an expert technical recruiter. You must select the most appropriate CV variant "
        "for a job from a list of available variants based on the job title and description."
    )

    user_prompt = f"""
Job Title: {job.title}
Job Description Snippet: {job.description[:1500]}

Available CV Variants:
{json.dumps(variant_info, indent=2)}

Select the best variant. Return ONLY a JSON object with:
{{
  "variant_name": "exact name of the variant",
  "confidence": 0.X,
  "reasoning": "brief explanation"
}}
"""

    logger.info("cv_variant_llm_disambiguation_started", job_id=str(job.id))

    try:
        response = await llm_client.complete(
            system=system_prompt,
            user=user_prompt,
            model=model,
            purpose=LLMPurpose.CV_VARIANT_SELECTION,
        )

        data = json.loads(response.text)
        v_name = data.get("variant_name")

        # Find the matching variant object
        selected = next((v for v in variants if v.name == v_name), None)
        if not selected:
            # If LLM hallucinated a name, pick the one with highest heuristic score
            logger.warning("cv_variant_llm_hallucinated_name", hallucinated_name=v_name)
            return None  # Signal to use heuristic instead

        return VariantRecommendation(
            variant_name=selected.name,
            variant_id=selected.id,
            confidence=float(data.get("confidence", 0.5)),
            reasoning=f"[LLM Fallback] {data.get('reasoning', 'Selected by LLM')}",
        )
    except Exception as e:
        logger.error("cv_variant_llm_disambiguation_failed", error=str(e))
        return None


async def recommend_cv_variant(
    job: Job,
    available_variants: Sequence[CVVariant],
    llm_client: AnthropicLLMClient | None = None,
) -> VariantRecommendation:
    """
    Recommends the optimal CV variant for a given job using heuristics and LLM fallback.

    Args:
        job: The Job object containing title and description.
        available_variants: List of CV variants from the database.
        llm_client: LLM client for ambiguous cases.

    Returns:
        A VariantRecommendation object.

    Raises:
        NoCVVariantsAvailableError: If available_variants is empty.
    """
    if not available_variants:
        raise NoCVVariantsAvailableError()

    if len(available_variants) == 1:
        v = available_variants[0]
        return VariantRecommendation(
            variant_name=v.name,
            variant_id=v.id,
            confidence=1.0,
            reasoning="Only one CV variant available.",
        )

    # Step 1: Heuristic Scoring
    variant_scores = []
    for v in available_variants:
        score = _keyword_match_score(v, job)
        variant_scores.append((v, score))

    # Sort by score descending
    variant_scores.sort(key=lambda x: x[1], reverse=True)

    best_variant, best_score = variant_scores[0]
    second_best_score = variant_scores[1][1] if len(variant_scores) > 1 else 0.0

    # Step 2: Fallback to LLM if ambiguous
    # Ambiguity criteria: confidence < 0.4 OR tie between top variants
    is_tie = best_score == second_best_score
    is_low_confidence = best_score < 0.4

    if (is_tie or is_low_confidence) and llm_client:
        recommendation = await _llm_disambiguate(job, available_variants, llm_client)
        if recommendation:
            return recommendation

    # Heuristic final choice (if no LLM or LLM failed/unnecessary)
    reasoning = f"Heuristic match based on keywords (score: {best_score:.2f})."
    if is_tie:
        reasoning = f"Heuristic tie-break (score: {best_score:.2f}), selected first match."

    return VariantRecommendation(
        variant_name=best_variant.name,
        variant_id=best_variant.id,
        confidence=best_score,
        reasoning=reasoning,
    )
