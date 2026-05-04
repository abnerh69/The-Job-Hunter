import json
from pathlib import Path
from typing import Any, Literal, Optional, Protocol

import structlog
from jinja2 import Template
from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import CandidateProfile
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.onboarding.resume_ingestor import ResumeData

logger = structlog.get_logger(__name__)


class SalaryProposal(BaseModel):
    """
    Proposed salary range and rationale.
    """

    currency: Literal["USD", "EUR"]
    period: Literal["month", "year"]
    floor: int
    target: int
    stretch: int
    rationale: str  # Narrative from the LLM
    data_sources: list[str]  # e.g., ["llm_baseline_2026", ...]
    confidence: float  # 0-1


class SalaryDataSource(Protocol):
    """
    Interface for salary data sources.
    """

    async def get_salary_data(self, profile: CandidateProfile) -> dict[str, Any]:
        """
        Retrieves salary data for the given profile.
        """
        ...


async def propose_salary(
    profile: CandidateProfile,
    resume_data: ResumeData,
    llm_client: AnthropicLLMClient,
    market_data_source: Optional[SalaryDataSource] = None,
    session: Optional[Session] = None,
) -> SalaryProposal:
    """
    Proposes a salary range (floor / target / stretch) based on the candidate's profile and experience.

    Args:
        profile: The candidate profile.
        resume_data: The structured resume data.
        llm_client: The Anthropic LLM client.
        market_data_source: Optional data source for real market data (Hook for v2).
        session: Optional SQLAlchemy session for tracking.

    Returns:
        A SalaryProposal object.
    """
    # 1. Prepare Prompt
    prompt_path = Path("prompts/onboarding/salary_proposer/v1.md")
    with open(prompt_path, "r") as f:
        prompt_template = Template(f.read())

    profile_json = {
        "seniority": profile.seniority,
        "years_experience": profile.years_experience,
        "country": profile.country,
        "primary_stack": profile.primary_stack,
        "contract_preferences": profile.contract_preferences,
    }

    # v2 Hook: If market_data_source is provided, we could incorporate its results into the prompt.
    # For now, we just pass None or empty to the template if not implemented.
    market_data = None
    if market_data_source:
        try:
            market_data = await market_data_source.get_salary_data(profile)
        except Exception as e:
            logger.warning("market_data_fetch_failed", error=str(e))

    system_prompt = prompt_template.render(
        profile_json=json.dumps(profile_json),
        resume_summary=resume_data.summary,
        market_data_json=json.dumps(market_data) if market_data else None,
    )

    # 2. LLM Call
    # Using 'claude-sonnet-4-6' as identified in the codebase as the standard Sonnet model
    response = await llm_client.complete(
        system=system_prompt,
        user="Propose a salary range for this candidate in JSON format.",
        model="claude-sonnet-4-6",
        purpose=LLMPurpose.SALARY_PROPOSAL,
        session=session,
        prompt_version="v1",
    )

    # 3. Parse and Validate
    try:
        data = json.loads(response.text)
        proposal = SalaryProposal(**data)
    except Exception as e:
        logger.error("salary_proposal_parsing_failed", error=str(e), raw_response=response.text)
        raise ValueError(f"Failed to parse salary proposal: {str(e)}")

    logger.info(
        "salary_proposal_generated",
        profile_id=str(profile.id),
        floor=proposal.floor,
        target=proposal.target,
        stretch=proposal.stretch,
        currency=proposal.currency,
    )

    return proposal
