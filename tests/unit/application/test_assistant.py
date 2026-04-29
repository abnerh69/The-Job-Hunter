import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from jobhunter.application.assistant import (
    ApplicationPackage,
    JobNotAssistableError,
    assist_application,
    clear_assistant_cache,
)
from jobhunter.application.ats_keywords import ATSKeywordsResult, Keyword
from jobhunter.application.cover_letter import CoverLetterResult
from jobhunter.application.cv import CVVariant
from jobhunter.application.cv_tweaks import CVTweaksResult, Tweak
from jobhunter.application.variant_selector import VariantRecommendation
from jobhunter.db.enums import JobTier
from jobhunter.db.models import Application, Job


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock(spec=Session)


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_job() -> Job:
    return Job(
        id=uuid4(),
        title="Python Engineer",
        company="Tech Corp",
        description="We need a Python developer.",
        tier=JobTier.A,
    )


@pytest.fixture
def mock_cv_variant() -> CVVariant:
    return MagicMock(spec=CVVariant, raw_markdown="My CV content")


@pytest.fixture
def mock_cover_letter() -> CoverLetterResult:
    return CoverLetterResult(
        text="Dear hiring manager...",
        model="test-model",
        prompt_version="v1",
        cost_usd=0.01,
        word_count=300,
    )


@pytest.fixture
def mock_ats_keywords() -> ATSKeywordsResult:
    return ATSKeywordsResult(
        must_have=[Keyword(term="Python", category="technical", weight=10, present_in_cv=True)],
        nice_to_have=[],
        model="haiku",
        prompt_version="v1",
        cost_usd=0.001,
    )


@pytest.fixture
def mock_cv_tweaks() -> CVTweaksResult:
    return CVTweaksResult(
        tweaks=[
            Tweak(
                type="add_keyword",
                target="Skills",
                suggested="Add Python",
                rationale="Essential for the role",
            )
        ],
        model="sonnet",
        prompt_version="v1",
        cost_usd=0.005,
    )


@pytest.mark.asyncio
async def test_assist_application_success(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
    mock_cv_variant: CVVariant,
    mock_cover_letter: CoverLetterResult,
    mock_ats_keywords: ATSKeywordsResult,
    mock_cv_tweaks: CVTweaksResult,
) -> None:
    # Arrange
    clear_assistant_cache()
    mock_session.get.return_value = sample_job
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with (
        patch(
            "jobhunter.application.assistant.recommend_cv_variant",
            return_value=VariantRecommendation(
                variant_name="fullstack", confidence=1.0, reasoning="test"
            ),
        ),
        patch("jobhunter.application.assistant.load_cv", return_value=mock_cv_variant),
        patch(
            "jobhunter.application.assistant.generate_cover_letter", return_value=mock_cover_letter
        ),
        patch(
            "jobhunter.application.assistant.extract_ats_keywords", return_value=mock_ats_keywords
        ),
        patch("jobhunter.application.assistant.suggest_cv_tweaks", return_value=mock_cv_tweaks),
    ):
        # Act
        package = await assist_application(mock_session, sample_job.id, mock_llm_client)

        # Assert
        assert isinstance(package, ApplicationPackage)
        assert package.job_id == sample_job.id
        assert package.cover_letter == mock_cover_letter
        assert package.ats_keywords == mock_ats_keywords
        assert package.cv_tweaks == mock_cv_tweaks
        assert package.total_cost_usd == pytest.approx(0.016)
        # Heuristic: 8 baseline + 1 tweak = 9.
        # But wait, Python is present_in_cv=True, and it's the only keyword.
        # So -2 min. 8 + 1 - 2 = 7.
        assert package.estimated_apply_time_min == 7


@pytest.mark.asyncio
async def test_assist_application_persistence(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
    mock_cv_variant: CVVariant,
    mock_cover_letter: CoverLetterResult,
    mock_ats_keywords: ATSKeywordsResult,
    mock_cv_tweaks: CVTweaksResult,
) -> None:
    # Arrange
    clear_assistant_cache()
    mock_session.get.return_value = sample_job

    mock_app = MagicMock(spec=Application)
    mock_session.execute.return_value.scalar_one_or_none.return_value = mock_app

    with (
        patch(
            "jobhunter.application.assistant.recommend_cv_variant",
            return_value=VariantRecommendation(
                variant_name="fullstack", confidence=1.0, reasoning="test"
            ),
        ),
        patch("jobhunter.application.assistant.load_cv", return_value=mock_cv_variant),
        patch(
            "jobhunter.application.assistant.generate_cover_letter", return_value=mock_cover_letter
        ),
        patch(
            "jobhunter.application.assistant.extract_ats_keywords", return_value=mock_ats_keywords
        ),
        patch("jobhunter.application.assistant.suggest_cv_tweaks", return_value=mock_cv_tweaks),
    ):
        # Act
        await assist_application(mock_session, sample_job.id, mock_llm_client)

        # Assert
        assert mock_app.cover_letter_text == mock_cover_letter.text
        assert mock_app.cover_letter_model == mock_cover_letter.model
        assert mock_session.commit.called


@pytest.mark.asyncio
async def test_assist_application_invalid_tier(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
) -> None:
    # Arrange
    clear_assistant_cache()
    sample_job.tier = JobTier.REJECT
    mock_session.get.return_value = sample_job

    # Act & Assert
    with pytest.raises(JobNotAssistableError):
        await assist_application(mock_session, sample_job.id, mock_llm_client)


@pytest.mark.asyncio
async def test_assist_application_parallelization(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
    mock_cv_variant: CVVariant,
    mock_cover_letter: CoverLetterResult,
    mock_ats_keywords: ATSKeywordsResult,
    mock_cv_tweaks: CVTweaksResult,
) -> None:
    # Arrange
    clear_assistant_cache()
    mock_session.get.return_value = sample_job
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    async def slow_cover_letter(*args: Any, **kwargs: Any) -> CoverLetterResult:
        await asyncio.sleep(0.2)
        return mock_cover_letter

    async def slow_keywords(*args: Any, **kwargs: Any) -> ATSKeywordsResult:
        await asyncio.sleep(0.1)
        return mock_ats_keywords

    async def slow_tweaks(*args: Any, **kwargs: Any) -> CVTweaksResult:
        await asyncio.sleep(0.1)
        return mock_cv_tweaks

    with (
        patch(
            "jobhunter.application.assistant.recommend_cv_variant",
            return_value=VariantRecommendation(
                variant_name="fullstack", confidence=1.0, reasoning="test"
            ),
        ),
        patch("jobhunter.application.assistant.load_cv", return_value=mock_cv_variant),
        patch(
            "jobhunter.application.assistant.generate_cover_letter", side_effect=slow_cover_letter
        ),
        patch("jobhunter.application.assistant.extract_ats_keywords", side_effect=slow_keywords),
        patch("jobhunter.application.assistant.suggest_cv_tweaks", side_effect=slow_tweaks),
    ):
        # Act
        start = time.perf_counter()
        await assist_application(mock_session, sample_job.id, mock_llm_client)
        duration = time.perf_counter() - start

        # Assert
        # Serial would be 0.2 + 0.1 + 0.1 = 0.4s
        # Parallel (cover letter) vs (keywords -> tweaks) would be max(0.2, 0.1 + 0.1) = 0.2s
        # We allow some overhead, but it should definitely be less than 0.35s
        assert duration < 0.35
        assert duration >= 0.2


@pytest.mark.asyncio
async def test_assist_application_cache(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
    mock_cv_variant: CVVariant,
    mock_cover_letter: CoverLetterResult,
    mock_ats_keywords: ATSKeywordsResult,
    mock_cv_tweaks: CVTweaksResult,
) -> None:
    # Arrange
    clear_assistant_cache()
    mock_session.get.return_value = sample_job
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with (
        patch(
            "jobhunter.application.assistant.recommend_cv_variant",
            return_value=VariantRecommendation(
                variant_name="fullstack", confidence=1.0, reasoning="test"
            ),
        ),
        patch("jobhunter.application.assistant.load_cv", return_value=mock_cv_variant),
        patch(
            "jobhunter.application.assistant.generate_cover_letter", return_value=mock_cover_letter
        ) as mock_cl,
        patch(
            "jobhunter.application.assistant.extract_ats_keywords", return_value=mock_ats_keywords
        ) as mock_ak,
        patch(
            "jobhunter.application.assistant.suggest_cv_tweaks", return_value=mock_cv_tweaks
        ) as mock_ct,
    ):
        # Act
        # First call
        package1 = await assist_application(mock_session, sample_job.id, mock_llm_client)
        # Second call
        package2 = await assist_application(mock_session, sample_job.id, mock_llm_client)

        # Assert
        assert package1 is package2
        # Verify mocks only called once
        mock_cl.assert_called_once()
        mock_ak.assert_called_once()
        mock_ct.assert_called_once()


@pytest.mark.asyncio
async def test_assist_application_cache_expiration(
    mock_session: MagicMock,
    mock_llm_client: AsyncMock,
    sample_job: Job,
    mock_cv_variant: CVVariant,
    mock_cover_letter: CoverLetterResult,
    mock_ats_keywords: ATSKeywordsResult,
    mock_cv_tweaks: CVTweaksResult,
) -> None:
    # Arrange
    clear_assistant_cache()
    mock_session.get.return_value = sample_job
    mock_session.execute.return_value.scalar_one_or_none.return_value = None

    with (
        patch(
            "jobhunter.application.assistant.recommend_cv_variant",
            return_value=VariantRecommendation(
                variant_name="fullstack", confidence=1.0, reasoning="test"
            ),
        ),
        patch("jobhunter.application.assistant.load_cv", return_value=mock_cv_variant),
        patch(
            "jobhunter.application.assistant.generate_cover_letter", return_value=mock_cover_letter
        ) as mock_cl,
        patch(
            "jobhunter.application.assistant.extract_ats_keywords", return_value=mock_ats_keywords
        ) as mock_ak,
        patch(
            "jobhunter.application.assistant.suggest_cv_tweaks", return_value=mock_cv_tweaks
        ) as mock_ct,
    ):
        # Act
        # First call
        await assist_application(mock_session, sample_job.id, mock_llm_client)

        # Force expiration by patching datetime
        expired_time = datetime.now(timezone.utc) + timedelta(hours=2)
        with patch("jobhunter.application.assistant.datetime") as mock_datetime:
            mock_datetime.now.return_value = expired_time
            # Second call should re-run
            await assist_application(mock_session, sample_job.id, mock_llm_client)

        # Assert
        assert mock_cl.call_count == 2
        assert mock_ak.call_count == 2
        assert mock_ct.call_count == 2
