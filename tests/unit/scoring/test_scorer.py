import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from jobhunter.db.models import Job
from jobhunter.llm.anthropic_client import LLMResponse
from jobhunter.scoring.errors import ScoringAPIError, ScoringParseError
from jobhunter.scoring.scorer import JobScorer, ScoringOutcome
from jobhunter.scoring.schema import ScoringResult, InvalidScoringResponse


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_job() -> Job:
    return Job(
        id=uuid.uuid4(),
        title="Python Engineer",
        company="Tech Corp",
        description="We are looking for a Python Engineer with 5 years of experience.",
        source="linkedin",
        url="https://linkedin.com/job/123",
        scraped_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        location_raw="Remote, EU",
    )


@pytest.fixture
def valid_json_response() -> str:
    return """
    {
        "valid": true,
        "fit_score": 85,
        "tier": "B",
        "company": {
            "name": "Tech Corp",
            "stage": "scaleup",
            "domain_inferred": "SaaS"
        },
        "role": {
            "title_normalized": "Python Engineer",
            "seniority_inferred": "senior",
            "primary_stack_match": ["python"],
            "stack_overlap_pct": 90,
            "is_ai_ml_role": false,
            "is_flutter_role": false,
            "is_full_stack": false
        },
        "compensation": {
            "salary_min_usd_month": 6000,
            "salary_max_usd_month": 8000,
            "salary_explicit_in_offer": true,
            "currency_original": "USD",
            "meets_floor": true,
            "meets_target": true,
            "notes": "Good salary"
        },
        "logistics": {
            "remote_type": "remote_eu_only",
            "timezone_requirement": "flexible_EU",
            "overlap_hours_required_with_CET": 4,
            "latam_friendly": false,
            "colombia_explicitly_blocked": false,
            "contract_type_offered": "B2B",
            "language_requirements": ["English"]
        },
        "match_analysis": {
            "key_match_points": ["Python", "Remote EU"],
            "key_gaps": ["No Flutter"],
            "differentiators_to_emphasize": ["Open source experience"]
        },
        "red_flags": [],
        "yellow_flags": ["No stock options"],
        "recommendation": {
            "action": "apply_now",
            "priority": "high",
            "reason_short": "Good fit",
            "cover_letter_angle": "Focus on Python expertise"
        }
    }
    """


@pytest.mark.asyncio
async def test_score_success(
    mock_llm_client: AsyncMock, sample_job: Job, valid_json_response: str
) -> None:
    # Arrange
    llm_response = LLMResponse(
        text=valid_json_response,
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=200,
        cost_usd=0.001,
        duration_ms=500,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = llm_response
    scorer = JobScorer(llm_client=mock_llm_client)

    # Act
    outcome = await scorer.score(sample_job, profile=sample_profile)

    # Assert
    assert isinstance(outcome, ScoringOutcome)
    assert isinstance(outcome.result, ScoringResult)
    assert outcome.result.fit_score == 85
    assert outcome.model == "claude-haiku-4-5-20251001"
    assert outcome.cost_usd == 0.001
    assert mock_llm_client.complete.call_count == 1


@pytest.mark.asyncio
async def test_score_retry_success(
    mock_llm_client: AsyncMock, sample_job: Job, valid_json_response: str
) -> None:
    # Arrange
    # The first response should fail because parse_scoring_response is strict if it has extra text

    responses = [
        LLMResponse(
            text="Invalid JSON here",
            model="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=10,
            cost_usd=0.0001,
            duration_ms=200,
            stop_reason="end_turn",
        ),
        LLMResponse(
            text=valid_json_response,
            model="claude-haiku-4-5-20251001",
            input_tokens=120,
            output_tokens=200,
            cost_usd=0.0012,
            duration_ms=500,
            stop_reason="end_turn",
        ),
    ]
    mock_llm_client.complete.side_effect = responses
    scorer = JobScorer(llm_client=mock_llm_client)

    # Act
    outcome = await scorer.score(sample_job, profile=sample_profile)

    # Assert
    assert isinstance(outcome, ScoringOutcome)
    assert isinstance(outcome.result, ScoringResult)
    assert outcome.result.fit_score == 85
    assert mock_llm_client.complete.call_count == 2
    # Second call should have reinforced prompt
    args, kwargs = mock_llm_client.complete.call_args
    assert "IMPORTANT: Respond with valid JSON only" in kwargs["user"]


@pytest.mark.asyncio
async def test_score_double_failure(mock_llm_client: AsyncMock, sample_job: Job) -> None:
    # Arrange
    llm_response = LLMResponse(
        text="Still invalid JSON",
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=10,
        cost_usd=0.0001,
        duration_ms=200,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = llm_response
    scorer = JobScorer(llm_client=mock_llm_client)

    # Act & Assert
    with pytest.raises(ScoringParseError) as excinfo:
        await scorer.score(sample_job, profile=sample_profile)

    assert "Failed to parse AI response after retry" in str(excinfo.value)
    assert excinfo.value.raw_response == "Still invalid JSON"
    assert mock_llm_client.complete.call_count == 2


@pytest.mark.asyncio
async def test_score_api_error(mock_llm_client: AsyncMock, sample_job: Job) -> None:
    # Arrange
    mock_llm_client.complete.side_effect = Exception("API connection failed")
    scorer = JobScorer(llm_client=mock_llm_client)

    # Act & Assert
    with pytest.raises(ScoringAPIError) as excinfo:
        await scorer.score(sample_job, profile=sample_profile)

    assert "Failed to call LLM" in str(excinfo.value)
    assert mock_llm_client.complete.call_count == 1


@pytest.mark.asyncio
async def test_score_invalid_response(mock_llm_client: AsyncMock, sample_job: Job) -> None:
    # Arrange
    invalid_json = '{"valid": false, "reason": "Spam job offer"}'
    llm_response = LLMResponse(
        text=invalid_json,
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=20,
        cost_usd=0.0002,
        duration_ms=300,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = llm_response
    scorer = JobScorer(llm_client=mock_llm_client)

    # Act
    outcome = await scorer.score(sample_job, profile=sample_profile)

    # Assert
    assert isinstance(outcome.result, InvalidScoringResponse)
    assert outcome.result.valid is False
    assert outcome.result.reason == "Spam job offer"


def test_truncate_description() -> None:
    # Arrange
    scorer = JobScorer(llm_client=MagicMock())
    long_desc = "Word " * 2000  # ~10000 chars

    # Act
    truncated = scorer._truncate_description(long_desc, max_chars=100)

    # Assert
    assert len(truncated) <= 100
    assert truncated.endswith("Word")  # Should cut at word boundary


def test_truncate_description_paragraph() -> None:
    # Arrange
    scorer = JobScorer(llm_client=MagicMock())
    # desc: 44 chars before \n\n. Total around 60.
    desc = "Paragraph 1 is very long and has many words.\n\nParagraph 2."

    # Act
    # max_chars=50. 70% of 50 is 35. 44 > 35.
    truncated = scorer._truncate_description(desc, max_chars=50)

    # Assert
    assert truncated == "Paragraph 1 is very long and has many words."


def test_truncate_description_sentence() -> None:
    # Arrange
    scorer = JobScorer(llm_client=MagicMock())
    # Sentence 1: 13 chars. Sentence 2: 21 chars. Total 34.
    desc = "Sentence one. Sentence two is longer. Sentence three."

    # Act
    # max_chars=40. 80% of 40 is 32. 34 > 32.
    truncated = scorer._truncate_description(desc, max_chars=40)

    # Assert
    assert truncated == "Sentence one. Sentence two is longer."
