"""
Core logic for loading and rendering versioned outreach message templates.
"""

import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class OutreachTemplate(BaseModel):
    """
    Schema for a loaded outreach message template.
    """

    template_type: str
    version: str
    system_prompt: str
    user_template: str
    requirements: str
    loaded_from: str


def load_outreach_template(template_type: str, version: str = "latest") -> OutreachTemplate:
    """
    Loads a versioned outreach message template from the prompts/outreach/vN/ directory.

    Args:
        template_type: The type of template (e.g., 'A_inhouse', 'B_boutique', etc.)
        version: The version directory to load from (e.g., 'v1'). If 'latest',
                 resolves to the directory with the highest version number.

    Returns:
        An OutreachTemplate object containing the parsed sections.

    Raises:
        FileNotFoundError: If the directory or template file is not found.
        ValueError: If the template file has an invalid format.
    """
    base_path = Path("prompts/outreach")
    if not base_path.exists():
        raise FileNotFoundError(f"Outreach prompts directory not found: {base_path}")

    # Version resolution
    if version == "latest":
        v_dirs = [d for d in base_path.glob("v*") if d.is_dir()]
        if not v_dirs:
            raise FileNotFoundError(f"No versioned directories found in {base_path}")

        def get_v_num(p: Path) -> int:
            match = re.search(r"v(\d+)", p.name)
            return int(match.group(1)) if match else -1

        latest_dir = max(v_dirs, key=get_v_num)
        target_dir = latest_dir
        target_version = f"v{get_v_num(latest_dir)}"
    else:
        target_dir = base_path / version
        target_version = version

    if not target_dir.exists():
        raise FileNotFoundError(f"Outreach prompt version {version} not found at {target_dir}")

    target_file = target_dir / f"{template_type}.md"
    if not target_file.exists():
        raise FileNotFoundError(
            f"Template {template_type} not found for version {target_version} at {target_file}"
        )

    content = target_file.read_text(encoding="utf-8")

    # Parse headers ## SYSTEM, ## USER_TEMPLATE, and ## REQUIREMENTS
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
            "Must contain ## SYSTEM, ## USER_TEMPLATE, and ## REQUIREMENTS headers."
        )

    return OutreachTemplate(
        template_type=template_type,
        version=target_version,
        system_prompt=system_match.group(1).strip(),
        user_template=user_match.group(1).strip(),
        requirements=requirements_match.group(1).strip(),
        loaded_from=str(target_file),
    )


def render_outreach_template(template_str: str, context: dict[str, Any]) -> str:
    """
    Renders an outreach template string using the provided context.

    Args:
        template_str: The template string with placeholders like {placeholder}.
        context: A dictionary of values to fill in the placeholders.

    Returns:
        The rendered string.

    Raises:
        ValueError: If a required placeholder is missing in the context.
    """
    try:
        return template_str.format_map(context)
    except KeyError as e:
        raise ValueError(f"Missing required placeholder in context: {e}") from e
