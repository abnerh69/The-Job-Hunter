"""
Loader and renderer for versioned email matcher prompts.
"""

import functools
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class EmailMatcherPrompt(BaseModel):
    """
    Schema for a loaded email matcher prompt.
    """

    version: str
    system_prompt: str
    user_template: str
    requirements: str
    loaded_from: str


@functools.lru_cache(maxsize=1)
def load_email_prompt(version: str = "v1") -> EmailMatcherPrompt:
    """
    Loads a versioned prompt from the prompts/email_matcher/ directory.

    Args:
        version: The version to load (e.g., 'v1').

    Returns:
        An EmailMatcherPrompt instance.

    Raises:
        FileNotFoundError: If the specified version is not found.
        ValueError: If the prompt file format is invalid.
    """
    base_path = Path("prompts/email_matcher")
    target_file = base_path / f"{version}.md"

    if not target_file.exists():
        raise FileNotFoundError(
            f"Email matcher prompt version {version} not found at {target_file}"
        )

    content = target_file.read_text(encoding="utf-8")

    # Parse headers ## SYSTEM, ## USER_TEMPLATE and ## REQUIREMENTS
    system_match = re.search(
        r"## SYSTEM\s*(.*?)\s*(?=## USER_TEMPLATE|$)", content, re.DOTALL | re.IGNORECASE
    )
    user_match = re.search(
        r"## USER_TEMPLATE\s*(.*?)\s*(?=## REQUIREMENTS|$)", content, re.DOTALL | re.IGNORECASE
    )
    requirements_match = re.search(r"## REQUIREMENTS\s*(.*)", content, re.DOTALL | re.IGNORECASE)

    if not system_match or not user_match or not requirements_match:
        raise ValueError(
            f"Invalid prompt file format in {target_file}. "
            "Must contain ## SYSTEM, ## USER_TEMPLATE and ## REQUIREMENTS headers."
        )

    return EmailMatcherPrompt(
        version=version,
        system_prompt=system_match.group(1).strip(),
        user_template=user_match.group(1).strip(),
        requirements=requirements_match.group(1).strip(),
        loaded_from=str(target_file),
    )


def render_email_user_prompt(template: str, context: dict[str, Any]) -> str:
    """
    Renders the email user prompt template by substituting placeholders.

    Args:
        template: The prompt template string with {placeholders}.
        context: A dictionary containing values for placeholders.

    Returns:
        The rendered prompt string.
    """
    try:
        return template.format_map(context)
    except KeyError as e:
        raise ValueError(f"Missing required placeholder in context: {e}") from e
