from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import prompt_metrics
from jobhunter.db.enums import LLMPurpose, JobTier
from jobhunter.db.models import Job, LLMCall


def test_get_prompt_performance(session: Session) -> None:
    call = LLMCall(
        model="claude-3-haiku",
        purpose=LLMPurpose.SCORING,
        prompt_version="v1",
        success=True,
        cost_usd=0.001,
        called_at=datetime.now(timezone.utc),
    )
    session.add(call)

    job = Job(
        title="Job",
        company="Co",
        source="S1",
        url="url",
        url_hash="h",
        description="description",
        tier=JobTier.A,
        score_version="v1",
    )
    session.add(job)
    session.commit()

    today = date.today()
    results = prompt_metrics.get_prompt_performance(session, today, today)

    assert len(results) == 1
    assert results[0].prompt_version == "v1"
    assert results[0].outcomes[str(JobTier.A)] == 1
