from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.analytics.quality_metrics import (
    get_false_rejects_detailed,
    get_missed_opportunities,
    rescore_suspicious_jobs,
)
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job
from jobhunter.scoring.scorer import JobScorer


@pytest.fixture
def session_with_rejects(session: Session) -> Session:
    """Seed the session with some rejected and manually promoted jobs."""
    # 1. Normal REJECT
    j1 = Job(
        source="test",
        url="http://test.com/1",
        url_hash="h1",
        title="Software Engineer",
        company="Tech Corp",
        description="A great job",
        tier=JobTier.REJECT,
        status=JobStatus.REJECTED,
        scraped_at=datetime.now(timezone.utc) - timedelta(days=5),
        score_data={
            "red_flags": ["No visa sponsorship"],
            "recommendation": {"reason_short": "No visa"},
        },
    )

    # 2. False Reject (Manually Promoted)
    j2 = Job(
        source="test",
        url="http://test.com/2",
        url_hash="h2",
        title="Senior Dev",
        company="Startup Inc",
        description="Another job",
        tier=JobTier.REJECT,
        status=JobStatus.QUEUED,
        scraped_at=datetime.now(timezone.utc) - timedelta(days=10),
        manually_promoted_at=datetime.now(timezone.utc) - timedelta(days=1),
        manually_promoted_reason="I have a referral",
        score_data={
            "red_flags": ["Experience mismatch"],
            "recommendation": {"reason_short": "Too senior"},
        },
    )

    # 3. Another REJECT for frequency analysis
    j3 = Job(
        source="test",
        url="http://test.com/3",
        url_hash="h3",
        title="Data Scientist",
        company="Data Co",
        description="Data job",
        tier=JobTier.REJECT,
        status=JobStatus.REJECTED,
        scraped_at=datetime.now(timezone.utc) - timedelta(days=30),
        score_data={
            "red_flags": ["Experience mismatch"],
            "recommendation": {"reason_short": "Too senior"},
        },
    )

    session.add_all([j1, j2, j3])
    session.commit()
    return session


def test_get_false_rejects_detailed(session_with_rejects: Session) -> None:
    rejects = get_false_rejects_detailed(session_with_rejects, limit=10, days=60)
    assert len(rejects) == 1
    assert rejects[0].company == "Startup Inc"
    assert rejects[0].manual_promotion_reason == "I have a referral"
    assert rejects[0].original_reject_reason == "Too senior"


def test_get_missed_opportunities(session_with_rejects: Session) -> None:
    # In our seed:
    # j2 was promoted and had "Experience mismatch"
    # j3 is rejected and has "Experience mismatch"
    # So "Experience mismatch" is an overridden flag.
    # get_missed_opportunities should find j3.

    # We need to make sure the time windows match.
    # Current implementation of get_missed_opportunities uses complex frequency heuristic.
    # Let's see if it catches j3 or j1.

    opps = get_missed_opportunities(session_with_rejects, limit=10, days=60)
    assert len(opps) >= 1
    # Check if j3 or j1 is in results (they are both REJECT and not promoted)
    job_ids = [o.job_id for o in opps]
    assert any(
        str(j.id) in job_ids
        for j in session_with_rejects.scalars(
            select(Job).where(Job.url_hash.in_(["h1", "h3"]))
        ).all()
    )


@pytest.mark.asyncio
async def test_rescore_suspicious_jobs(session_with_rejects: Session) -> None:
    from jobhunter.scoring.schema import (
        Action,
        CompanyInfo,
        CompanyStage,
        CompensationInfo,
        ContractType,
        LogisticsInfo,
        MatchAnalysis,
        Priority,
        Recommendation,
        RoleInfo,
        ScoringResult,
        Seniority,
        Tier,
        RemoteType,
        TimezoneRequirement,
    )

    # Mock Scorer
    mock_scorer = MagicMock(spec=JobScorer)

    # Mock a successful improved outcome
    mock_result = ScoringResult(
        fit_score=85,
        tier=Tier.A,
        company=CompanyInfo(
            name="Tech Corp", stage=CompanyStage.ENTERPRISE, domain_inferred="tech"
        ),
        role=RoleInfo(
            title_normalized="SE",
            seniority_inferred=Seniority.SENIOR,
            primary_stack_match=["Python"],
            stack_overlap_pct=90,
            is_ai_ml_role=False,
            is_flutter_role=False,
            is_full_stack=True,
        ),
        compensation=CompensationInfo(
            salary_min_usd_month=5000,
            salary_max_usd_month=7000,
            salary_explicit_in_offer=True,
            currency_original="USD",
            meets_floor=True,
            meets_target=True,
            notes=None,
        ),
        logistics=LogisticsInfo(
            remote_type=RemoteType.REMOTE_EU_ONLY,
            timezone_requirement=TimezoneRequirement.STRICT_CET,
            overlap_hours_required_with_CET=8,
            latam_friendly=True,
            colombia_explicitly_blocked=False,
            contract_type_offered=ContractType.B2B,
            language_requirements=["English"],
        ),
        match_analysis=MatchAnalysis(
            key_match_points=["Good stack"], key_gaps=[], differentiators_to_emphasize=[]
        ),
        red_flags=[],
        yellow_flags=[],
        recommendation=Recommendation(
            action=Action.APPLY_NOW,
            priority=Priority.HIGH,
            reason_short="Great match",
            cover_letter_angle="Tech",
        ),
        valid=True,
    )

    mock_outcome = MagicMock()
    mock_outcome.result = mock_result
    mock_outcome.model = "test-model"
    mock_outcome.prompt_version = "v1"
    mock_scorer.score = AsyncMock(return_value=mock_outcome)

    job = session_with_rejects.scalars(select(Job).where(Job.url_hash == "h1")).one()

    reports = await rescore_suspicious_jobs(session_with_rejects, mock_scorer, [job], confirm=False)

    assert len(reports) == 1
    assert reports[0].improved is True
    assert reports[0].new_tier == JobTier.A

    # Verify DB update
    assert job.tier == JobTier.A
    assert job.status == JobStatus.QUEUED
