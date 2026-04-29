import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from typer.testing import CliRunner

from jobhunter.__main__ import app
from jobhunter.application.assistant import ApplicationPackage, clear_assistant_cache
from jobhunter.application.ats_keywords import ATSKeywordsResult, Keyword
from jobhunter.application.cover_letter import CoverLetterResult
from jobhunter.application.cv_tweaks import CVTweaksResult, Tweak
from jobhunter.application.variant_selector import VariantRecommendation
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Application, Job

runner = CliRunner()


@pytest.fixture
def mock_package() -> ApplicationPackage:
    job_id = uuid.uuid4()
    return ApplicationPackage(
        job_id=job_id,
        cv_variant=VariantRecommendation(
            variant_name="ai_python", confidence=0.9, reasoning="Matched Python and AI"
        ),
        cover_letter=CoverLetterResult(
            text="Mocked cover letter content",
            model="test-model",
            prompt_version="v1",
            cost_usd=0.01,
            word_count=200,
        ),
        ats_keywords=ATSKeywordsResult(
            must_have=[Keyword(term="Python", category="technical", weight=10, present_in_cv=True)],
            nice_to_have=[],
            model="haiku",
            prompt_version="v1",
            cost_usd=0.001,
        ),
        cv_tweaks=CVTweaksResult(
            tweaks=[
                Tweak(
                    type="rewrite_bullet",
                    target="Experience",
                    suggested="Better bullet",
                    rationale="Impact",
                )
            ],
            model="sonnet",
            prompt_version="v1",
            cost_usd=0.005,
        ),
        total_cost_usd=0.016,
        total_duration_ms=500,
        estimated_apply_time_min=10,
    )


def test_assist_cli_basic(mock_package: ApplicationPackage, tmp_path: Path) -> None:
    job_id = str(mock_package.job_id)

    with (
        patch("jobhunter.__main__.get_session"),
        patch("jobhunter.__main__.AnthropicLLMClient"),
        patch("jobhunter.__main__.assist_application", return_value=mock_package),
    ):
        result = runner.invoke(app, ["assist", job_id])
        assert result.exit_code == 0
        assert "Application Package for Job" in result.stdout
        assert "ai_python" in result.stdout
        assert "Mocked cover letter content" in result.stdout


def test_assist_cli_no_letter(mock_package: ApplicationPackage) -> None:
    job_id = str(mock_package.job_id)
    mock_package.cover_letter = None

    with (
        patch("jobhunter.__main__.get_session"),
        patch("jobhunter.__main__.AnthropicLLMClient"),
        patch("jobhunter.__main__.assist_application", return_value=mock_package) as mock_assist,
    ):
        result = runner.invoke(app, ["assist", job_id, "--no-letter"])
        assert result.exit_code == 0
        assert "Cover Letter" not in result.stdout
        mock_assist.assert_called_once()
        assert mock_assist.call_args.kwargs["no_letter"] is True


def test_assist_cli_output_dir(mock_package: ApplicationPackage, tmp_path: Path) -> None:
    job_id = str(mock_package.job_id)
    output_dir = tmp_path / "output"

    with (
        patch("jobhunter.__main__.get_session"),
        patch("jobhunter.__main__.AnthropicLLMClient"),
        patch("jobhunter.__main__.assist_application", return_value=mock_package),
    ):
        result = runner.invoke(app, ["assist", job_id, "--output-dir", str(output_dir)])
        assert result.exit_code == 0
        assert (output_dir / "cover_letter.md").exists()
        assert (output_dir / "cv_tweaks.md").exists()
        assert (output_dir / "keywords.txt").exists()
        assert (output_dir / "cv_variant.txt").exists()


def test_letter_cli_basic(tmp_path: Path) -> None:
    job_id = str(uuid.uuid4())
    mock_job = MagicMock(spec=Job, id=uuid.UUID(job_id), tier=JobTier.A)
    mock_letter = CoverLetterResult(
        text="Single letter content",
        model="test",
        prompt_version="v1",
        cost_usd=0.01,
        word_count=100,
    )

    with (
        patch("jobhunter.__main__.get_session") as mock_get_session,
        patch("jobhunter.__main__.AnthropicLLMClient"),
        patch("jobhunter.__main__.generate_cover_letter", return_value=mock_letter),
        patch("jobhunter.__main__.load_cv"),
            patch("jobhunter.application.variant_selector.recommend_cv_variant") as mock_rec,
    ):
        mock_rec.return_value = VariantRecommendation(
            variant_name="fullstack", confidence=1.0, reasoning="test"
        )
        mock_session = mock_get_session.return_value.__enter__.return_value
        mock_session.get.return_value = mock_job

        result = runner.invoke(app, ["letter", job_id])
        assert result.exit_code == 0
        assert "Single letter content" in result.stdout


def test_apply_cli_persistence_from_db_cache(mock_package: ApplicationPackage) -> None:
    job_id = mock_package.job_id
    mock_job = MagicMock(
        spec=Job,
        id=job_id,
        company="Test Co",
        title="Dev",
        score_data={
            "assistant_cache": {
                "cover_letter_text": mock_package.cover_letter.text,
                "cover_letter_model": mock_package.cover_letter.model,
            }
        },
    )

    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_session = mock_get_session.return_value.__enter__.return_value
        mock_session.get.return_value = mock_job

        result = runner.invoke(
            app,
            [
                "apply",
                str(job_id),
                "--method",
                "linkedin",
                "--cv-variant",
                "ai_python",
                "--notes",
                "Some notes",
            ],
        )

        assert result.exit_code == 0
        assert "Successfully registered application" in result.stdout
        assert "Persisting cover letter from database cache" in result.stdout

        # Verify Application record was created with data from cache
        added_objects = [
            call.args[0] for call in mock_session.add.call_args_list if isinstance(call.args[0], Application)
        ]
        assert len(added_objects) == 1
        app_record = added_objects[0]
        assert app_record.job_id == job_id
        assert app_record.application_method == "linkedin"
        assert app_record.cv_variant == "ai_python"
        assert app_record.cover_letter_text == mock_package.cover_letter.text
        assert app_record.notes == "Some notes"

        # Verify Job status was updated
        assert mock_job.status == JobStatus.APPLIED
        assert mock_session.commit.called


def test_apply_cli_missing_options() -> None:
    job_id = str(uuid.uuid4())
    # Missing --method and --cv-variant
    result = runner.invoke(app, ["apply", job_id])
    assert result.exit_code != 0
    # Typer might print to stderr instead of stdout
    assert "Missing option" in result.stdout or "Missing option" in result.stderr
