"""
Unit tests for the scoring prompt loader and renderer.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from jobhunter.scoring.prompt import (
    PromptRenderError,
    ScoringPrompt,
    load_prompt,
    render_user_prompt,
)


def test_load_prompt_v1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading a specific version of a prompt."""
    prompt_dir = tmp_path / "prompts" / "scoring"
    prompt_dir.mkdir(parents=True)

    v1_content = """## SYSTEM
System instructions
## USER_TEMPLATE
User template with {title}
"""
    v1_file = prompt_dir / "v1.md"
    v1_file.write_text(v1_content)

    # Mock the base path in load_prompt
    monkeypatch.chdir(tmp_path)

    prompt = load_prompt("v1")

    assert isinstance(prompt, ScoringPrompt)
    assert prompt.version == "v1"
    assert prompt.system_prompt == "System instructions"
    assert prompt.user_template == "User template with {title}"
    assert prompt.loaded_from == str(v1_file.relative_to(tmp_path))


def test_load_prompt_latest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test loading the latest version of a prompt."""
    prompt_dir = tmp_path / "prompts" / "scoring"
    prompt_dir.mkdir(parents=True)

    (prompt_dir / "v1.md").write_text("## SYSTEM\nv1 system\n## USER_TEMPLATE\nv1 user")
    (prompt_dir / "v2.md").write_text("## SYSTEM\nv2 system\n## USER_TEMPLATE\nv2 user")
    (prompt_dir / "v10.md").write_text("## SYSTEM\nv10 system\n## USER_TEMPLATE\nv10 user")

    monkeypatch.chdir(tmp_path)

    prompt = load_prompt("latest")

    assert prompt.version == "v10"
    assert prompt.system_prompt == "v10 system"


def test_load_prompt_not_found() -> None:
    """Test error when version file does not exist."""
    with pytest.raises(FileNotFoundError, match="Prompt version v999 not found"):
        load_prompt("v999")


def test_load_prompt_invalid_format(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test error when prompt file lacks required headers."""
    prompt_dir = tmp_path / "prompts" / "scoring"
    prompt_dir.mkdir(parents=True)

    (prompt_dir / "v1.md").write_text("Invalid content")

    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="Invalid prompt file format"):
        load_prompt("v1")


def test_render_user_prompt_success() -> None:
    """Test successful rendering of user prompt with all placeholders."""
    template = "Job: {title} at {company}. Description: {description}. Source: {source} ({url}). Scraped at {scraped_at}. Location: {location_raw}"
    job_data = {
        "title": "Software Engineer",
        "company": "Tech Corp",
        "description": "A great job",
        "source": "LinkedIn",
        "url": "https://linkedin.com/jobs/1",
        "scraped_at": datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "location_raw": "Berlin, Germany",
    }

    rendered = render_user_prompt(template, job_data)

    assert "Job: Software Engineer at Tech Corp" in rendered
    assert "Description: A great job" in rendered
    assert "Source: LinkedIn (https://linkedin.com/jobs/1)" in rendered
    assert "Scraped at 2024-01-01T12:00:00+00:00" in rendered
    assert "Location: Berlin, Germany" in rendered


def test_render_user_prompt_missing_placeholder() -> None:
    """Test error when a required placeholder is missing from job data."""
    template = "Job: {title} at {company}"
    job_data = {"title": "Software Engineer"}  # missing 'company'

    with pytest.raises(
        PromptRenderError, match="Missing required placeholder in job data: 'company'"
    ):
        render_user_prompt(template, job_data)


def test_render_user_prompt_none_values() -> None:
    """Test rendering when some job data values are None."""
    template = "Location: {location_raw}"
    job_data = {"location_raw": None}

    rendered = render_user_prompt(template, job_data)

    assert rendered == "Location: "
