import json
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from jobhunter.application.ats_keywords import ATSKeywordsResult, Keyword
from jobhunter.application.cv import CVVariant, Experience
from jobhunter.application.cv_tweaks import suggest_cv_tweaks, load_cv_tweaks_prompt
from jobhunter.db.models import Job
from jobhunter.llm.anthropic_client import AnthropicLLMClient, LLMResponse


@pytest.fixture
def mock_job() -> Job:
    return Job(
        id=uuid4(),
        title="Python Developer",
        company="Tech Corp",
        description="We need a Python developer with experience in FastAPI and AWS.",
    )


@pytest.fixture
def mock_cv_variant() -> CVVariant:
    return CVVariant(
        name="test_cv",
        summary="Senior Developer",
        stack_primary=["Python", "SQL"],
        stack_secondary=["AWS"],
        experience=[
            Experience(
                role="Developer",
                company="Old Corp",
                dates="2020-2023",
                bullets=["Built stuff", "Fixed bugs"],
            )
        ],
        skills=["Python", "AWS"],
        raw_markdown="## SUMMARY\nSenior Developer\n## EXPERIENCE\n### Developer | Old Corp | 2020-2023\n- Built stuff\n- Fixed bugs",
    )


@pytest.fixture
def mock_ats_keywords() -> ATSKeywordsResult:
    return ATSKeywordsResult(
        must_have=[
            Keyword(term="Python", category="technical", weight=10, present_in_cv=True),
            Keyword(term="FastAPI", category="technical", weight=9, present_in_cv=False),
        ],
        nice_to_have=[
            Keyword(term="AWS", category="tool", weight=5, present_in_cv=True),
        ],
        model="test-model",
        prompt_version="v1",
        cost_usd=0.01,
    )


def test_load_cv_tweaks_prompt() -> None:
    version, system, user = load_cv_tweaks_prompt("v1")
    assert version == "v1"
    assert "Eres un experto en optimización de CVs" in system
    assert "{job_description}" in user
    assert "{ats_keywords}" in user
    assert "{cv_content}" in user


@pytest.mark.asyncio
async def test_suggest_cv_tweaks_success(
    mock_job: Job, mock_cv_variant: CVVariant, mock_ats_keywords: ATSKeywordsResult
) -> None:
    llm_client = MagicMock(spec=AnthropicLLMClient)

    tweaks_response = {
        "tweaks": [
            {
                "type": "add_keyword",
                "target": "Skills",
                "original": None,
                "suggested": "FastAPI",
                "rationale": "FastAPI is a must-have for this role.",
            },
            {
                "type": "rewrite_bullet",
                "target": "Experience at Old Corp",
                "original": "Built stuff",
                "suggested": "Built high-performance APIs using Python and FastAPI",
                "rationale": "Shows direct experience with requested stack.",
            },
        ]
    }

    llm_client.complete = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(tweaks_response),
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.02,
            duration_ms=500,
            stop_reason="end_turn",
        )
    )

    result = await suggest_cv_tweaks(mock_job, mock_cv_variant, mock_ats_keywords, llm_client)

    assert len(result.tweaks) == 2
    assert result.tweaks[0].type == "add_keyword"
    assert result.tweaks[1].type == "rewrite_bullet"
    assert result.model == "claude-sonnet-4-6"
    assert result.cost_usd == 0.02


@pytest.mark.asyncio
async def test_suggest_cv_tweaks_enforces_max_5(
    mock_job: Job, mock_cv_variant: CVVariant, mock_ats_keywords: ATSKeywordsResult
) -> None:
    llm_client = MagicMock(spec=AnthropicLLMClient)

    # Mock 6 tweaks
    tweaks_response = {
        "tweaks": [{"type": "remove", "target": "X", "rationale": "R"} for _ in range(6)]
    }

    llm_client.complete = AsyncMock(
        return_value=LLMResponse(
            text=json.dumps(tweaks_response),
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.02,
            duration_ms=500,
            stop_reason="end_turn",
        )
    )

    result = await suggest_cv_tweaks(mock_job, mock_cv_variant, mock_ats_keywords, llm_client)

    assert len(result.tweaks) == 5
