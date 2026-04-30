import uuid
from datetime import datetime, timezone, timedelta
from typing import Generator
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.db.base import Base
from jobhunter.db.models import Job
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.repos.job import JobRepo

@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session_factory = sessionmaker(bind=engine)
    session = Session_factory()
    yield session
    session.close()

def test_list_new_matches_filtering(session: Session) -> None:
    repo = JobRepo(session)

    # Create test data
    job1 = Job(
        source="LinkedIn",
        url="https://example.com/1",
        url_hash="hash1",
        title="Python Backend Developer",
        company="Tech Co",
        description="We need a Python developer.",
        status=JobStatus.QUEUED,
        tier=JobTier.A,
        fit_score=90,
        score_data={
            "role": {"title_normalized": "Backend Developer", "primary_stack_match": ["Python"]},
            "compensation": {"salary_max_usd_month": 8000}
        }
    )

    job2 = Job(
        source="Indeed",
        url="https://example.com/2",
        url_hash="hash2",
        title="Flutter Engineer",
        company="Mobile App Inc",
        description="Flutter dev role.",
        status=JobStatus.QUEUED,
        tier=JobTier.B,
        fit_score=75,
        score_data={
            "role": {"title_normalized": "Mobile Developer", "is_flutter_role": True},
            "compensation": {"salary_max_usd_month": 5000}
        }
    )

    job3 = Job(
        source="Direct",
        url="https://example.com/3",
        url_hash="hash3",
        title="AI Researcher",
        company="AI Lab",
        description="AI/ML stuff.",
        status=JobStatus.QUEUED,
        tier=JobTier.A,
        fit_score=95,
        score_data={
            "role": {"title_normalized": "AI Engineer", "is_ai_ml_role": True},
            "compensation": {"salary_max_usd_month": 12000}
        }
    )

    job4 = Job(
        source="LinkedIn",
        url="https://example.com/4",
        url_hash="hash4",
        title="Archived Python Job",
        company="Old Tech",
        description="Old job.",
        status=JobStatus.ARCHIVED,
        tier=JobTier.A,
        fit_score=85,
        score_data={
            "role": {"title_normalized": "Python dev", "primary_stack_match": ["Python"]},
        }
    )

    session.add_all([job1, job2, job3, job4])
    session.commit()

    # 1. Filter by Tier
    matches = repo.list_new_matches(tiers=[JobTier.A])
    assert len(matches) == 2
    assert all(j.tier == JobTier.A for j in matches)
    assert all(j.status == JobStatus.QUEUED for j in matches)

    # 2. Filter by Source
    matches = repo.list_new_matches(sources=["Indeed"])
    assert len(matches) == 1
    assert matches[0].source == "Indeed"

    # 3. Filter by Min Score
    matches = repo.list_new_matches(min_score=92)
    assert len(matches) == 1
    assert matches[0].fit_score == 95

    # 4. Filter by Stack (Python)
    matches = repo.list_new_matches(stacks=["Python"])
    assert len(matches) == 1
    assert "Python" in matches[0].title

    # 5. Filter by Stack (Flutter)
    matches = repo.list_new_matches(stacks=["Flutter"])
    assert len(matches) == 1
    assert "Flutter" in matches[0].title

    # 6. Filter by multiple stacks
    matches = repo.list_new_matches(stacks=["Python", "AI/ML"])
    assert len(matches) == 2

def test_get_dashboard_metrics(session: Session) -> None:
    repo = JobRepo(session)
    now = datetime.now(timezone.utc)

    # Jobs scraped today
    job1 = Job(
        source="Source1", url="url1", url_hash="h1", title="T1", company="C1", description="D1",
        scraped_at=now, status=JobStatus.QUEUED, tier=JobTier.A
    )
    job2 = Job(
        source="Source2", url="url2", url_hash="h2", title="T2", company="C2", description="D2",
        scraped_at=now, status=JobStatus.QUEUED, tier=JobTier.B
    )

    # Job scraped yesterday
    job3 = Job(
        source="Source3", url="url3", url_hash="h3", title="T3", company="C3", description="D3",
        scraped_at=now - timedelta(days=1), status=JobStatus.QUEUED, tier=JobTier.A
    )

    session.add_all([job1, job2, job3])
    session.commit()

    metrics = repo.get_dashboard_metrics()

    assert metrics["jobs_today"] == 2
    assert metrics["pending_a"] == 2 # job1 and job3
