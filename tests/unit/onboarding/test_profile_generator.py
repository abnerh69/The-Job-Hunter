import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from jobhunter.db.models import CandidateProfile
from jobhunter.onboarding.profile_generator import ProfileUserInputs, generate_profile
from jobhunter.onboarding.resume_ingestor import ResumeData


from sqlalchemy.orm import Session
from _pytest.capture import CaptureFixture


@pytest.mark.asyncio
async def test_generate_profile_success(db_session: Session) -> None:
    # 1. Setup Input Data
    resume_data = ResumeData(
        name="John Doe",
        email="john@example.com",
        languages=["English", "Spanish"],
        detected_seniority="senior",
        detected_years_experience=10,
        raw_text="Extracted resume text...",
    )

    user_inputs = ProfileUserInputs(
        country="Spain",
        work_authorization="EU Citizen",
        timezone_home="CET",
        overlap_max_hours_cet=8,
        contract_preferences=["Full-time"],
        hard_blockers=["No crypto"],
        payment_methods_ok=["Bank Transfer"],
        profile_name="Senior Python Developer",
    )

    # 2. Mock LLM Client
    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()

    llm_response_data = {
        "seniority": "senior",
        "years_experience": 10,
        "primary_stack": ["Python", "Django", "PostgreSQL"],
        "secondary_stack": ["Docker", "AWS"],
        "domains": ["FinTech", "SaaS"],
        "positive_signals": ["Led a team of 5", "Expert in Django"],
        "soft_negatives": ["None"],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(llm_response_data)
    mock_llm_client.complete.return_value = mock_response

    # 3. Execute generate_profile
    profile = await generate_profile(
        resume_data=resume_data,
        user_inputs=user_inputs,
        session=db_session,
        llm_client=mock_llm_client,
    )

    # 4. Assertions
    assert isinstance(profile, CandidateProfile)
    assert profile.id is not None
    assert profile.name == "Senior Python Developer"
    assert profile.seniority == "senior"
    assert profile.years_experience == 10
    assert profile.country == "Spain"

    # Check language logic (Spanish should be native in Spain)
    assert profile.languages is not None
    assert profile.languages["Spanish"] == "native"
    assert profile.languages["English"] == "fluent"

    # Check stacks and domains
    assert profile.primary_stack is not None
    assert "Python" in profile.primary_stack
    assert profile.domains is not None
    assert "FinTech" in profile.domains

    # Check persistence
    db_session.expire(profile)
    persisted_profile = db_session.get(CandidateProfile, profile.id)
    assert persisted_profile is not None
    assert persisted_profile.name == "Senior Python Developer"
    assert persisted_profile.compensation is None


@pytest.mark.asyncio
async def test_generate_profile_experience_mismatch_warning(
    db_session: Session, capsys: CaptureFixture[str]
) -> None:
    # 1. Setup Input Data (with mismatching experience)
    resume_data = ResumeData(
        name="John Doe",
        detected_years_experience=15,  # Resume says 15
        experiences=[],
        raw_text="Extracted resume text...",
    )

    user_inputs = ProfileUserInputs(
        country="USA",
        work_authorization="Green Card",
        timezone_home="EST",
        overlap_max_hours_cet=4,
        profile_name="Senior Dev",
    )

    # 2. Mock LLM Client (inferring 5 years instead of 15)
    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()

    llm_response_data = {
        "seniority": "senior",
        "years_experience": 5,  # LLM says 5
        "primary_stack": ["Go"],
        "secondary_stack": [],
        "domains": [],
        "positive_signals": [],
        "soft_negatives": [],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(llm_response_data)
    mock_llm_client.complete.return_value = mock_response

    # 3. Execute
    await generate_profile(
        resume_data=resume_data,
        user_inputs=user_inputs,
        session=db_session,
        llm_client=mock_llm_client,
    )

    # 4. Assertions - Check if warning was logged
    captured = capsys.readouterr()
    assert "profile_experience_mismatch" in captured.out
    assert (
        "LLM inferred years of experience differs from resume ingestion detection" in captured.out
    )


@pytest.mark.asyncio
async def test_generate_profile_llm_parse_error(db_session: Session) -> None:
    resume_data = ResumeData(name="John Doe", raw_text="...")
    user_inputs = ProfileUserInputs(
        country="UK",
        work_authorization="Citizen",
        timezone_home="GMT",
        overlap_max_hours_cet=8,
        profile_name="Dev",
    )

    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()
    mock_response = MagicMock()
    mock_response.text = "NOT A JSON"
    mock_llm_client.complete.return_value = mock_response

    with pytest.raises(ValueError, match="Failed to parse LLM response as JSON"):
        await generate_profile(
            resume_data=resume_data,
            user_inputs=user_inputs,
            session=db_session,
            llm_client=mock_llm_client,
        )
