import pytest
from typing import Generator
from unittest.mock import patch, MagicMock
from sqlalchemy.orm import Session
from typer.testing import CliRunner
from jobhunter.__main__ import app
from jobhunter.db.models import ABTest, Job
from jobhunter.db.enums import ABTestStatus

runner = CliRunner()


@pytest.fixture
def patch_get_session(session: Session) -> Generator[MagicMock, None, None]:
    with patch("jobhunter.__main__.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        yield mock_get_session


def test_ab_test_create_cli(patch_get_session: MagicMock, session: Session) -> None:
    result = runner.invoke(
        app,
        [
            "analytics",
            "ab-test",
            "create",
            "--name",
            "cli_test",
            "--variants",
            "v1=0.5,v2=0.5",
            "--metric",
            "tier_a_precision",
        ],
    )
    assert result.exit_code == 0
    assert "Successfully created A/B test: cli_test" in result.output

    test = session.query(ABTest).filter_by(name="cli_test").first()
    assert test is not None
    assert test.variants == {"v1": 0.5, "v2": 0.5}


def test_ab_test_create_invalid_weights(patch_get_session: MagicMock, session: Session) -> None:
    result = runner.invoke(
        app,
        [
            "analytics",
            "ab-test",
            "create",
            "--name",
            "bad_weights",
            "--variants",
            "v1=0.6,v2=0.5",
            "--metric",
            "tier_a_precision",
        ],
    )
    assert result.exit_code != 0
    assert "Error: Weights must sum to 1.0" in result.output


def test_ab_test_conclude_min_sample_size(patch_get_session: MagicMock, session: Session) -> None:
    # Create a test
    ab_test = ABTest(
        name="conclude_test",
        variants={"v1": 0.5, "v2": 0.5},
        metric_target="tier_a_precision",
        status=ABTestStatus.ACTIVE,
    )
    session.add(ab_test)

    # Add only 10 jobs (less than 30)
    for i in range(10):
        job = Job(
            source="test",
            url=f"http://test.com/{i}",
            url_hash=f"hash{i}",
            title="test",
            company="test",
            description="test",
            score_version="v1" if i % 2 == 0 else "v2",
        )
        session.add(job)

    session.commit()

    result = runner.invoke(
        app,
        [
            "analytics",
            "ab-test",
            "conclude",
            "conclude_test",
            "--winner",
            "v1",
            "--conclusion",
            "looks good",
        ],
    )
    assert result.exit_code != 0
    assert "Error: Sample size for variant 'v1' is too small" in result.output


def test_ab_test_results_cli(patch_get_session: MagicMock, session: Session) -> None:
    ab_test = ABTest(
        name="results_test",
        variants={"v1": 0.5, "v2": 0.5},
        metric_target="tier_a_precision",
        status=ABTestStatus.ACTIVE,
    )
    session.add(ab_test)
    session.commit()

    result = runner.invoke(app, ["analytics", "ab-test", "results", "results_test"])
    assert result.exit_code == 0
    assert "A/B Test Results: results_test" in result.output
    assert "v1" in result.output
    assert "v2" in result.output
