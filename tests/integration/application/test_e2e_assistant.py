import pytest
from sqlalchemy.orm import Session
from jobhunter.db.models import Job, Application
from jobhunter.db.enums import JobStatus, JobTier, ApplicationStatus
from jobhunter.application.assistant import assist_application, JobNotAssistableError
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from typer.testing import CliRunner
from jobhunter.__main__ import app
from unittest.mock import patch
import uuid
from typing import Any


@pytest.mark.asyncio
async def test_assist_application_e2e_python_ai(
    db_session: Session,
    mock_llm_client: Any,
) -> None:
    """
    End-to-end test for assist_application with a Tier-A Python/AI job.
    """
    # 1. Setup a Tier-A Job
    job = Job(
        source="test",
        url="https://example.com/job1",
        url_hash="hash1",
        title="Senior Python and AI stack Engineer",
        company="AI Innovations",
        description="We need a Senior Python and AI stack Engineer. Expertise in PyTorch is required.",
        tier=JobTier.A,
        status=JobStatus.NEW,
        score_data={
            "valid": True,
            "role": {"is_ai_ml_role": True, "primary_stack_match": ["Python", "PyTorch"]},
        },
    )
    db_session.add(job)
    db_session.commit()

    # 2. Run assist_application
    package = await assist_application(
        session=db_session,
        job_id=job.id,
        llm_client=mock_llm_client,
    )

    # 3. Verify results
    assert package.job_id == job.id
    assert package.cv_variant.variant_name == "ai_python"
    assert package.cover_letter is not None
    assert "Dear Hiring Manager" in package.cover_letter.text
    assert len(package.ats_keywords.must_have) > 0
    assert len(package.cv_tweaks.tweaks) > 0

    # Verify persistence in job.score_data["assistant_cache"]
    db_session.refresh(job)
    assert job.score_data is not None
    score_data = job.score_data
    assistant_cache = score_data["assistant_cache"]
    assert assistant_cache["cv_variant"] == "ai_python"
    assert "Dear Hiring Manager" in assistant_cache["cover_letter_text"]


@pytest.mark.asyncio
async def test_assist_application_rejected_job_raises_error(
    db_session: Session,
    mock_llm_client: Any,
) -> None:
    """
    Verifies that assist_application raises JobNotAssistableError for REJECT tier.
    """
    job = Job(
        source="test",
        url="https://example.com/job2",
        url_hash="hash2",
        title="Junior Developer",
        company="Bad Corp",
        description="Low salary and bad tech stack.",
        tier=JobTier.REJECT,
        status=JobStatus.REJECTED,
    )
    db_session.add(job)
    db_session.commit()

    with pytest.raises(JobNotAssistableError):
        await assist_application(
            session=db_session,
            job_id=job.id,
            llm_client=mock_llm_client,
        )


def test_apply_command_persists_application_and_uses_cache(
    db_session: Session,
) -> None:
    """
    Integration test for the 'apply' CLI command.
    Verifies it creates an Application record and uses cached assistant data.
    """
    # 1. Setup a Job with assistant_cache
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        source="test",
        url="https://example.com/job3",
        url_hash="hash3",
        title="Senior Flutter Developer",
        company="MobileFirst",
        description="Flutter apps development role.",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
        score_data={
            "assistant_cache": {
                "cv_variant": "flutter",
                "cover_letter_text": "Cached cover letter for Flutter.",
                "cover_letter_model": "claude-opus-4-7",
            }
        },
    )
    db_session.add(job)
    db_session.commit()

    # 2. Run 'apply' command via CliRunner
    # We need to mock get_session to return our test db_session
    runner = CliRunner()
    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = db_session
        result = runner.invoke(
            app,
            ["apply", str(job_id), "--method", "LinkedIn", "--cv-variant", "flutter"],
            catch_exceptions=False,
        )

    # 3. Verify CLI output
    if result.exit_code != 0:
        print(f"CLI Output: {result.output}")
    assert result.exit_code == 0
    assert "Successfully registered application" in result.output
    assert "Persisting cover letter from database cache" in result.output

    # 4. Verify Database state
    db_session.expire_all()
    app_record = db_session.query(Application).filter_by(job_id=job_id).one()
    assert app_record.status == ApplicationStatus.APPLIED
    assert app_record.application_method == "LinkedIn"
    assert app_record.cv_variant == "flutter"
    assert app_record.cover_letter_text == "Cached cover letter for Flutter."

    updated_job = db_session.get(Job, job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.APPLIED
