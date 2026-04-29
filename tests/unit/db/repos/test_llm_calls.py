from datetime import datetime, timezone
from typing import Generator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.db.base import Base
from jobhunter.db.enums import LLMPurpose
from jobhunter.db.repos.llm_calls import LLMCallRepo


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    # We need to make sure JSONB is handled as JSON in SQLite for tests
    # But since we are using Base.metadata.create_all, it should use the type_annotation_map
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_record_call(session: Session) -> None:
    repo = LLMCallRepo(session)
    call = repo.record_call(
        model="claude-3-haiku",
        purpose=LLMPurpose.SCORING,
        success=True,
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=500,
    )

    assert call.id is not None
    assert call.model == "claude-3-haiku"
    assert call.purpose == LLMPurpose.SCORING
    assert call.success is True
    assert call.input_tokens == 100
    assert call.cost_usd == 0.001


def test_monthly_total_usd(session: Session) -> None:
    repo = LLMCallRepo(session)
    now = datetime.now(timezone.utc)

    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=1.0)
    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=2.0)

    # Another month
    # last_month = now.replace(day=1) - datetime.resolution
    # Manual insertion to control date if needed, but record_call uses now()
    # Let's mock datetime.now if we want to test different months
    # Or just use the current month for this test

    total = repo.monthly_total_usd(now.year, now.month)
    assert total == 3.0


def test_weekly_total_usd(session: Session) -> None:
    repo = LLMCallRepo(session)
    now = datetime.now(timezone.utc)

    repo.record_call(model="m1", purpose=LLMPurpose.SCORING, success=True, cost_usd=0.5)

    total = repo.weekly_total_usd(now)
    assert total == 0.5
