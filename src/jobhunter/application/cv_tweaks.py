"""
Logic for suggesting CV tweaks to improve match with a specific job description.
"""

import json
import re
from pathlib import Path
from typing import Literal, Optional

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from jobhunter.application.ats_keywords import ATSKeywordsResult
from jobhunter.application.cv import CVVariant
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import Job
from jobhunter.llm.base import LLMClient

logger = structlog.get_logger(__name__)

TweakType = Literal["reorder_bullet", "add_keyword", "rewrite_bullet", "add_section", "remove"]


class Tweak(BaseModel):
    """
    A specific suggestion to improve the CV.
    """

    type: TweakType
    target: str
    original: Optional[str] = None
    suggested: Optional[str] = None
    rationale: str


class CVTweaksResult(BaseModel):
    """
    Result of the CV tweaks suggestion process.
    """

    model_config = ConfigDict(extra="forbid")

    tweaks: list[Tweak]
    model: str
    prompt_version: str
    cost_usd: float


def load_cv_tweaks_prompt(version: str = "latest") -> tuple[str, str, str]:
    """
    Loads a versioned CV tweaks prompt.
    Returns: (version, system_prompt, user_template)
    """
    base_path = Path("prompts/cv_tweaks")
    if not base_path.exists():
        raise FileNotFoundError(f"CV tweaks prompt directory not found: {base_path}")

    files = list(base_path.glob("v*.md"))
    if not files:
        raise FileNotFoundError(f"No CV tweaks prompt versions found in {base_path}")

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
        raise FileNotFoundError(f"CV tweaks prompt version {version} not found at {target_file}")

    content = target_file.read_text(encoding="utf-8")

    system_match = re.search(
        r"## SYSTEM\s*(.*?)\s*(?=## USER_TEMPLATE|$)", content, re.DOTALL | re.IGNORECASE
    )
    user_match = re.search(r"## USER_TEMPLATE\s*(.*)", content, re.DOTALL | re.IGNORECASE)

    if not system_match or not user_match:
        raise ValueError(f"Invalid prompt file format in {target_file}")

    return target_version, system_match.group(1).strip(), user_match.group(1).strip()


async def suggest_cv_tweaks(
    job: Job,
    cv_variant: CVVariant,
    ats_keywords: ATSKeywordsResult,
    llm_client: LLMClient,
    session: Session | None = None,
    prompt_version: str = "latest",
    model: str = "claude-sonnet-4-6",
) -> CVTweaksResult:
    """
    Suggests actionable tweaks for a CV to match a specific job description.

    Args:
        job: The job to match against.
        cv_variant: The current CV variant.
        ats_keywords: Extracted ATS keywords for the job.
        llm_client: The LLM client to use.
        session: Optional DB session to record the call.
        prompt_version: Version of the prompt to use.
        model: The LLM model to use (defaults to Sonnet).

    Returns:
        CVTweaksResult containing up to 5 suggested tweaks.
    """
    version, system_prompt, user_template = load_cv_tweaks_prompt(prompt_version)

    # Format keywords for the prompt
    must_have = [f"- {kw.term} (weight: {kw.weight})" for kw in ats_keywords.must_have]
    nice_to_have = [f"- {kw.term} (weight: {kw.weight})" for kw in ats_keywords.nice_to_have]
    keywords_str = (
        "MUST HAVE:\n" + "\n".join(must_have) + "\n\nNICE TO HAVE:\n" + "\n".join(nice_to_have)
    )

    # Truncate JD
    max_jd_chars = 8000
    jd_truncated = job.description
    if len(jd_truncated) > max_jd_chars:
        jd_truncated = jd_truncated[:max_jd_chars] + "..."

    user_prompt = user_template.format(
        job_description=f"TITLE: {job.title}\nCOMPANY: {job.company}\n\n{jd_truncated}",
        ats_keywords=keywords_str,
        cv_content=cv_variant.raw_markdown,
    )

    response = await llm_client.complete(
        system=system_prompt,
        user=user_prompt,
        model=model,
        purpose=LLMPurpose.CV_TWEAKS,
        job_id=job.id,
        prompt_version=version,
        session=session,
        max_tokens=1500,
    )

    try:
        data = json.loads(response.text.strip())
        tweaks_data = data.get("tweaks", [])

        # Enforce max 5 tweaks and order
        tweaks = [Tweak(**t) for t in tweaks_data[:5]]

        return CVTweaksResult(
            tweaks=tweaks,
            model=model,
            prompt_version=version,
            cost_usd=response.cost_usd,
        )

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("cv_tweaks_parse_failed", error=str(e), raw_response=response.text)
        raise
