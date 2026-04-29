import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path
import uuid

from jobhunter.application.cover_letter import (
    generate_cover_letter,
    validate_cover_letter,
    CoverLetterResult,
)
from jobhunter.db.models import Job, Application
from jobhunter.application.cv import CVVariant
from jobhunter.llm.anthropic_client import LLMResponse


@pytest.fixture
def mock_job():
    return Job(
        id=uuid.uuid4(),
        title="Senior Python Engineer",
        company="Tech Corp",
        description="We are looking for a senior python engineer with experience in AI and ML. "
        * 50,
        score_data={"recommendation": {"cover_letter_angle": "Focus on AI experience"}},
    )


@pytest.fixture
def mock_cv_variant():
    return CVVariant(
        name="ai_python",
        path=Path("dummy.md"),
        summary="Expert AI developer",
        stack_primary=["Python", "PyTorch"],
        stack_secondary=[],
        experience=[],
        skills=[],
        raw_markdown="## SUMMARY\nExpert AI developer\n## EXPERIENCE\n### Lead | Co | 2020\n- Did AI",
    )


def test_validate_cover_letter():
    forbidden = ["passionate about"]

    # Valid
    text_valid = "Word " * 300
    assert validate_cover_letter(text_valid, forbidden) == []

    # Too short
    text_short = "Short"
    assert (
        "Word count 1 is outside the allowed range"
        in validate_cover_letter(text_short, forbidden)[0]
    )

    # Too long
    text_long = "Word " * 500
    assert (
        "Word count 500 is outside the allowed range"
        in validate_cover_letter(text_long, forbidden)[0]
    )

    # Placeholder
    text_placeholder = "Hello [Company]" + " Word" * 300
    assert "Found placeholders" in validate_cover_letter(text_placeholder, forbidden)[0]

    # Forbidden
    text_forbidden = "I am passionate about AI" + " Word" * 300
    assert (
        "Found forbidden phrase: 'passionate about'"
        in validate_cover_letter(text_forbidden, forbidden)[0]
    )


@pytest.mark.asyncio
async def test_generate_cover_letter_success(mock_job, mock_cv_variant):
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(
        return_value=LLMResponse(
            text="This is a valid cover letter. " * 50,
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=300,
            cost_usd=0.05,
            duration_ms=2000,
            stop_reason="end_turn",
        )
    )

    result = await generate_cover_letter(
        job=mock_job, cv_variant=mock_cv_variant, llm_client=mock_llm, model="claude-opus-4-7"
    )

    assert isinstance(result, CoverLetterResult)
    assert result.word_count >= 250
    assert mock_llm.complete.call_count == 1


@pytest.mark.asyncio
async def test_generate_cover_letter_retry(mock_job, mock_cv_variant):
    mock_llm = MagicMock()
    # First response is too short, second is valid
    mock_llm.complete = AsyncMock(
        side_effect=[
            LLMResponse(
                text="Too short.",
                model="claude-opus-4-7",
                input_tokens=100,
                output_tokens=10,
                cost_usd=0.01,
                duration_ms=1000,
                stop_reason="end_turn",
            ),
            LLMResponse(
                text="This is a valid cover letter. " * 50,
                model="claude-opus-4-7",
                input_tokens=150,
                output_tokens=300,
                cost_usd=0.05,
                duration_ms=2000,
                stop_reason="end_turn",
            ),
        ]
    )

    result = await generate_cover_letter(
        job=mock_job, cv_variant=mock_cv_variant, llm_client=mock_llm, model="claude-opus-4-7"
    )

    assert result.word_count >= 250
    assert mock_llm.complete.call_count == 2
    # Check that retry had extra instruction
    args, kwargs = mock_llm.complete.call_args
    assert "Your previous attempt failed validation" in kwargs["system"]


@pytest.mark.asyncio
async def test_generate_cover_letter_persistence(mock_job, mock_cv_variant):
    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock(
        return_value=LLMResponse(
            text="This is a valid cover letter. " * 50,
            model="claude-opus-4-7",
            input_tokens=100,
            output_tokens=300,
            cost_usd=0.05,
            duration_ms=2000,
            stop_reason="end_turn",
        )
    )

    mock_session = MagicMock()
    mock_app = Application(job_id=mock_job.id)

    # Mock session.execute(stmt).scalar_one_or_none()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_app
    mock_session.execute.return_value = mock_result

    await generate_cover_letter(
        job=mock_job,
        cv_variant=mock_cv_variant,
        llm_client=mock_llm,
        model="claude-opus-4-7",
        session=mock_session,
    )

    assert mock_app.cover_letter_text.startswith("This is a valid cover letter.")
    assert mock_app.cover_letter_model == "claude-opus-4-7"
    mock_session.commit.assert_called_once()
