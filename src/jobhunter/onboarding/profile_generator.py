import json
from pathlib import Path

import structlog
from jinja2 import Template
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import CandidateProfile
from jobhunter.db.repos.candidate_profile import CandidateProfileRepo
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.onboarding.resume_ingestor import ResumeData

logger = structlog.get_logger(__name__)


class ProfileUserInputs(BaseModel):
    """Contextual inputs provided by the user that the IA cannot infer from the resume alone."""

    country: str = Field(
        ..., description="Country where the candidate is located or wants to work."
    )
    work_authorization: str = Field(
        ..., description="Work authorization status (e.g., 'US Citizen', 'Sponsorship needed')."
    )
    timezone_home: str = Field(
        ..., description="The candidate's home timezone (e.g., 'CET', 'EST')."
    )
    overlap_max_hours_cet: int = Field(
        ..., description="Maximum hours of overlap with CET timezone."
    )
    contract_preferences: list[str] = Field(
        default_factory=list,
        description="Preferred contract types (e.g., 'Full-time', 'Contract').",
    )
    hard_blockers: list[str] = Field(
        default_factory=list,
        description="Non-negotiable constraints (e.g., 'No crypto', 'Remote only').",
    )
    payment_methods_ok: list[str] = Field(
        default_factory=list,
        description="Acceptable payment methods (e.g., 'Bank Transfer', 'Deel').",
    )
    profile_name: str = Field(
        ..., description="A descriptive name for this profile (e.g., 'Python AI Senior')."
    )


async def generate_profile(
    resume_data: ResumeData,
    user_inputs: ProfileUserInputs,
    session: Session,
    llm_client: AnthropicLLMClient,
) -> CandidateProfile:
    """
    Transforms extracted ResumeData and interactive user inputs into a persisted CandidateProfile.

    Args:
        resume_data: The structured data extracted from the resume.
        user_inputs: The contextual inputs provided by the user.
        session: The SQLAlchemy session for database operations.
        llm_client: The Anthropic LLM client for profile inference.

    Returns:
        The newly created CandidateProfile entity.
    """
    # 1. Prepare Prompt
    prompt_path = Path("prompts/onboarding/profile_generator/v1.md")
    with open(prompt_path, "r") as f:
        prompt_template = Template(f.read())

    # Filter out raw_text from resume_data for the prompt to save tokens if needed,
    # but here we follow the AC to use resume_data.
    resume_json = resume_data.model_dump_json(exclude={"raw_text"})
    user_inputs_json = user_inputs.model_dump_json()

    system_prompt = prompt_template.render(
        resume_data_json=resume_json, user_inputs_json=user_inputs_json
    )

    # 2. LLM Inference
    # Using 'claude-sonnet-4-6' as identified in the codebase as the standard Sonnet model
    response = await llm_client.complete(
        system=system_prompt,
        user="Generate the candidate profile JSON based on the provided data.",
        model="claude-sonnet-4-6",
        purpose=LLMPurpose.PROFILE_GENERATION,
        session=session,
        prompt_version="v1",
    )

    try:
        inferred_data = json.loads(response.text)
    except json.JSONDecodeError as e:
        logger.error("profile_llm_json_parse_failed", error=str(e), raw_response=response.text)
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")

    # 3. Validation Cross-check
    llm_years = inferred_data.get("years_experience")
    resume_years = resume_data.detected_years_experience
    if llm_years is not None and resume_years is not None and llm_years != resume_years:
        logger.warning(
            "profile_experience_mismatch",
            llm_years=llm_years,
            resume_years=resume_years,
            msg="LLM inferred years of experience differs from resume ingestion detection.",
        )

    # 4. Language Logic
    # Defaults: "native" if it's the language of the country declared, "fluent" otherwise.
    # Simple heuristic: if country name is in the language name or vice versa.
    # Also handle common cases like "Spain" -> "Spanish".
    languages_dict = {}
    country_lower = user_inputs.country.lower()

    country_to_lang = {
        "spain": "spanish",
        "germany": "german",
        "france": "french",
        "italy": "italian",
        "united kingdom": "english",
        "usa": "english",
        "united states": "english",
    }

    target_lang = country_to_lang.get(country_lower, country_lower)

    for lang in resume_data.languages:
        lang_lower = lang.lower()
        # VERY basic heuristic for "native"
        if target_lang in lang_lower or lang_lower in target_lang:
            languages_dict[lang] = "native"
        else:
            languages_dict[lang] = "fluent"

    # 5. Build CandidateProfile
    profile = CandidateProfile(
        name=user_inputs.profile_name,
        seniority=inferred_data.get("seniority"),
        years_experience=inferred_data.get("years_experience"),
        country=user_inputs.country,
        work_authorization=user_inputs.work_authorization,
        timezone_home=user_inputs.timezone_home,
        overlap_max_hours_cet=user_inputs.overlap_max_hours_cet,
        primary_stack=inferred_data.get("primary_stack", []),
        secondary_stack=inferred_data.get("secondary_stack", []),
        domains=inferred_data.get("domains", []),
        languages=languages_dict,
        contract_preferences=user_inputs.contract_preferences,
        hard_blockers=user_inputs.hard_blockers,
        positive_signals=inferred_data.get("positive_signals", []),
        soft_negatives=inferred_data.get("soft_negatives", []),
        payment_methods_ok=user_inputs.payment_methods_ok,
        compensation=None,  # Explicitly NULL as per AC
    )

    logger.info(
        "candidate_profile_generated",
        profile_name=profile.name,
    )

    return profile
