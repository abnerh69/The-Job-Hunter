import pytest
from sqlalchemy.orm import Session
from jobhunter.db.models import CandidateProfile, Job
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.scoring.pipeline import score_pending_jobs
from jobhunter.scoring.scorer import JobScorer
from jobhunter.scoring.schema import ScoringResult, InvalidScoringResponse
from jobhunter.llm.budget import BudgetExceededError
from typing import Any


@pytest.mark.asyncio
async def test_pipeline_e2e_distribution(
    db_session: Session, mock_job_scorer: JobScorer, sample_candidate_profile: CandidateProfile
) -> None:
    """
    Test the full pipeline with a variety of jobs and verify distribution.
    """
    # Create 20 mock jobs with different keywords to trigger different fixtures
    jobs = []

    # 4 Tier A Python/AI
    for i in range(4):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/a_py_{i}",
                url_hash=f"hash_a_py_{i}",
                title="Senior Python AI Developer",
                company="AI Corp",
                description="python and ai stack",
                status=JobStatus.NEW,
            )
        )

    # 3 Tier A Flutter
    for i in range(3):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/a_fl_{i}",
                url_hash=f"hash_a_fl_{i}",
                title="Senior Flutter Developer",
                company="Mobile Corp",
                description="flutter apps development",
                status=JobStatus.NEW,
            )
        )

    # 3 Tier B Borderline
    for i in range(3):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/b_{i}",
                url_hash=f"hash_b_{i}",
                title="Software Engineer",
                company="Mid Corp",
                description="Generic description for testing",
                status=JobStatus.NEW,
            )
        )

    # 3 Tier C Manual Review
    for i in range(3):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/c_{i}",
                url_hash=f"hash_c_{i}",
                title="Maintenance Role",
                company="Oldschool",
                description="manual review needed for maintenance",
                status=JobStatus.NEW,
            )
        )

    # 3 Reject EU Only
    for i in range(3):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/rej_eu_{i}",
                url_hash=f"hash_rej_eu_{i}",
                title="Local Dev",
                company="Eurocentric",
                description="eu work permit required strictly",
                status=JobStatus.NEW,
            )
        )

    # 2 Reject Low Salary
    for i in range(2):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/rej_low_{i}",
                url_hash=f"hash_rej_low_{i}",
                title="Junior Dev",
                company="CheapCode",
                description="low salary offered for this junior role",
                status=JobStatus.NEW,
            )
        )

    # 2 Invalid/Spam
    for i in range(2):
        jobs.append(
            Job(
                source="test",
                url=f"http://test.com/inv_{i}",
                url_hash=f"hash_inv_{i}",
                title="Spam Job",
                company="Spammer",
                description="invalid post that looks like a spam job",
                status=JobStatus.NEW,
            )
        )

    db_session.add_all(jobs)
    db_session.commit()

    # Run pipeline
    report = await score_pending_jobs(db_session, mock_job_scorer, limit=20)

    # Verify report
    assert report.total_processed == 20
    assert report.success_count == 20
    assert report.tier_distribution.get("A", 0) == 7  # 4 Py + 3 Flutter
    assert report.tier_distribution.get("B", 0) == 3
    assert report.tier_distribution.get("C", 0) == 3
    assert report.tier_distribution.get("REJECT", 0) == 5  # 3 EU + 2 Low Salary
    assert report.tier_distribution.get("INVALID", 0) == 2

    # Verify DB states
    queued_count = db_session.query(Job).filter(Job.status == JobStatus.QUEUED).count()
    assert queued_count == 10  # 7 A + 3 B

    manual_review_count = (
        db_session.query(Job).filter(Job.status == JobStatus.MANUAL_REVIEW).count()
    )
    assert manual_review_count == 3

    rejected_count = db_session.query(Job).filter(Job.status == JobStatus.REJECTED).count()
    assert rejected_count == 5

    archived_count = db_session.query(Job).filter(Job.status == JobStatus.ARCHIVED).count()
    assert archived_count == 2


@pytest.mark.asyncio
async def test_pipeline_budget_exceeded(
    db_session: Session,
    mock_job_scorer: JobScorer,
    monkeypatch: pytest.MonkeyPatch,
    sample_candidate_profile: CandidateProfile,
) -> None:
    """
    Test that JobScorer.score raises BudgetExceededError when budget is reached.
    """

    # Force budget to 0 by patching check_budget directly in JobScorer.score
    def mock_check_budget(session: Session) -> None:
        raise BudgetExceededError(100.0, 50.0)

    monkeypatch.setattr("jobhunter.scoring.scorer.check_budget", mock_check_budget)

    job = Job(
        source="test",
        url="http://test.com/budget",
        url_hash="hash_budget",
        title="Python AI",
        company="AI Corp",
        description="Expensive call",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    # We test JobScorer.score directly because the pipeline swallows the error
    # to continue processing other jobs (failure isolation).
    with pytest.raises(BudgetExceededError):
        await mock_job_scorer.score(job, profile=sample_candidate_profile, session=db_session)


@pytest.mark.asyncio
async def test_score_data_roundtrip_validation(
    db_session: Session, mock_job_scorer: JobScorer, sample_candidate_profile: CandidateProfile
) -> None:
    """
    Verify that persisted score_data is valid against the Pydantic schema.
    """
    job = Job(
        source="test",
        url="http://test.com/roundtrip",
        url_hash="hash_roundtrip",
        title="Python AI Developer",
        company="AI Corp",
        description="python and ai stack",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    await score_pending_jobs(db_session, mock_job_scorer)

    # Refresh job from DB
    db_session.expire_all()
    job_from_db = db_session.query(Job).filter(Job.url_hash == "hash_roundtrip").one()

    # Scores are now in job_profile_scores table
    from jobhunter.db.models import JobProfileScore

    profile_score = (
        db_session.query(JobProfileScore).filter(JobProfileScore.job_id == job_from_db.id).one()
    )

    assert profile_score.score_data is not None

    # Validate against Pydantic schema
    if profile_score.score_data.get("valid"):
        res_valid = ScoringResult.model_validate(profile_score.score_data)
        assert res_valid.fit_score == 95
        assert res_valid.tier == "A"
    else:
        res_invalid = InvalidScoringResponse.model_validate(profile_score.score_data)
        assert res_invalid.valid is False


@pytest.mark.asyncio
async def test_scorer_retry_on_malformed_json(
    db_session: Session,
    mock_job_scorer: JobScorer,
    mock_llm_client: Any,
    sample_candidate_profile: CandidateProfile,
) -> None:
    """
    Test that the scorer retries when receiving malformed JSON.
    """
    # Reset call count for this specific test
    mock_llm_client.call_count = 0

    job = Job(
        source="test",
        url="http://test.com/malformed",
        url_hash="hash_malformed",
        title="Malformed test",
        company="Broken",
        description="this will return malformed first",
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.commit()

    # The MockLLMClient is programmed to return malformed_json.txt on the first call
    # when "malformed" is in the prompt, and tier_a_python_ai.json on the second call.

    report = await score_pending_jobs(db_session, mock_job_scorer)

    assert report.success_count == 1
    assert report.tier_distribution.get("A", 0) == 1

    # Verify job status
    db_session.expire_all()
    job_from_db = db_session.query(Job).filter(Job.url_hash == "hash_malformed").one()
    assert job_from_db.status == JobStatus.QUEUED

    from jobhunter.db.models import JobProfileScore

    profile_score = (
        db_session.query(JobProfileScore).filter(JobProfileScore.job_id == job_from_db.id).one()
    )
    assert profile_score.tier == JobTier.A

    # Verify it took 2 calls
    assert mock_llm_client.call_count == 2
