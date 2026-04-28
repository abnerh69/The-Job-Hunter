"""
Schemas and utilities for parsing and validating job scoring responses from the AI.

This module provides Pydantic models that define the structure and validation rules
for job scoring results, ensuring consistency and preventing malformed data from
entering the system.
"""

import re
from enum import StrEnum
from typing import Annotated, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    model_validator,
)


class Tier(StrEnum):
    """Enumeration of job tiers."""

    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"


class CompanyStage(StrEnum):
    """Enumeration of company stages."""

    EARLY_STARTUP = "early_startup"
    GROWTH_STARTUP = "growth_startup"
    SCALEUP = "scaleup"
    ENTERPRISE = "enterprise"
    AGENCY = "agency"
    UNKNOWN = "unknown"


class Seniority(StrEnum):
    """Enumeration of seniority levels."""

    JUNIOR = "junior"
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"
    LEAD = "lead"
    UNKNOWN = "unknown"


class RemoteType(StrEnum):
    """Enumeration of remote work types."""

    REMOTE_GLOBAL = "remote_global"
    REMOTE_EU_ONLY = "remote_eu_only"
    REMOTE_DACH_ONLY = "remote_dach_only"
    REMOTE_COUNTRY_ONLY = "remote_country_only"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class TimezoneRequirement(StrEnum):
    """Enumeration of timezone requirements."""

    STRICT_CET = "strict_CET"
    FLEXIBLE_EU = "flexible_EU"
    ANY = "any"
    AMERICAS_ONLY = "americas_only"
    UNKNOWN = "unknown"


class ContractType(StrEnum):
    """Enumeration of contract types."""

    B2B = "B2B"
    EOR = "EOR"
    DIRECT_EMPLOYEE = "direct_employee"
    EITHER = "either"
    UNKNOWN = "unknown"


class Action(StrEnum):
    """Enumeration of recommended actions."""

    APPLY_NOW = "apply_now"
    APPLY_WITH_CAVEATS = "apply_with_caveats"
    MANUAL_REVIEW = "manual_review"
    SKIP = "skip"


class Priority(StrEnum):
    """Enumeration of recommendation priorities."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CompanyInfo(BaseModel):
    """Information about the company."""

    model_config = ConfigDict(extra="forbid")

    name: str
    stage: CompanyStage
    domain_inferred: str | None


class RoleInfo(BaseModel):
    """Information about the job role."""

    model_config = ConfigDict(extra="forbid")

    title_normalized: str
    seniority_inferred: Seniority
    primary_stack_match: list[str]
    stack_overlap_pct: Annotated[int, Field(ge=0, le=100)]
    is_ai_ml_role: bool
    is_flutter_role: bool
    is_full_stack: bool


class CompensationInfo(BaseModel):
    """Information about the role compensation."""

    model_config = ConfigDict(extra="forbid")

    salary_min_usd_month: float | None
    salary_max_usd_month: float | None
    salary_explicit_in_offer: bool
    currency_original: str | None
    meets_floor: bool | None
    meets_target: bool | None
    notes: str | None


class LogisticsInfo(BaseModel):
    """Information about job logistics."""

    model_config = ConfigDict(extra="forbid")

    remote_type: RemoteType
    timezone_requirement: TimezoneRequirement
    overlap_hours_required_with_CET: int | None
    latam_friendly: bool | None
    colombia_explicitly_blocked: bool
    contract_type_offered: ContractType
    language_requirements: list[str]


class MatchAnalysis(BaseModel):
    """Analysis of the match between candidate and role."""

    model_config = ConfigDict(extra="forbid")

    key_match_points: list[str]
    key_gaps: list[str]
    differentiators_to_emphasize: list[str]


class Recommendation(BaseModel):
    """Final recommendation for the job offer."""

    model_config = ConfigDict(extra="forbid")

    action: Action
    priority: Priority
    reason_short: str
    cover_letter_angle: str


class ScoringResult(BaseModel):
    """Schema for a valid scoring response from the AI."""

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(True, frozen=True)
    fit_score: Annotated[int, Field(ge=0, le=100)]
    tier: Tier
    company: CompanyInfo
    role: RoleInfo
    compensation: CompensationInfo
    logistics: LogisticsInfo
    match_analysis: MatchAnalysis
    red_flags: list[str]
    yellow_flags: list[str]
    recommendation: Recommendation

    @model_validator(mode="after")
    def validate_tier_and_flags(self) -> "ScoringResult":
        """
        Validate consistency between tier and red flags.
        - If tier=REJECT, there must be at least one red_flag.
        - If tier=A, there cannot be any red_flags.
        """
        if self.tier == Tier.REJECT and not self.red_flags:
            raise ValueError("If tier is REJECT, at least one red flag must be specified.")
        if self.tier == Tier.A and self.red_flags:
            raise ValueError("Tier A cannot have red flags.")
        return self


class InvalidScoringResponse(BaseModel):
    """Schema for cases where the AI determines the offer is invalid or spam."""

    model_config = ConfigDict(extra="forbid")

    valid: bool = Field(False, frozen=True)
    reason: str


def parse_scoring_response(raw_text: str) -> ScoringResult | InvalidScoringResponse:
    """
    Parses the raw text from the AI response into a ScoringResult or InvalidScoringResponse.

    Args:
        raw_text: The raw string response from the AI.

    Returns:
        A validated ScoringResult or InvalidScoringResponse.

    Raises:
        ValidationError: If the JSON is invalid or does not match either schema.
    """
    # Extract JSON from markdown fences if present
    json_match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw_text, re.DOTALL)
    content = json_match.group(1) if json_match else raw_text.strip()

    # Use TypeAdapter for robust parsing of Union
    adapter: TypeAdapter[ScoringResult | InvalidScoringResponse] = TypeAdapter(
        Union[ScoringResult, InvalidScoringResponse]
    )
    result = adapter.validate_json(content)

    return result
