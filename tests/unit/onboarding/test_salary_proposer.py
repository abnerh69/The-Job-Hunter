import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from jobhunter.db.models import CandidateProfile
from jobhunter.llm.anthropic_client import AnthropicLLMClient, LLMResponse
from jobhunter.onboarding.resume_ingestor import ResumeData
from jobhunter.onboarding.salary_proposer import SalaryProposal, propose_salary


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock(spec=AnthropicLLMClient)
    client.complete = AsyncMock()
    return client


@pytest.fixture
def sample_profile() -> MagicMock:
    profile = MagicMock(spec=CandidateProfile)
    profile.id = "test-profile-id"
    profile.seniority = "senior"
    profile.years_experience = 10
    profile.country = "Mexico"
    profile.primary_stack = ["Python", "FastAPI"]
    profile.contract_preferences = ["B2B"]
    return profile


@pytest.fixture
def sample_resume_data() -> MagicMock:
    resume = MagicMock(spec=ResumeData)
    resume.summary = "Experienced Python developer with 10 years of experience."
    return resume


@pytest.mark.asyncio
async def test_propose_salary_success(
    mock_llm_client: MagicMock, sample_profile: MagicMock, sample_resume_data: MagicMock
) -> None:
    # Mock LLM response
    mock_response = LLMResponse(
        text=json.dumps(
            {
                "currency": "USD",
                "period": "year",
                "floor": 80000,
                "target": 100000,
                "stretch": 120000,
                "rationale": "Strong experience in Python.",
                "data_sources": ["llm_baseline_2026"],
                "confidence": 0.85,
            }
        ),
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        duration_ms=500,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = mock_response

    proposal = await propose_salary(sample_profile, sample_resume_data, mock_llm_client)

    assert isinstance(proposal, SalaryProposal)
    assert proposal.currency == "USD"
    assert proposal.floor == 80000
    assert proposal.target == 100000
    assert proposal.stretch == 120000
    assert "Python" in proposal.rationale
    assert proposal.confidence == 0.85


@pytest.mark.asyncio
async def test_propose_salary_parsing_error(
    mock_llm_client: MagicMock, sample_profile: MagicMock, sample_resume_data: MagicMock
) -> None:
    # Mock invalid LLM response
    mock_response = LLMResponse(
        text="Invalid JSON",
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        duration_ms=500,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = mock_response

    with pytest.raises(ValueError, match="Failed to parse salary proposal"):
        await propose_salary(sample_profile, sample_resume_data, mock_llm_client)


@pytest.mark.asyncio
async def test_propose_salary_with_market_data(
    mock_llm_client: MagicMock, sample_profile: MagicMock, sample_resume_data: MagicMock
) -> None:
    # Mock market data source
    market_source = AsyncMock()
    market_source.get_salary_data.return_value = {"median": 95000}

    # Mock LLM response
    mock_response = LLMResponse(
        text=json.dumps(
            {
                "currency": "USD",
                "period": "year",
                "floor": 85000,
                "target": 95000,
                "stretch": 110000,
                "rationale": "Based on market data.",
                "data_sources": ["market_data"],
                "confidence": 0.95,
            }
        ),
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.01,
        duration_ms=500,
        stop_reason="end_turn",
    )
    mock_llm_client.complete.return_value = mock_response

    proposal = await propose_salary(
        sample_profile, sample_resume_data, mock_llm_client, market_data_source=market_source
    )

    assert proposal.target == 95000
    market_source.get_salary_data.assert_called_once_with(sample_profile)
