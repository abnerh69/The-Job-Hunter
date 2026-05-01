from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import cost_metrics
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import LLMCall


def test_get_llm_costs(session: Session) -> None:
    call1 = LLMCall(
        model="claude-3-haiku",
        purpose=LLMPurpose.SCORING,
        cost_usd=0.001,
        called_at=datetime.now(timezone.utc),
    )
    call2 = LLMCall(
        model="claude-3-haiku",
        purpose=LLMPurpose.COVER_LETTER,
        cost_usd=0.005,
        called_at=datetime.now(timezone.utc),
    )
    session.add_all([call1, call2])
    session.commit()

    today = date.today()
    result = cost_metrics.get_llm_costs(session, today, today)

    assert result.total_cost_usd == 0.006
    assert result.purpose_breakdown[LLMPurpose.SCORING] == 0.001
    assert result.purpose_breakdown[LLMPurpose.COVER_LETTER] == 0.005
    assert len(result.daily_trend) == 1
    assert result.daily_trend[0].cost == 0.006
