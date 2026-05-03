import pytest
import uuid
from typing import Any
from unittest.mock import MagicMock, patch, AsyncMock
from typer.testing import CliRunner
from datetime import datetime, timezone

from jobhunter.__main__ import app
from jobhunter.onboarding.resume_ingestor import ResumeData
from jobhunter.onboarding.salary_proposer import SalaryProposal
from jobhunter.db.models import CandidateProfile, CVVariant

runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb"})


@pytest.fixture
def dummy_resume(tmp_path: Any) -> Any:
    resume_path = tmp_path / "resume.md"
    resume_path.write_text("# John Doe\nPython Developer")
    return resume_path


@pytest.fixture
def mock_resume_data() -> ResumeData:
    return ResumeData(
        name="John Doe",
        email="john@example.com",
        experiences=[],
        educations=[],
        skills=["Python", "SQL"],
        languages=["English"],
        detected_primary_stack=["Python"],
        raw_text="John Doe Python Developer",
    )


@pytest.fixture
def mock_profile() -> CandidateProfile:
    profile = CandidateProfile(
        id=uuid.uuid4(),
        name="John Doe's Profile",
        seniority="senior",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    return profile


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.onboarding.resume_ingestor.ingest_resume", new_callable=AsyncMock)
@patch("jobhunter.onboarding.profile_generator.generate_profile", new_callable=AsyncMock)
@patch("jobhunter.onboarding.salary_proposer.propose_salary", new_callable=AsyncMock)
@patch("jobhunter.onboarding.cv_variant_generator.generate_variant", new_callable=AsyncMock)
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
def test_profile_bootstrap_non_interactive(
    mock_profile_repo_cls: MagicMock,
    mock_gen_variant: AsyncMock,
    mock_propose_salary: AsyncMock,
    mock_gen_profile: AsyncMock,
    mock_ingest: AsyncMock,
    mock_get_session: MagicMock,
    dummy_resume: Any,
    mock_resume_data: ResumeData,
    mock_profile: CandidateProfile,
) -> None:
    mock_ingest.return_value = mock_resume_data
    mock_gen_profile.return_value = mock_profile
    mock_propose_salary.return_value = SalaryProposal(
        currency="EUR",
        period="year",
        floor=60000,
        target=70000,
        stretch=80000,
        rationale="Good profile",
        data_sources=["test"],
        confidence=0.9,
    )

    # Mock session.scalar for cost tracking
    mock_session = MagicMock()
    mock_get_session.return_value.__enter__.return_value = mock_session
    mock_session.scalar.return_value = 0.05

    # Mock to_yaml_string
    with patch.object(CandidateProfile, "to_yaml_string", return_value="name: John Doe's Profile"):
        result = runner.invoke(app, ["profile", "bootstrap", "--resume", str(dummy_resume)])

    assert result.exit_code == 0
    assert "Profile Bootstrap Summary" in result.output
    assert str(mock_profile.id) in result.output
    assert "John Doe's Profile" in result.output


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
@patch("jobhunter.db.repos.cv_variant.CVVariantRepo")
def test_profile_list(
    mock_cv_repo_cls: MagicMock,
    mock_profile_repo_cls: MagicMock,
    mock_get_session: MagicMock,
    mock_profile: CandidateProfile,
) -> None:
    mock_profile_repo = MagicMock()
    mock_profile_repo.list.return_value = [mock_profile]
    mock_profile_repo_cls.return_value = mock_profile_repo

    mock_cv_repo = MagicMock()
    mock_cv_repo.list_by_profile.return_value = [MagicMock(id=uuid.uuid4())]
    mock_cv_repo_cls.return_value = mock_cv_repo

    result = runner.invoke(app, ["profile", "list"])

    assert result.exit_code == 0
    assert "Candidate Profiles" in result.output
    assert "John Doe's Profile" in result.output
    assert "YES" in result.output  # Active


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
def test_profile_show(
    mock_repo_cls: MagicMock, mock_get_session: MagicMock, mock_profile: CandidateProfile
) -> None:
    mock_repo = MagicMock()
    mock_repo.get.return_value = mock_profile
    mock_profile_repo_cls = mock_repo_cls
    mock_profile_repo_cls.return_value = mock_repo

    # Mock to_yaml_string
    with patch.object(CandidateProfile, "to_yaml_string", return_value="name: John Doe's Profile"):
        result = runner.invoke(app, ["profile", "show", str(mock_profile.id)])

    assert result.exit_code == 0
    assert "Candidate Profile: John Doe's Profile" in result.output
    assert "name: John Doe's Profile" in result.output


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
def test_profile_activate(
    mock_repo_cls: MagicMock, mock_get_session: MagicMock, mock_profile: CandidateProfile
) -> None:
    mock_repo = MagicMock()
    mock_repo.get.return_value = mock_profile
    mock_repo_cls.return_value = mock_repo

    result = runner.invoke(app, ["profile", "activate", str(mock_profile.id)])

    assert result.exit_code == 0
    assert f"Profile {mock_profile.id} activated." in result.output
    mock_repo.update.assert_called_once_with(mock_profile.id, is_active=True)


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
def test_profile_deactivate(
    mock_repo_cls: MagicMock, mock_get_session: MagicMock, mock_profile: CandidateProfile
) -> None:
    mock_repo = MagicMock()
    mock_repo.get.return_value = mock_profile
    mock_repo_cls.return_value = mock_repo

    result = runner.invoke(app, ["profile", "deactivate", str(mock_profile.id)])

    assert result.exit_code == 0
    assert f"Profile {mock_profile.id} deactivated." in result.output
    mock_repo.update.assert_called_once_with(mock_profile.id, is_active=False)


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
def test_profile_delete_soft(
    mock_repo_cls: MagicMock, mock_get_session: MagicMock, mock_profile: CandidateProfile
) -> None:
    mock_repo = MagicMock()
    mock_repo.get.return_value = mock_profile
    mock_repo_cls.return_value = mock_repo

    result = runner.invoke(app, ["profile", "delete", str(mock_profile.id)])

    assert result.exit_code == 0
    assert "marked as inactive (soft delete)" in result.output
    mock_repo.update.assert_called_once_with(mock_profile.id, is_active=False)


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.db.repos.cv_variant.CVVariantRepo")
def test_profile_variants_list(
    mock_repo_cls: MagicMock, mock_get_session: MagicMock, mock_profile: CandidateProfile
) -> None:
    mock_repo = MagicMock()
    variant = CVVariant(
        id=uuid.uuid4(),
        name="standard",
        display_name="Standard CV",
        created_at=datetime.now(timezone.utc),
    )
    mock_repo.list_by_profile.return_value = [variant]
    mock_repo_cls.return_value = mock_repo

    result = runner.invoke(app, ["profile", "variants", str(mock_profile.id)])

    assert result.exit_code == 0
    assert "CV Variants for Profile" in result.output
    assert str(mock_profile.id) in result.output
    assert "standard" in result.output


@patch("jobhunter.__main__.get_session")
@patch("jobhunter.onboarding.resume_ingestor.ingest_resume", new_callable=AsyncMock)
@patch("jobhunter.onboarding.cv_variant_generator.generate_variant", new_callable=AsyncMock)
@patch("jobhunter.db.repos.candidate_profile.CandidateProfileRepo")
@patch("jobhunter.db.repos.cv_variant.CVVariantRepo")
def test_profile_rebuild_variants_success(
    mock_cv_repo_cls: MagicMock,
    mock_profile_repo_cls: MagicMock,
    mock_gen_variant: AsyncMock,
    mock_ingest: AsyncMock,
    mock_get_session: MagicMock,
    mock_profile: CandidateProfile,
    mock_resume_data: ResumeData,
    dummy_resume: Any,
) -> None:
    mock_profile_repo = MagicMock()
    mock_profile_repo.get.return_value = mock_profile
    mock_profile_repo_cls.return_value = mock_profile_repo

    mock_cv_repo = MagicMock()
    # Return one variant
    variant = MagicMock()
    variant.name = "standard"
    variant.display_name = "Standard CV"
    variant.target_role_keywords = ["Python"]
    variant.target_stack = ["Python"]
    variant.target_seniority = "senior"
    mock_cv_repo.list_by_profile.return_value = [variant]
    mock_cv_repo_cls.return_value = mock_cv_repo

    mock_ingest.return_value = mock_resume_data

    result = runner.invoke(
        app, ["profile", "rebuild-variants", str(mock_profile.id), "--resume", str(dummy_resume)]
    )

    assert result.exit_code == 0
    assert f"Successfully rebuilt 1 variants for profile {mock_profile.id}" in result.output
    assert mock_gen_variant.call_count == 1
