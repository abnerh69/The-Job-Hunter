import uuid
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from jobhunter.__main__ import app
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job
from jobhunter.scoring.pipeline import ScoringBatchReport
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
    RemoteType,
    RoleInfo,
    ScoringResult,
    Seniority,
    Tier,
    TimezoneRequirement,
)

runner = CliRunner()


@pytest.fixture
def mock_session() -> Generator[MagicMock, None, None]:
    with patch("jobhunter.__main__.get_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session


@pytest.fixture
def mock_llm_client() -> Generator[MagicMock, None, None]:
    with patch("jobhunter.__main__.AnthropicLLMClient") as mock:
        yield mock.return_value


def test_score_command_success(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    """Test the score command successfully processes jobs."""
    # Setup mock report
    report = ScoringBatchReport(
        total_processed=2,
        success_count=2,
        failed_count=0,
        tier_distribution={"A": 1, "B": 1},
        total_cost_usd=0.01,
        duration_seconds=1.5,
    )

    with patch("jobhunter.__main__.score_pending_jobs", return_value=report) as mock_score:
        result = runner.invoke(app, ["score", "--limit", "10", "--concurrency", "2"])

        assert result.exit_code == 0
        assert "Scoring Report" in result.output
        assert "Processed" in result.output
        assert "2" in result.output
        assert "Total Cost" in result.output
        assert "$0.0100" in result.output

        mock_score.assert_called_once()
        args, kwargs = mock_score.call_args
        assert kwargs["limit"] == 10
        assert kwargs["concurrency"] == 2
        assert kwargs["dry_run"] is False


def test_score_command_low_success_rate(
    mock_session: MagicMock, mock_llm_client: MagicMock
) -> None:
    """Test the score command exits with code 1 if success rate is low."""
    report = ScoringBatchReport(
        total_processed=10,
        success_count=8,  # 80% success rate < 90%
        failed_count=2,
        tier_distribution={"A": 8},
        total_cost_usd=0.05,
        duration_seconds=2.0,
    )

    with patch("jobhunter.__main__.score_pending_jobs", return_value=report):
        result = runner.invoke(app, ["score"])

        assert result.exit_code == 1
        assert "Low success rate: 80.0%" in result.output


def test_score_command_dry_run(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    """Test the score command with --dry-run flag."""
    report = ScoringBatchReport(total_processed=0)

    with patch("jobhunter.__main__.score_pending_jobs", return_value=report) as mock_score:
        result = runner.invoke(app, ["score", "--dry-run"])

        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        mock_score.assert_called_once()
        assert mock_score.call_args[1]["dry_run"] is True


def test_score_job_command_success(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    """Test score-job command for a single job."""
    job_id = uuid.uuid4()
    job = Job(id=job_id, title="Test Job", company="Test Co", description="Desc")

    mock_repo = MagicMock()
    mock_repo.get.return_value = job

    outcome = MagicMock()
    outcome.raw_response = "AI Response"
    outcome.model = "claude-haiku"
    outcome.cost_usd = 0.001
    outcome.input_tokens = 100
    outcome.output_tokens = 50
    outcome.result = ScoringResult(
        valid=True,
        fit_score=85,
        tier=Tier.A,
        company=CompanyInfo(
            name="Test Co",
            stage=CompanyStage.SCALEUP,
            domain_inferred="Fintech",
        ),
        role=RoleInfo(
            title_normalized="QA Engineer",
            seniority_inferred=Seniority.MID,
            primary_stack_match=["Python"],
            stack_overlap_pct=80,
            is_ai_ml_role=False,
            is_flutter_role=False,
            is_full_stack=False,
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
            timezone_requirement=TimezoneRequirement.FLEXIBLE_EU,
            overlap_hours_required_with_CET=4,
            latam_friendly=True,
            colombia_explicitly_blocked=False,
            contract_type_offered=ContractType.B2B,
            language_requirements=["English"],
        ),
        match_analysis=MatchAnalysis(
            key_match_points=["Python"],
            key_gaps=[],
            differentiators_to_emphasize=["QA Automation"],
        ),
        recommendation=Recommendation(
            action=Action.APPLY_NOW,
            priority=Priority.HIGH,
            reason_short="Good fit",
            cover_letter_angle="Emphasize QA skills",
        ),
        yellow_flags=[],
        red_flags=[],
    )
    outcome.prompt_version = "v1"

    with (
        patch("jobhunter.__main__.JobRepo", return_value=mock_repo),
        patch("jobhunter.__main__.asyncio.run", return_value=outcome),
    ):
        result = runner.invoke(app, ["score-job", str(job_id)])

        assert result.exit_code == 0
        assert "RAW RESPONSE" in result.output
        assert "AI Response" in result.output
        assert "Tier" in result.output
        assert "A" in result.output
        assert "Result NOT persisted" in result.output


def test_score_job_command_persist(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    """Test score-job command with --persist flag."""
    job_id = uuid.uuid4()
    job = Job(
        id=job_id, title="Test Job", company="Test Co", description="Desc", status=JobStatus.NEW
    )

    mock_repo = MagicMock()
    mock_repo.get.return_value = job

    outcome = MagicMock()
    outcome.raw_response = "AI Response"
    outcome.model = "claude-haiku"
    outcome.cost_usd = 0.001
    outcome.input_tokens = 100
    outcome.output_tokens = 50
    outcome.result = ScoringResult(
        valid=True,
        fit_score=95,
        tier=Tier.A,
        company=CompanyInfo(
            name="Test Co",
            stage=CompanyStage.SCALEUP,
            domain_inferred="Fintech",
        ),
        role=RoleInfo(
            title_normalized="QA Engineer",
            seniority_inferred=Seniority.SENIOR,
            primary_stack_match=["Python"],
            stack_overlap_pct=100,
            is_ai_ml_role=False,
            is_flutter_role=False,
            is_full_stack=False,
        ),
        compensation=CompensationInfo(
            salary_min_usd_month=8000,
            salary_max_usd_month=10000,
            salary_explicit_in_offer=True,
            currency_original="USD",
            meets_floor=True,
            meets_target=True,
            notes=None,
        ),
        logistics=LogisticsInfo(
            remote_type=RemoteType.REMOTE_GLOBAL,
            timezone_requirement=TimezoneRequirement.ANY,
            overlap_hours_required_with_CET=0,
            latam_friendly=True,
            colombia_explicitly_blocked=False,
            contract_type_offered=ContractType.B2B,
            language_requirements=["English"],
        ),
        match_analysis=MatchAnalysis(
            key_match_points=["Python"],
            key_gaps=[],
            differentiators_to_emphasize=["Senior QA"],
        ),
        recommendation=Recommendation(
            action=Action.APPLY_NOW,
            priority=Priority.HIGH,
            reason_short="Perfect fit",
            cover_letter_angle="Emphasize seniority",
        ),
        yellow_flags=[],
        red_flags=[],
    )
    outcome.prompt_version = "v1"

    with (
        patch("jobhunter.__main__.JobRepo", return_value=mock_repo),
        patch("jobhunter.__main__.asyncio.run", return_value=outcome),
    ):
        result = runner.invoke(app, ["score-job", str(job_id), "--persist"])

        assert result.exit_code == 0
        assert "Result persisted to database." in result.output
        assert job.status == JobStatus.QUEUED
        assert job.tier == JobTier.A
        mock_session.commit.assert_called()


def test_rescore_command(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    """Test the rescore command."""
    report = ScoringBatchReport(
        total_processed=5,
        success_count=5,
        failed_count=0,
        tier_distribution={"A": 5},
        total_cost_usd=0.1,
        duration_seconds=5.0,
    )

    with patch("jobhunter.__main__.rescore_jobs", return_value=report) as mock_rescore:
        result = runner.invoke(app, ["rescore", "--tier", "B", "--limit", "20"])

        assert result.exit_code == 0
        assert "Rescoring Report" in result.output
        assert "B" in result.output
        assert "Processed" in result.output
        assert "5" in result.output

        mock_rescore.assert_called_once()
        args, kwargs = mock_rescore.call_args
        assert kwargs["filters"] == {"tier": "B"}
        assert kwargs["limit"] == 20
