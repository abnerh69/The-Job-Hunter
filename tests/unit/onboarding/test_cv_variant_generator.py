import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import date
from jobhunter.db.models import CandidateProfile, CVVariant, CVVariantExperience
from jobhunter.onboarding.cv_variant_generator import (
    VariantSpec,
    cv_variant_to_markdown,
    generate_variant,
    _parse_cv_dates,
)
from jobhunter.onboarding.resume_ingestor import ParsedExperience, ResumeData


@pytest.fixture
def sample_resume_data() -> ResumeData:
    return ResumeData(
        name="John Doe",
        email="john@example.com",
        summary="Experienced software engineer.",
        experiences=[
            ParsedExperience(
                role="Senior Developer",
                company="Tech Co",
                dates="2020-2023",
                bullets=["Built Python apps", "Worked with Flutter"],
            ),
            ParsedExperience(
                role="Junior Developer",
                company="StartUp Inc",
                dates="2018-2020",
                bullets=["Maintained legacy code", "Fixed bugs"],
            ),
        ],
        skills=["Python", "Flutter", "SQL"],
        languages=["English"],
        raw_text="...",
    )


@pytest.fixture
def sample_profile(db_session: Session) -> CandidateProfile:
    profile = CandidateProfile(
        name="John Doe Profile",
        seniority="senior",
        years_experience=5,
        country="Germany",
    )
    db_session.add(profile)
    db_session.flush()
    return profile


@pytest.mark.asyncio
async def test_generate_variant_success(
    db_session: Session, sample_profile: CandidateProfile, sample_resume_data: ResumeData
) -> None:
    # 1. Setup
    variant_spec = VariantSpec(
        name="python_expert",
        display_name="Python Expert",
        target_role_keywords=["Python", "Backend"],
        target_stack=["Python", "FastAPI"],
        target_seniority="senior",
        angle_description="Focus on backend Python development",
    )

    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()

    llm_response_data = {
        "summary": "Expert Python developer with focus on backend systems.",
        "skills": ["Python", "FastAPI", "SQL"],
        "experiences": [
            {
                "role": "Senior Developer",
                "company": "Tech Co",
                "dates": "2020-2023",
                "bullets": ["Built high-performance Python apps", "Designed backend architectures"],
            }
        ],
    }

    mock_response = MagicMock()
    mock_response.text = json.dumps(llm_response_data)
    mock_llm_client.complete.return_value = mock_response

    # 2. Execute
    variant = await generate_variant(
        profile=sample_profile,
        resume_data=sample_resume_data,
        variant_spec=variant_spec,
        session=db_session,
        llm_client=mock_llm_client,
    )

    # 3. Assertions
    assert isinstance(variant, CVVariant)
    assert variant.name == "python_expert"
    assert variant.display_name == "Python Expert"
    assert variant.summary == llm_response_data["summary"]
    assert len(variant.experiences) == 1
    assert variant.experiences[0].role == "Senior Developer"
    assert variant.raw_markdown is not None
    assert "Python" in variant.raw_markdown

    # Check persistence
    db_session.expire_all()
    persisted_variant = db_session.get(CVVariant, variant.id)
    assert persisted_variant is not None
    assert len(persisted_variant.experiences) == 1
    # Check bullets from the first experience
    exp_data = llm_response_data["experiences"]
    assert isinstance(exp_data, list)
    assert persisted_variant.experiences[0].bullets == exp_data[0].get("bullets")


@pytest.mark.asyncio
async def test_generate_variant_different_specs_different_outputs(
    db_session: Session, sample_profile: CandidateProfile, sample_resume_data: ResumeData
) -> None:
    # This test verifies that different specs lead to different LLM calls and results
    # We'll mock two different responses for two calls

    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()

    # Response 1: Python
    res1 = {
        "summary": "Python focus summary",
        "skills": ["Python"],
        "experiences": [
            {"role": "Dev", "company": "Co", "dates": "2020", "bullets": ["Python bullet"]}
        ],
    }
    # Response 2: Flutter
    res2 = {
        "summary": "Flutter focus summary",
        "skills": ["Flutter"],
        "experiences": [
            {"role": "Dev", "company": "Co", "dates": "2020", "bullets": ["Flutter bullet"]}
        ],
    }

    mock_response1 = MagicMock()
    mock_response1.text = json.dumps(res1)
    mock_response2 = MagicMock()
    mock_response2.text = json.dumps(res2)

    mock_llm_client.complete.side_effect = [mock_response1, mock_response2]

    spec1 = VariantSpec(
        name="python", display_name="P", target_seniority="senior", angle_description="Python focus"
    )
    spec2 = VariantSpec(
        name="flutter",
        display_name="F",
        target_seniority="senior",
        angle_description="Flutter focus",
    )

    v1 = await generate_variant(
        sample_profile, sample_resume_data, spec1, db_session, mock_llm_client
    )
    v2 = await generate_variant(
        sample_profile, sample_resume_data, spec2, db_session, mock_llm_client
    )

    assert v1.summary != v2.summary
    assert v1.summary is not None and "Python" in v1.summary
    assert v2.summary is not None and "Flutter" in v2.summary
    assert v1.skills != v2.skills


@pytest.mark.asyncio
async def test_generate_variant_atomic_rollback(
    db_session: Session, sample_profile: CandidateProfile, sample_resume_data: ResumeData
) -> None:
    # Mock LLM to return valid JSON but we'll force a DB error later
    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock()

    llm_res = {
        "summary": "...",
        "skills": [],
        "experiences": [{"role": "R", "company": "C", "dates": "D", "bullets": []}],
    }
    mock_response = MagicMock()
    mock_response.text = json.dumps(llm_res)
    mock_llm_client.complete.return_value = mock_response

    spec = VariantSpec(
        name="fail", display_name="F", target_seniority="senior", angle_description="Fail"
    )

    # To force a rollback, we could mock the repo to raise an exception
    # or pass something that violates a constraint if possible.
    # Let's try to mock the CVVariantRepo's create_with_experiences to raise an error.
    from unittest.mock import patch

    with pytest.raises(RuntimeError, match="DB Fail"):
        with patch(
            "jobhunter.onboarding.cv_variant_generator.CVVariantRepo.create_with_experiences",
            side_effect=RuntimeError("DB Fail"),
        ):
            await generate_variant(
                sample_profile, sample_resume_data, spec, db_session, mock_llm_client
            )

    # Verify no variant was created
    res = db_session.execute(select(CVVariant).where(CVVariant.name == "fail")).scalars().all()
    assert len(res) == 0


def test_cv_variant_to_markdown() -> None:
    variant = CVVariant(
        name="test",
        display_name="Test Variant",
        summary="Test Summary",
        target_stack=["Python", "FastAPI"],
        skills=["TDD", "Git"],
    )
    exp = CVVariantExperience(
        role="Dev",
        company="Co",
        start_date=date(2020, 1, 1),
        end_date=date(2023, 5, 1),
        bullets=["B1", "B2"],
    )
    variant.experiences = [exp]

    markdown = cv_variant_to_markdown(variant)

    assert "# Test Variant" in markdown
    assert "## SUMMARY" in markdown
    assert "Test Summary" in markdown
    assert "**Target Stack**: Python, FastAPI" in markdown
    assert "**Key Skills**: TDD, Git" in markdown
    assert "### Dev | Co | 2020-01 - 2023-05" in markdown
    assert "- B1" in markdown
    assert "- B2" in markdown


def test_parse_cv_dates() -> None:
    # Range with years
    s, e = _parse_cv_dates("2020-2023")
    assert s == date(2020, 1, 1)
    assert e == date(2023, 1, 1)

    # Range with months
    s, e = _parse_cv_dates("Jan 2020 - May 2022")
    assert s == date(2020, 1, 1)
    assert e == date(2022, 5, 1)

    # Range with present
    s, e = _parse_cv_dates("2019 to Present")
    assert s == date(2019, 1, 1)
    assert e is None

    # Invalid
    s, e = _parse_cv_dates("Not a date")
    assert s is None
    assert e is None
