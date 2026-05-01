"""
Core logic for A/B testing, including deterministic variant selection
and statistical significance calculations.
"""

import hashlib
import math
import uuid
from typing import List, Optional

import structlog
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ABTestStatus
from jobhunter.db.models import ABTest, Job, OutreachMessage

logger = structlog.get_logger(__name__)


class VariantResult(BaseModel):
    """Result metrics for a specific variant."""

    variant: str
    sample_size: int
    conversions: int
    conversion_rate: float
    confidence_interval: tuple[float, float]


class ABTestResults(BaseModel):
    """Comprehensive results for an A/B test."""

    test_name: str
    metric_target: str
    variants: List[VariantResult]
    statistical_significance: bool
    p_value: float
    winner: Optional[str] = None


def select_variant(session: Session, test_name: str, entity_id: uuid.UUID) -> str:
    """
    Deterministically selects a variant for a given entity and test.

    Args:
        session: SQLAlchemy session.
        test_name: The name of the A/B test.
        entity_id: The UUID of the entity (job, contact, etc.).

    Returns:
        The selected variant name, or 'default' if no active test is found.
    """
    stmt = select(ABTest).where(
        and_(ABTest.name == test_name, ABTest.status == ABTestStatus.ACTIVE)
    )
    test = session.scalar(stmt)

    if not test:
        return "default"

    # Deterministic hash: hash(entity_id + test_name) % 100 -> bucket
    hasher = hashlib.md5()
    hasher.update(f"{entity_id}{test_name}".encode())
    bucket = int(hasher.hexdigest(), 16) % 100

    cumulative_weight = 0.0
    # Sort variants for deterministic iteration
    sorted_variants = sorted(test.variants.items())
    for variant, weight in sorted_variants:
        cumulative_weight += weight * 100
        if bucket < cumulative_weight:
            return variant

    return "default"


def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def calculate_z_test(p1: float, n1: int, p2: float, n2: int) -> float:
    """
    Calculates the p-value for a two-proportion z-test.
    """
    if n1 == 0 or n2 == 0:
        return 1.0

    p_pooled = (p1 * n1 + p2 * n2) / (n1 + n2)

    if p_pooled == 0 or p_pooled == 1:
        return 1.0

    se = math.sqrt(p_pooled * (1 - p_pooled) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se

    # Two-tailed p-value
    p_value = 2 * (1 - _normal_cdf(abs(z)))
    return float(p_value)


def get_ab_test_results(session: Session, test_name: str) -> ABTestResults:
    """
    Aggregates metrics and calculates statistical significance for an A/B test.
    """
    stmt = select(ABTest).where(ABTest.name == test_name)
    test = session.scalar(stmt)

    if not test:
        raise ValueError(f"A/B test '{test_name}' not found.")

    variant_results = []

    # Define metrics based on metric_target
    # tier_a_precision -> tier='A' / total_scored
    # outreach_response_rate -> replied_at is not null / total_sent

    for variant in test.variants.keys():
        sample_size = 0
        conversions = 0

        if test.metric_target == "tier_a_precision":
            sample_size = (
                session.scalar(select(func.count(Job.id)).where(Job.score_version == variant)) or 0
            )
            from jobhunter.db.enums import JobTier

            conversions = (
                session.scalar(
                    select(func.count(Job.id)).where(
                        and_(Job.score_version == variant, Job.tier == JobTier.A)
                    )
                )
                or 0
            )
        elif test.metric_target == "outreach_response_rate":
            sample_size = (
                session.scalar(
                    select(func.count(OutreachMessage.id)).where(
                        and_(
                            OutreachMessage.template_version == variant,
                            OutreachMessage.status != "draft",
                        )
                    )
                )
                or 0
            )
            conversions = (
                session.scalar(
                    select(func.count(OutreachMessage.id)).where(
                        and_(
                            OutreachMessage.template_version == variant,
                            OutreachMessage.replied_at.is_not(None),
                        )
                    )
                )
                or 0
            )
        # Add more metrics as needed

        rate = conversions / sample_size if sample_size > 0 else 0.0

        # Basic normal approximation for confidence interval
        margin = 1.96 * math.sqrt(rate * (1 - rate) / sample_size) if sample_size > 0 else 0.0

        variant_results.append(
            VariantResult(
                variant=variant,
                sample_size=sample_size,
                conversions=conversions,
                conversion_rate=rate,
                confidence_interval=(max(0.0, rate - margin), min(1.0, rate + margin)),
            )
        )

    # Calculate significance vs control (assume first variant in the test.variants dict is control)
    # Actually dictionaries are ordered in Python 3.7+
    p_value = 1.0
    sig = False
    if len(variant_results) >= 2:
        control = variant_results[0]
        treatment = variant_results[1]
        p_value = calculate_z_test(
            control.conversion_rate,
            control.sample_size,
            treatment.conversion_rate,
            treatment.sample_size,
        )
        sig = p_value < 0.05

    return ABTestResults(
        test_name=test_name,
        metric_target=test.metric_target,
        variants=variant_results,
        statistical_significance=sig,
        p_value=p_value,
    )
