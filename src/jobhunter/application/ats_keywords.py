"""
Logic for extracting ATS keywords from job descriptions and checking their presence in CVs.
"""

import json
import re
from pathlib import Path
from typing import Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from jobhunter.application.cv import CVVariant
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import Job
from jobhunter.llm.base import LLMClient

logger = structlog.get_logger(__name__)

# Hardcoded synonyms for v1
KEYWORD_SYNONYMS: dict[str, list[str]] = {
    "Python": ["Python 3", "Py3", "CPython"],
    "Flutter": ["Flutter SDK", "Dart/Flutter"],
    "AWS": ["Amazon Web Services", "Amazon AWS"],
    "Kubernetes": ["K8s"],
    "Docker": ["Docker Containers"],
    "PostgreSQL": ["Postgres", "PSQL"],
    "TypeScript": ["TS"],
    "JavaScript": ["JS", "ES6"],
    "React": ["React.js", "ReactJS"],
    "Artificial Intelligence": ["AI", "IA"],
    "Machine Learning": ["ML"],
}

KeywordCategory = Literal["technical", "soft", "certification", "tool", "methodology"]


class Keyword(BaseModel):
    """
    Represents an ATS keyword.
    """

    term: str
    category: KeywordCategory
    weight: int = Field(ge=1, le=10)
    present_in_cv: bool = False


class ATSKeywordsResult(BaseModel):
    """
    Result of an ATS keyword extraction.
    """

    model_config = ConfigDict(extra="forbid")

    must_have: list[Keyword]
    nice_to_have: list[Keyword]
    model: str
    prompt_version: str
    cost_usd: float


def load_ats_prompt(version: str = "latest") -> tuple[str, str, str]:
    """
    Loads a versioned ATS keyword prompt.
    Returns: (version, system_prompt, user_template)
    """
    base_path = Path("prompts/ats_keywords")
    if not base_path.exists():
        raise FileNotFoundError(f"ATS prompt directory not found: {base_path}")

    files = list(base_path.glob("v*.md"))
    if not files:
        raise FileNotFoundError(f"No ATS prompt versions found in {base_path}")

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
        raise FileNotFoundError(f"ATS prompt version {version} not found at {target_file}")

    content = target_file.read_text(encoding="utf-8")

    system_match = re.search(
        r"## SYSTEM\s*(.*?)\s*(?=## USER_TEMPLATE|$)", content, re.DOTALL | re.IGNORECASE
    )
    user_match = re.search(r"## USER_TEMPLATE\s*(.*)", content, re.DOTALL | re.IGNORECASE)

    if not system_match or not user_match:
        raise ValueError(f"Invalid prompt file format in {target_file}")

    return target_version, system_match.group(1).strip(), user_match.group(1).strip()


def _check_presence_in_cv(term: str, cv_text: str) -> bool:
    """
    Checks if a keyword (or its synonyms) is present in the CV text.
    Case-insensitive substring matching.
    """
    cv_text_lower = cv_text.lower()

    # Check original term
    # We use word boundaries to avoid partial matches like "Java" in "JavaScript"
    # though for some keywords substring might be better. Let's start with flexible regex.
    pattern = rf"\b{re.escape(term.lower())}\b"
    if re.search(pattern, cv_text_lower):
        return True

    # Check synonyms
    synonyms = KEYWORD_SYNONYMS.get(term, [])
    for syn in synonyms:
        pattern = rf"\b{re.escape(syn.lower())}\b"
        if re.search(pattern, cv_text_lower):
            return True

    return False


async def extract_ats_keywords(
    job: Job,
    llm_client: LLMClient,
    cv_variant: CVVariant | None = None,
    session: Session | None = None,
    prompt_version: str = "latest",
) -> ATSKeywordsResult:
    """
    Extracts ATS keywords from a job description using an LLM and checks presence in CV.
    """
    version, system_prompt, user_template = load_ats_prompt(prompt_version)

    # Truncate JD to stay safe
    max_jd_chars = 8000
    jd_truncated = job.description
    if len(jd_truncated) > max_jd_chars:
        jd_truncated = jd_truncated[:max_jd_chars] + "..."

    user_prompt = user_template.format(
        title=job.title, company=job.company, description=jd_truncated
    )

    model = "claude-haiku-4-5-20251001"

    response = await llm_client.complete(
        system=system_prompt,
        user=user_prompt,
        model=model,
        purpose=LLMPurpose.ATS_KEYWORDS,
        job_id=job.id,
        prompt_version=version,
        session=session,
        max_tokens=1000,
    )

    try:
        # AnthropicLLMClient might return text with preamble if not careful,
        # but our prompt is strict.
        data = json.loads(response.text.strip())

        must_have = [Keyword(**k) for k in data.get("must_have", [])]
        nice_to_have = [Keyword(**k) for k in data.get("nice_to_have", [])]

        # Post-processing: presence in CV
        if cv_variant:
            cv_text = cv_variant.raw_markdown
            for kw in must_have:
                kw.present_in_cv = _check_presence_in_cv(kw.term, cv_text)
            for kw in nice_to_have:
                kw.present_in_cv = _check_presence_in_cv(kw.term, cv_text)

        # Sort by weight descending
        must_have.sort(key=lambda x: x.weight, reverse=True)
        nice_to_have.sort(key=lambda x: x.weight, reverse=True)

        return ATSKeywordsResult(
            must_have=must_have,
            nice_to_have=nice_to_have,
            model=model,
            prompt_version=version,
            cost_usd=response.cost_usd,
        )

    except (json.JSONDecodeError, ValueError) as e:
        logger.error("ats_keywords_parse_failed", error=str(e), raw_response=response.text)
        raise
