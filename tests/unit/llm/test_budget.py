from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobhunter.db.base import Base
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.llm.budget import BudgetExceededError, check_budget


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@patch("jobhunter.llm.budget.Settings")
def test_check_budget_ok(mock_settings, session) -> None:
    mock_settings.return_value.LLM_MONTHLY_BUDGET_USD = 10.0
    repo = LLMCallRepo(session)
    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=5.0)

    status = check_budget(session)
    assert status.current_month_spend == 5.0
    assert status.pct_used == 50.0
    assert status.is_exceeded is False
    assert status.is_warning is False


@patch("jobhunter.llm.budget.Settings")
def test_check_budget_warning(mock_settings, session) -> None:
    mock_settings.return_value.LLM_MONTHLY_BUDGET_USD = 10.0
    repo = LLMCallRepo(session)
    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=8.5)

    status = check_budget(session)
    assert status.pct_used == 85.0
    assert status.is_warning is True
    assert status.is_exceeded is False


@patch("jobhunter.llm.budget.Settings")
def test_check_budget_exceeded(mock_settings, session) -> None:
    mock_settings.return_value.LLM_MONTHLY_BUDGET_USD = 10.0
    repo = LLMCallRepo(session)
    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=11.0)

    with pytest.raises(BudgetExceededError) as excinfo:
        check_budget(session)

    assert "LLM budget exceeded" in str(excinfo.value)
    assert excinfo.value.current_spend == 11.0
    assert excinfo.value.budget == 10.0
