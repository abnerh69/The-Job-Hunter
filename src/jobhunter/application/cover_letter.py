"""
Core logic for generating and validating cover letters.
"""

import re
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobhunter.application.cv import CVVariant
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import Application, Job
from jobhunter.llm.anthropic_client import AnthropicLLMClient

logger = structlog.get_logger(__name__)


class CoverLetterPrompt(BaseModel):
    """
    Schema for a loaded cover letter prompt.
    """

    version: str
    system_prompt: str
    user_template: str
    loaded_from: str


class CoverLetterResult(BaseModel):
    """
    Result of a cover letter generation.
    """

    text: str
    model: str
    prompt_version: str
    cost_usd: float
    word_count: int


def load_cover_letter_prompt(version: str = "latest") -> CoverLetterPrompt:
    """
    Loads a versioned cover letter prompt from the prompts/cover_letter/ directory.
    """
    base_path = Path("prompts/cover_letter")
    if not base_path.exists():
        raise FileNotFoundError(f"Cover letter prompt directory not found: {base_path}")

    files = list(base_path.glob("v*.md"))
    if not files:
        raise FileNotFoundError(f"No cover letter prompt versions found in {base_path}")

    if version == "latest":

        def get_v_num(p: Path) -> int:
            match = re.search(r"v(\d+)", p.name)
            return int(match.group(1)) if match else -1

        latest_file = max(files, key=get_v_num)
        target_file = latest_file
        target_version = f"v{get_v_num(latest_file)}"
    else:
        target_file = base_path / f"{version}.md"
        target_version = version

    if not target_file.exists():
        raise FileNotFoundError(f"Cover letter prompt version {version} not found at {target_file}")

    content = target_file.read_text(encoding="utf-8")

    # Parse headers ## SYSTEM and ## USER_TEMPLATE
    system_match = re.search(
        r"## SYSTEM\s*(.*?)\s*(?=## USER_TEMPLATE|$)", content, re.DOTALL | re.IGNORECASE
    )
    user_match = re.search(r"## USER_TEMPLATE\s*(.*)", content, re.DOTALL | re.IGNORECASE)

    if not system_match or not user_match:
        raise ValueError(
            f"Invalid prompt file format in {target_file}. "
            "Must contain ## SYSTEM and ## USER_TEMPLATE headers."
        )

    return CoverLetterPrompt(
        version=target_version,
        system_prompt=system_match.group(1).strip(),
        user_template=user_match.group(1).strip(),
        loaded_from=str(target_file),
    )


def render_cover_letter_prompt(template: str, data: dict[str, Any]) -> str:
    """
    Renders the cover letter prompt template.
    """
    try:
        return template.format_map(data)
    except KeyError as e:
        raise ValueError(f"Missing required placeholder in data: {e}") from e


def validate_cover_letter(text: str, forbidden_phrases: list[str]) -> list[str]:
    """
    Validates the generated cover letter.
    Returns a list of validation errors, or an empty list if valid.
    """
    errors = []

    # Word count check (250-450)
    word_count = len(text.split())
    if word_count < 250 or word_count > 450:
        errors.append(f"Word count {word_count} is outside the allowed range [250, 450].")

    # Placeholder check
    placeholders = re.findall(r"\[.*?\]", text)
    if placeholders:
        errors.append(f"Found placeholders in text: {', '.join(set(placeholders))}")

    # Forbidden phrases check
    for phrase in forbidden_phrases:
        if phrase.lower() in text.lower():
            errors.append(f"Found forbidden phrase: '{phrase}'")

    return errors


async def generate_cover_letter(
    job: Job,
    cv_variant: CVVariant,
    llm_client: AnthropicLLMClient,
    model: str,
    prompt_version: str = "latest",
    session: Session | None = None,
) -> CoverLetterResult:
    """
    Generates a cover letter for a job using a CV variant and an LLM.
    """
    prompt = load_cover_letter_prompt(prompt_version)
    forbidden_phrases_path = Path("prompts/cover_letter/forbidden_phrases.txt")
    forbidden_phrases = (
        forbidden_phrases_path.read_text().splitlines() if forbidden_phrases_path.exists() else []
    )
    forbidden_phrases = [p.strip() for p in forbidden_phrases if p.strip()]

    # Truncate JD
    max_jd_chars = 6000
    jd_truncated = job.description
    if len(jd_truncated) > max_jd_chars:
        jd_truncated = jd_truncated[:max_jd_chars] + "..."

    # Extract angle
    cover_letter_angle = ""
    if job.score_data and "recommendation" in job.score_data:
        cover_letter_angle = job.score_data["recommendation"].get("cover_letter_angle", "")

    data = {
        "title": job.title,
        "company": job.company,
        "description": jd_truncated,
        "cv_markdown": cv_variant.raw_markdown,
        "cover_letter_angle": cover_letter_angle,
    }

    user_prompt = render_cover_letter_prompt(prompt.user_template, data)
    system_prompt = prompt.system_prompt

    async def call_llm(extra_instruction: str = "") -> CoverLetterResult:
        final_system = system_prompt
        if extra_instruction:
            final_system += f"\n\nIMPORTANT: {extra_instruction}"

        response = await llm_client.complete(
            system=final_system,
            user=user_prompt,
            model=model,
            purpose=LLMPurpose.COVER_LETTER,
            job_id=job.id,
            prompt_version=prompt.version,
            session=session,
            max_tokens=1000,
        )

        return CoverLetterResult(
            text=response.text.strip(),
            model=model,
            prompt_version=prompt.version,
            cost_usd=response.cost_usd,
            word_count=len(response.text.split()),
        )

    # First attempt
    result = await call_llm()
    errors = validate_cover_letter(result.text, forbidden_phrases)

    if errors:
        logger.warning(
            "cover_letter_validation_failed",
            job_id=str(job.id),
            errors=errors,
            attempt=1,
        )
        # Retry with reinforced instruction
        reinforced_instruction = (
            "Your previous attempt failed validation for the following reasons:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nPlease rewrite the cover letter strictly following all rules, "
            "especially addressing the issues above."
        )
        result = await call_llm(extra_instruction=reinforced_instruction)
        # Final validation (logging only)
        final_errors = validate_cover_letter(result.text, forbidden_phrases)
        if final_errors:
            logger.error(
                "cover_letter_validation_failed_final",
                job_id=str(job.id),
                errors=final_errors,
                attempt=2,
            )

    # Persistence logic (Step 5 of plan)
    if session:
        from sqlalchemy import select

        stmt = select(Application).where(Application.job_id == job.id)
        app = session.execute(stmt).scalar_one_or_none()
        if app:
            app.cover_letter_text = result.text
            app.cover_letter_model = model
            session.commit()
            logger.info("cover_letter_persisted", job_id=str(job.id), app_id=str(app.id))

    return result
