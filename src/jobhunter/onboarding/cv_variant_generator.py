import json
import re
from datetime import date, datetime
from pathlib import Path

import structlog
from dateutil import parser  # type: ignore[import-untyped]
from jinja2 import Template
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import CandidateProfile, CVVariant, CVVariantExperience
from jobhunter.db.repos.cv_variant import CVVariantRepo
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.onboarding.resume_ingestor import ResumeData

logger = structlog.get_logger(__name__)


class VariantSpec(BaseModel):
    """Specification for a CV variant provided by the user."""

    name: str = Field(..., description="Machine-friendly name, e.g., 'ai_python_engineer'")
    display_name: str = Field(..., description="Human-friendly name, e.g., 'AI Python Engineer'")
    target_role_keywords: list[str] = Field(
        default_factory=list, description="Keywords related to the target role"
    )
    target_stack: list[str] = Field(
        default_factory=list, description="Key technologies for this variant"
    )
    target_seniority: str | None = Field(None, description="Target seniority level")
    angle_description: str = Field(
        ..., description="The specific focus or angle for this CV variant"
    )


def cv_variant_to_markdown(variant: CVVariant) -> str:
    """
    Renders a CVVariant model into a formatted Markdown string.

    Args:
        variant: The CVVariant model (with experiences loaded).

    Returns:
        A Markdown string representing the CV.
    """
    lines = []
    lines.append(f"# {variant.display_name or variant.name}")
    lines.append("")

    if variant.summary:
        lines.append("## SUMMARY")
        lines.append(variant.summary)
        lines.append("")

    if variant.target_stack or variant.skills:
        lines.append("## STACK & SKILLS")
        if variant.target_stack:
            lines.append(f"**Target Stack**: {', '.join(variant.target_stack)}")
        if variant.skills:
            lines.append(f"**Key Skills**: {', '.join(variant.skills)}")
        lines.append("")

    if variant.experiences:
        lines.append("## EXPERIENCE")
        for exp in variant.experiences:
            start_str = exp.start_date.strftime("%Y-%m") if exp.start_date else "Unknown"
            end_str = exp.end_date.strftime("%Y-%m") if exp.end_date else "Present"
            header = f"### {exp.role} | {exp.company} | {start_str} - {end_str}"
            lines.append(header)
            for bullet in exp.bullets or []:
                lines.append(f"- {bullet}")
            lines.append("")

    return "\n".join(lines)


def _parse_cv_dates(date_str: str | None) -> tuple[date | None, date | None]:
    """
    Heuristically parses a date range string into start and end dates.
    Example: '2020-2023', 'Jan 2020 - Present', '2019/01 to 2022/05'
    """
    if not date_str:
        return None, None

    # Common separators
    separators = [r"\s*-\s*", r"\s+to\s+", r"\s*–\s*"]
    parts = []
    for sep in separators:
        if re.search(sep, date_str, re.IGNORECASE):
            parts = re.split(sep, date_str, flags=re.IGNORECASE)
            break

    if not parts:
        # Try to parse as a single date
        try:
            dt = parser.parse(date_str, default=datetime(2000, 1, 1))
            return dt.date(), None
        except (ValueError, OverflowError):
            return None, None

    start_date = None
    end_date = None

    try:
        start_date = parser.parse(parts[0], default=datetime(2000, 1, 1)).date()
    except (ValueError, OverflowError):
        pass

    if len(parts) > 1:
        end_part = parts[1].strip().lower()
        if end_part in ["present", "current", "now", "today"]:
            end_date = None
        else:
            try:
                end_date = parser.parse(parts[1], default=datetime(2000, 1, 1)).date()
            except (ValueError, OverflowError):
                pass

    return start_date, end_date


async def generate_variant(
    profile: CandidateProfile,
    resume_data: ResumeData,
    variant_spec: VariantSpec,
    session: Session,
    llm_client: AnthropicLLMClient,
) -> CVVariant:
    """
    Generates a targeted CV variant using LLM and persists it to the database.

    Args:
        profile: The candidate's general profile.
        resume_data: The full extracted resume data.
        variant_spec: The user-provided specification for the variant.
        session: The SQLAlchemy session.
        llm_client: The Anthropic LLM client.

    Returns:
        The created and persisted CVVariant.
    """
    # 1. Prepare Prompt
    prompt_path = Path("prompts/onboarding/cv_variant_generator/v1.md")
    with open(prompt_path, "r") as f:
        prompt_template = Template(f.read())

    profile_json = json.dumps(
        {
            "name": profile.name,
            "seniority": profile.seniority,
            "years_experience": profile.years_experience,
            "country": profile.country,
        }
    )
    resume_json = resume_data.model_dump_json(exclude={"raw_text"})
    variant_spec_json = variant_spec.model_dump_json()

    system_prompt = prompt_template.render(
        profile_json=profile_json,
        resume_data_json=resume_json,
        variant_spec_json=variant_spec_json,
    )

    # 2. LLM Call
    response = await llm_client.complete(
        system=system_prompt,
        user="Generate the targeted CV variant JSON.",
        model="claude-3-5-sonnet-20241022",
        purpose=LLMPurpose.CV_VARIANT_GENERATION,
        session=session,
        prompt_version="v1",
    )

    try:
        variant_data = json.loads(response.text)
    except json.JSONDecodeError as e:
        logger.error("cv_variant_llm_json_parse_failed", error=str(e), raw_response=response.text)
        raise ValueError(f"Failed to parse LLM response as JSON: {str(e)}")

    # 3. Persistence (Atomic Transaction)
    repo = CVVariantRepo(session)

    # We use a nested transaction (savepoint) to ensure atomicity for this specific variant
    # though usually the caller manages the session transaction.
    # To follow AC "In a transaction, INSERT in cv_variants + N INSERT in cv_variant_experiences. If falla cualquiera, rollback."
    try:
        with session.begin_nested():
            variant = CVVariant(
                profile_id=profile.id,
                name=variant_spec.name,
                display_name=variant_spec.display_name,
                target_role_keywords=variant_spec.target_role_keywords,
                target_stack=variant_spec.target_stack,
                target_seniority=variant_spec.target_seniority,
                summary=variant_data.get("summary"),
                skills=variant_data.get("skills"),
            )

            experiences = []
            for i, exp_data in enumerate(variant_data.get("experiences", [])):
                start_date, end_date = _parse_cv_dates(exp_data.get("dates"))
                exp = CVVariantExperience(
                    role=exp_data.get("role"),
                    company=exp_data.get("company"),
                    start_date=start_date,
                    end_date=end_date,
                    bullets=exp_data.get("bullets"),
                    sort_order=i,
                )
                experiences.append(exp)

            repo.create_with_experiences(variant, experiences)

            # 4. Render and update Markdown
            variant.raw_markdown = cv_variant_to_markdown(variant)
            session.flush()

            logger.info(
                "cv_variant_generated",
                profile_id=str(profile.id),
                variant_name=variant.name,
                experience_count=len(experiences),
            )
            return variant

    except Exception as e:
        logger.error("cv_variant_persistence_failed", error=str(e))
        session.rollback()
        raise
