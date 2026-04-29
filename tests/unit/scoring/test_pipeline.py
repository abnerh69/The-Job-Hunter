import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job, LLMCall
from jobhunter.scoring.pipeline import rescore_jobs, score_pending_jobs
from jobhunter.scoring.schema import ScoringResult, Tier
from jobhunter.scoring.scorer import ScoringOutcome


@pytest.fixture
def mock_scorer() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def sample_outcome() -> ScoringOutcome:
    # Minimal ScoringResult mock
    result = MagicMock(spec=ScoringResult)
    result.valid = True
    result.fit_score = 85
    result.tier = Tier.A
    result.red_flags = []
    result.model_dump.return_value = {"mock": "data"}

    return ScoringOutcome(
        result=result,
        model="claude-haiku-4-5-20251001",
        prompt_version="v1",
        input_tokens=100,
        output_tokens=200,
        cost_usd=0.001,
        duration_ms=500,
        raw_response="{}",
    )


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.mark.asyncio
async def test_score_pending_jobs_success(
    mock_session: MagicMock, mock_scorer: AsyncMock, sample_outcome: ScoringOutcome
) -> None:
    # Arrange
    job = Job(
        id=uuid.uuid4(),
        title="Python Developer",
        company="Test Inc",
        description="Great job",
        source="test",
        url="https://test.com/1",
        url_hash="hash1",
        status=JobStatus.NEW,
    )
    mock_session.scalars.return_value.all.return_value = [job]
    mock_scorer.score.return_value = sample_outcome

    # Act
    report = await score_pending_jobs(mock_session, mock_scorer)

    # Assert
    assert report.total_processed == 1
    assert report.success_count == 1
    assert report.total_cost_usd == 0.001
    assert report.tier_distribution[JobTier.A] == 1

    assert job.status == JobStatus.QUEUED
    assert job.tier == JobTier.A
    assert job.fit_score == 85
    assert job.score_model == "claude-haiku-4-5-20251001"

    # Check that score was called with the session
    mock_scorer.score.assert_called_once_with(job, session=mock_session)

    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_score_pending_jobs_failure_isolation(
    mock_session: MagicMock, mock_scorer: AsyncMock, sample_outcome: ScoringOutcome
) -> None:
    # Arrange
    job1 = Job(id=uuid.uuid4(), title="J1", company="C1", status=JobStatus.NEW)
    job2 = Job(id=uuid.uuid4(), title="J2", company="C2", status=JobStatus.NEW)

    mock_session.scalars.return_value.all.return_value = [job1, job2]
    mock_scorer.score.side_effect = [
        Exception("Scoring failed"),
        sample_outcome,
    ]

    # Act
    report = await score_pending_jobs(mock_session, mock_scorer, concurrency=1)

    # Assert
    assert report.total_processed == 2
    assert report.success_count == 1
    assert report.failed_count == 1

    assert job1.status == JobStatus.NEW
    assert job2.status == JobStatus.QUEUED
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_score_pending_jobs_idempotency(
    mock_session: MagicMock, mock_scorer: AsyncMock
) -> None:
    # Arrange
    mock_session.scalars.return_value.all.return_value = []

    # Act
    report = await score_pending_jobs(mock_session, mock_scorer)

    # Assert
    assert report.total_processed == 0
    assert mock_scorer.score.call_count == 0


@pytest.mark.asyncio
async def test_rescore_jobs(
    mock_session: MagicMock, mock_scorer: AsyncMock, sample_outcome: ScoringOutcome
) -> None:
    # Arrange
    job = Job(
        id=uuid.uuid4(),
        title="J1",
        company="C1",
        status=JobStatus.QUEUED,
        tier=JobTier.B,
    )
    mock_session.scalars.return_value.all.return_value = [job]

    assert isinstance(sample_outcome.result, ScoringResult)
    sample_outcome.result.tier = Tier.A
    mock_scorer.score.return_value = sample_outcome

    # Act
    report = await rescore_jobs(mock_session, mock_scorer, filters={"tier": JobTier.B})

    # Assert
    assert report.total_processed == 1
    assert report.success_count == 1
    assert job.tier == JobTier.A
    mock_session.commit.assert_called_once()
