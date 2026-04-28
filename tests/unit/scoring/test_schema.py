import json
from typing import Any

import pytest
from pydantic import ValidationError

from jobhunter.scoring.schema import (
    InvalidScoringResponse,
    ScoringResult,
    Tier,
    parse_scoring_response,
)


@pytest.fixture
def valid_scoring_data() -> dict[str, Any]:
    return {
        "valid": True,
        "fit_score": 85,
        "tier": "A",
        "company": {"name": "Tech Corp", "stage": "scaleup", "domain_inferred": "Fintech"},
        "role": {
            "title_normalized": "Senior Python Engineer",
            "seniority_inferred": "senior",
            "primary_stack_match": ["Python", "AWS"],
            "stack_overlap_pct": 90,
            "is_ai_ml_role": False,
            "is_flutter_role": False,
            "is_full_stack": False,
        },
        "compensation": {
            "salary_min_usd_month": 7000.0,
            "salary_max_usd_month": 9000.0,
            "salary_explicit_in_offer": True,
            "currency_original": "USD",
            "meets_floor": True,
            "meets_target": True,
            "notes": "Excellent package",
        },
        "logistics": {
            "remote_type": "remote_global",
            "timezone_requirement": "flexible_EU",
            "overlap_hours_required_with_CET": 4,
            "latam_friendly": True,
            "colombia_explicitly_blocked": False,
            "contract_type_offered": "B2B",
            "language_requirements": ["English"],
        },
        "match_analysis": {
            "key_match_points": ["Strong Python skills", "AWS experience"],
            "key_gaps": [],
            "differentiators_to_emphasize": ["Experience with high-scale systems"],
        },
        "red_flags": [],
        "yellow_flags": [],
        "recommendation": {
            "action": "apply_now",
            "priority": "high",
            "reason_short": "Perfect match for senior role",
            "cover_letter_angle": "Highlight AWS and scalability experience",
        },
    }


def test_valid_scoring_result(valid_scoring_data: dict[str, Any]) -> None:
    """Test that a valid response is correctly parsed into ScoringResult."""
    raw_json = json.dumps(valid_scoring_data)
    result = parse_scoring_response(raw_json)
    assert isinstance(result, ScoringResult)
    assert result.valid is True
    assert result.fit_score == 85
    assert result.tier == Tier.A
    assert result.company.name == "Tech Corp"


def test_reject_with_red_flags(valid_scoring_data: dict[str, Any]) -> None:
    """Test that tier=REJECT is valid if there are red flags."""
    valid_scoring_data["tier"] = "REJECT"
    valid_scoring_data["red_flags"] = ["EU residents only"]
    valid_scoring_data["fit_score"] = 20

    raw_json = json.dumps(valid_scoring_data)
    result = parse_scoring_response(raw_json)
    assert isinstance(result, ScoringResult)
    assert result.tier == Tier.REJECT
    assert "EU residents only" in result.red_flags


def test_reject_without_red_flags_fails(valid_scoring_data: dict[str, Any]) -> None:
    """Test that tier=REJECT without red flags raises ValidationError."""
    valid_scoring_data["tier"] = "REJECT"
    valid_scoring_data["red_flags"] = []

    raw_json = json.dumps(valid_scoring_data)
    with pytest.raises(ValidationError) as excinfo:
        parse_scoring_response(raw_json)
    assert "If tier is REJECT, at least one red flag must be specified." in str(excinfo.value)


def test_tier_a_with_red_flags_fails(valid_scoring_data: dict[str, Any]) -> None:
    """Test that tier=A with red flags raises ValidationError."""
    valid_scoring_data["tier"] = "A"
    valid_scoring_data["red_flags"] = ["Some red flag"]

    raw_json = json.dumps(valid_scoring_data)
    with pytest.raises(ValidationError) as excinfo:
        parse_scoring_response(raw_json)
    assert "Tier A cannot have red flags." in str(excinfo.value)


def test_markdown_fences(valid_scoring_data: dict[str, Any]) -> None:
    """Test that parse_scoring_response handles markdown fences."""
    raw_json = json.dumps(valid_scoring_data)
    raw_text = f"Here is the result:\n```json\n{raw_json}\n```\nHope it helps!"

    result = parse_scoring_response(raw_text)
    assert isinstance(result, ScoringResult)
    assert result.fit_score == 85


def test_malformed_json() -> None:
    """Test that malformed JSON raises ValidationError."""
    raw_text = '{"valid": true, "fit_score": 85'  # Missing closing brace
    with pytest.raises(ValidationError):
        parse_scoring_response(raw_text)


def test_extra_field_forbidden(valid_scoring_data: dict[str, Any]) -> None:
    """Test that extra fields in JSON raise ValidationError (extra='forbid')."""
    valid_scoring_data["unexpected_field"] = "boom"
    raw_json = json.dumps(valid_scoring_data)

    with pytest.raises(ValidationError):
        parse_scoring_response(raw_json)


def test_invalid_scoring_response_schema() -> None:
    """Test that {valid: false, reason: ...} returns InvalidScoringResponse."""
    raw_json = json.dumps({"valid": False, "reason": "Offer is spam"})
    result = parse_scoring_response(raw_json)
    assert isinstance(result, InvalidScoringResponse)
    assert result.valid is False
    assert result.reason == "Offer is spam"


def test_invalid_range_fit_score(valid_scoring_data: dict[str, Any]) -> None:
    """Test that fit_score outside [0, 100] raises ValidationError."""
    valid_scoring_data["fit_score"] = 105
    raw_json = json.dumps(valid_scoring_data)
    with pytest.raises(ValidationError):
        parse_scoring_response(raw_json)

    valid_scoring_data["fit_score"] = -5
    raw_json = json.dumps(valid_scoring_data)
    with pytest.raises(ValidationError):
        parse_scoring_response(raw_json)
