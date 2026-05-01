from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from jobhunter.analytics.recommendations import (
    _check_template_zero_response,
    _check_source_dry_spell,
    _check_prompt_regression,
    _check_manual_review_bottleneck,
    _check_budget_warning,
    _check_circuit_breaker_stuck,
    Priority,
)
from jobhunter.db.enums import SourceState, EmailMatchStatus
from jobhunter.db.models import SourceHealth


def test_check_template_zero_response() -> None:
    session = MagicMock()
    # Mock return value for the query
    # OutreachMessage.template_type, total_sent, replies
    session.execute.return_value.all.return_value = [
        MagicMock(template_type="A_inhouse", total_sent=10, replies=0),
        MagicMock(template_type="B_boutique", total_sent=5, replies=0),
        MagicMock(template_type="C_senior", total_sent=15, replies=2),
    ]

    recs = _check_template_zero_response(session)
    assert len(recs) == 1
    assert recs[0].action == "Pausar template 'A_inhouse'"
    assert recs[0].priority == Priority.P1


def test_check_source_dry_spell() -> None:
    session = MagicMock()
    # Mock active sources
    session.scalars.return_value.all.return_value = ["LinkedIn", "Indeed"]

    # Mock a_tier_count for each source
    # First call for LinkedIn (0), second for Indeed (1)
    session.scalar.side_effect = [0, 1]

    recs = _check_source_dry_spell(session)
    assert len(recs) == 1
    assert recs[0].action == "Revisar filtros de la fuente 'LinkedIn'"
    assert recs[0].priority == Priority.P2


def test_check_prompt_regression() -> None:
    session = MagicMock()

    # Precision calculation helper inside the function uses session.execute().all()
    # We need to mock it twice: once for current, once for baseline.

    # Mock for current: precision < 0.8
    # EmailMatchStatus.AUTO_MATCHED, count
    current_mock = MagicMock()
    current_mock.all.return_value = [
        (EmailMatchStatus.AUTO_MATCHED, 7),
        (EmailMatchStatus.USER_REJECTED, 3),
    ]

    # Mock for baseline: precision >= 0.9
    baseline_mock = MagicMock()
    baseline_mock.all.return_value = [
        (EmailMatchStatus.AUTO_MATCHED, 10),
        (EmailMatchStatus.USER_REJECTED, 0),
    ]

    session.execute.side_effect = [current_mock, baseline_mock]

    recs = _check_prompt_regression(session)
    assert len(recs) == 1
    assert "Rollback" in recs[0].action
    assert recs[0].priority == Priority.P1


def test_check_manual_review_bottleneck() -> None:
    session = MagicMock()
    # Mock total_manual and old_manual
    # Case: total=10, old=4 (40% > 30%)
    session.scalar.side_effect = [10, 4]

    recs = _check_manual_review_bottleneck(session)
    assert len(recs) == 1
    assert "Tier C" in recs[0].action
    assert recs[0].priority == Priority.P2


def test_check_budget_warning() -> None:
    session = MagicMock()
    # Mock current_cost
    # Assuming budget is 25.0 (default), 80% is 20.0
    session.scalar.return_value = 21.0

    with patch("jobhunter.analytics.recommendations.Settings") as MockSettings:
        MockSettings.return_value.LLM_MONTHLY_BUDGET_USD = 25.0
        recs = _check_budget_warning(session)

    assert len(recs) == 1
    assert "presupuesto" in recs[0].reason
    assert recs[0].priority == Priority.P1


def test_check_circuit_breaker_stuck() -> None:
    session = MagicMock()
    # Mock stuck_breakers
    breaker = SourceHealth(
        source_name="LinkedIn",
        state=SourceState.OPEN,
        last_failure_at=datetime.now(timezone.utc) - timedelta(hours=25),
    )
    session.scalars.return_value.all.return_value = [breaker]

    recs = _check_circuit_breaker_stuck(session)
    assert len(recs) == 1
    assert "Investigar fuente 'LinkedIn'" in recs[0].action
    assert recs[0].priority == Priority.P1
