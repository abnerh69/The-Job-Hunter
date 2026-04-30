"""
Unit tests for outreach message templates.
"""

import pytest
from jobhunter.outreach.templates import load_outreach_template, render_outreach_template


def test_load_all_templates_v1() -> None:
    """
    Test that all four template types can be loaded from v1.
    """
    for t_type in ["A_inhouse", "B_boutique", "C_senior", "D_followup"]:
        template = load_outreach_template(t_type, version="v1")
        assert template.template_type == t_type
        assert template.version == "v1"
        assert "## SYSTEM" not in template.system_prompt
        assert "## USER_TEMPLATE" not in template.user_template
        assert "## REQUIREMENTS" not in template.requirements
        assert len(template.system_prompt) > 0
        assert len(template.user_template) > 0
        assert len(template.requirements) > 0


def test_load_latest_resolves_to_v1() -> None:
    """
    Test that 'latest' resolves to 'v1' (since it's currently the highest).
    """
    template = load_outreach_template("A_inhouse", version="latest")
    assert template.version == "v1"


def test_render_template_success() -> None:
    """
    Test successful rendering of an outreach template.
    """
    template = load_outreach_template("A_inhouse", version="v1")
    context = {
        "contact_name": "John Doe",
        "contact_role": "Tech Recruiter",
        "contact_company": "Acme Corp",
        "research_notes": "Saw your post about the new AI team.",
        "candidate_profile_yaml": "name: Abner\nrole: Senior Engineer",
        "target_language": "en",
    }
    rendered = render_outreach_template(template.user_template, context)
    assert "John Doe" in rendered
    assert "Acme Corp" in rendered
    assert "Saw your post about the new AI team." in rendered


def test_render_template_missing_key() -> None:
    """
    Test rendering fails when a required key is missing from context.
    """
    template = load_outreach_template("A_inhouse", version="v1")
    context = {
        "contact_name": "John Doe",
        # Missing other keys
    }
    with pytest.raises(ValueError, match="Missing required placeholder in context"):
        render_outreach_template(template.user_template, context)


def test_load_non_existent_version() -> None:
    """
    Test loading a non-existent version raises FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError, match="Outreach prompt version v99 not found"):
        load_outreach_template("A_inhouse", version="v99")


def test_load_non_existent_template_type() -> None:
    """
    Test loading a non-existent template type raises FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError, match="Template non_existent not found"):
        load_outreach_template("non_existent", version="v1")
