from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from jobhunter.__main__ import app
from jobhunter.notify.base import NotificationResult


runner = CliRunner()


def test_regression_anti_flapping(session: Session, pytestconfig: pytest.Config) -> None:
    """Test that regression alerts are deduplicated (anti-flapping)."""

    # Mock check_metrics to return a regression
    from jobhunter.analytics.regression_detector import MetricValue, RegressionReport

    mock_metric = MetricValue(
        name="Tier A Rate",
        current_value=10.0,
        baseline_value=50.0,
        change_pct=-80.0,
        change_absolute=-40.0,
        is_regression=True,
    )

    mock_report = RegressionReport(
        metrics=[mock_metric], inferred_context={}, detected_at=datetime.now(timezone.utc)
    )

    with (
        patch("jobhunter.__main__.check_metrics", return_value=mock_report),
        patch(
            "jobhunter.__main__.get_session",
            return_value=MagicMock(__enter__=lambda s: session, __exit__=lambda s, *a: None),
        ),
        patch("jobhunter.notify.telegram.TelegramNotifier.is_enabled", return_value=True),
        patch(
            "jobhunter.notify.telegram.TelegramNotifier.send",
            return_value=NotificationResult(success=True, duration_ms=0),
        ) as mock_send,
    ):
        # First run: should alert
        result = runner.invoke(app, ["analytics", "check-regressions"])
        if result.exit_code != 0:
            print(result.output)
        assert result.exit_code == 0
        assert mock_send.call_count == 1

        # Second run immediately: should NOT alert (deduplicated)
        result = runner.invoke(app, ["analytics", "check-regressions"])
        assert result.exit_code == 0
        assert mock_send.call_count == 1  # Still 1

        # Simulate significantly worse regression (new bucket)
        # bucket = int(abs(m.change_pct) // 20) -> abs(-80) // 20 = 4
        # if we change it to -100, abs(-100) // 20 = 5

        mock_metric.change_pct = -100.0
        result = runner.invoke(app, ["analytics", "check-regressions"])
        assert result.exit_code == 0
        assert mock_send.call_count == 2
