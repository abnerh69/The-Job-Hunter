from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.repos.llm_calls import LLMCallRepo


class BudgetExceededError(Exception):
    """
    Exception raised when the LLM budget is exceeded.
    """

    def __init__(self, current_spend: float, budget: float):
        self.current_spend = current_spend
        self.budget = budget
        super().__init__(
            f"LLM budget exceeded: ${current_spend:.2f} spent of ${budget:.2f} budget."
        )


class BudgetStatus(BaseModel):
    """
    Current status of the LLM budget.
    """

    current_month_spend: float
    budget: float
    pct_used: float
    is_exceeded: bool
    is_warning: bool


def check_budget(session: Session) -> BudgetStatus:
    """
    Checks the current LLM spend against the configured budget.

    Args:
        session: The SQLAlchemy session.

    Returns:
        A BudgetStatus object.

    Raises:
        BudgetExceededError: If the budget is exceeded.
    """
    settings = Settings()  # type: ignore[call-arg]
    repo = LLMCallRepo(session)
    now = datetime.now(timezone.utc)

    current_spend = repo.monthly_total_usd(now.year, now.month)
    budget = settings.LLM_MONTHLY_BUDGET_USD

    pct_used = (current_spend / budget) * 100 if budget > 0 else 0
    is_exceeded = current_spend >= budget
    is_warning = pct_used >= 80

    status = BudgetStatus(
        current_month_spend=current_spend,
        budget=budget,
        pct_used=pct_used,
        is_exceeded=is_exceeded,
        is_warning=is_warning,
    )

    if is_exceeded:
        raise BudgetExceededError(current_spend, budget)

    return status
