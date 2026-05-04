"""
Logic for recommending the most suitable CV variant for a given job.

This module provides a deterministic heuristic to choose between available CV variants
(e.g., ai_python, flutter, fullstack) based on job details and structured scoring data.
"""

from pydantic import BaseModel, Field
from jobhunter.db.models import Job


class VariantRecommendation(BaseModel):
    """
    Recommendation for a CV variant.

    Attributes:
        variant_name: The name of the recommended CV variant.
        confidence: Confidence score of the recommendation [0, 1].
        reasoning: Explanation for why this variant was recommended.
    """

    variant_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def recommend_cv_variant(job: Job) -> VariantRecommendation:
    """
    Recommends the optimal CV variant for a given job using deterministic heuristics.

    It prioritizes structured scoring data if available, falling back to keyword
    matching on the title and description otherwise.

    Args:
        job: The Job object containing title, description, and optionally score_data.

    Returns:
        A VariantRecommendation object.
    """
    score_data = job.score_data

    if score_data and score_data.get("valid"):
        role = score_data.get("role", {})
        is_ai_ml = role.get("is_ai_ml_role", False)
        is_flutter = role.get("is_flutter_role", False)
        is_fullstack = role.get("is_full_stack", False)
        stack = [s.lower() for s in role.get("primary_stack_match", [])]

        # 1. AI/Python match
        if is_ai_ml:
            return VariantRecommendation(
                variant_name="ai_python",
                confidence=1.0,
                reasoning="Role is explicitly flagged as AI/ML in structured scoring data.",
            )

        has_python = "python" in stack
        has_ai_keywords = any(
            kw in stack
            for kw in ["ai", "llm", "ml", "machine learning", "pytorch", "tensorflow", "langchain"]
        )
        if has_python and has_ai_keywords:
            return VariantRecommendation(
                variant_name="ai_python",
                confidence=0.9,
                reasoning="Stack match: contains Python and AI/ML keywords.",
            )

        # 2. Flutter match
        if is_flutter:
            return VariantRecommendation(
                variant_name="flutter",
                confidence=1.0,
                reasoning="Role is explicitly flagged as Flutter in structured scoring data.",
            )

        if any(kw in stack for kw in ["flutter", "dart"]):
            return VariantRecommendation(
                variant_name="flutter",
                confidence=0.9,
                reasoning="Stack match: contains Flutter or Dart keywords.",
            )

        # 3. Fullstack match
        if is_fullstack:
            return VariantRecommendation(
                variant_name="fullstack",
                confidence=0.8,
                reasoning="Role is explicitly flagged as Full Stack in structured scoring data.",
            )

        # 4. Default with score data (Structured but no specific match)
        return VariantRecommendation(
            variant_name="fullstack",
            confidence=0.5,
            reasoning="No specific stack match found in scoring data; defaulting to fullstack.",
        )

    # 5. Fallback: Keyword matching on raw text (No structured score_data or invalid)
    text = f"{job.title} {job.description}".lower()

    # Check Flutter keywords first as they are very specific
    if "flutter" in text or "dart" in text:
        return VariantRecommendation(
            variant_name="flutter",
            confidence=0.5,
            reasoning="Heuristic match based on title/description keywords (flutter/dart).",
        )

    # Check AI/Python keywords
    if "python" in text and any(kw in text for kw in ["ai", "llm", "ml", "machine learning"]):
        return VariantRecommendation(
            variant_name="ai_python",
            confidence=0.5,
            reasoning="Heuristic match based on title/description keywords (python + ai/ml).",
        )

    # 6. Absolute Fallback
    return VariantRecommendation(
        variant_name="fullstack",
        confidence=0.4,
        reasoning="No structured scoring data or clear keyword matches; defaulting to fullstack.",
    )
