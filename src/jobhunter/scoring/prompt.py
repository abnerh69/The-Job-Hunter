"""
Loader and renderer for versioned scoring prompts.

This module handles loading prompt templates from versioned markdown files
and rendering them with job data for use with AI models.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class PromptRenderError(Exception):
    """Raised when there is an error rendering the prompt template."""


class ScoringPrompt(BaseModel):
    """
    Schema for a loaded scoring prompt.

    Attributes:
        version: The version string of the prompt (e.g., 'v1').
        system_prompt: The system-level instructions for the AI.
        user_template: The template for the user message, containing placeholders.
        loaded_from: The file path the prompt was loaded from.
    """

    version: str
    system_prompt: str
    user_template: str
    loaded_from: str


def load_prompt(version: str = "latest") -> ScoringPrompt:
    """
    Loads a versioned prompt from the prompts/scoring/ directory.

    Args:
        version: The version to load (e.g., 'v1', 'v2') or 'latest' for the
            highest version found.

    Returns:
        A ScoringPrompt instance.

    Raises:
        FileNotFoundError: If the specified version or any version (if 'latest')
            is not found.
        ValueError: If the prompt file format is invalid.
    """
    base_path = Path("prompts/scoring")
    if not base_path.exists():
        raise FileNotFoundError(f"Prompt directory not found: {base_path}")

    files = list(base_path.glob("v*.md"))
    if not files:
        raise FileNotFoundError(f"No prompt versions found in {base_path}")

    if version == "latest":
        # Extract version numbers and find the max
        # Assumes format v[number].md
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
        raise FileNotFoundError(f"Prompt version {version} not found at {target_file}")

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

    return ScoringPrompt(
        version=target_version,
        system_prompt=system_match.group(1).strip(),
        user_template=user_match.group(1).strip(),
        loaded_from=str(target_file),
    )


def render_user_prompt(template: str, job_data: dict[str, Any]) -> str:
    """
    Renders the user prompt template by substituting placeholders with job data.

    Args:
        template: The prompt template string with {placeholders}.
        job_data: A dictionary containing job attributes. Expected keys:
            title, company, description, source, url, scraped_at, location_raw.

    Returns:
        The rendered prompt string.

    Raises:
        PromptRenderError: If a required placeholder is missing from job_data.
    """
    # Prepare data for format_map
    data = {}
    for key, value in job_data.items():
        if isinstance(value, datetime):
            data[key] = value.isoformat()
        else:
            data[key] = value if value is not None else ""

    try:
        return template.format_map(data)
    except KeyError as e:
        raise PromptRenderError(f"Missing required placeholder in job data: {e}") from e
