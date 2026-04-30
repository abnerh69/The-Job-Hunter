import pytest
import uuid
from datetime import datetime, timezone
from jobhunter.db.models import Job
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.enums import JobTier, JobStatus

from jobhunter.db.base import Base

def test_list_new_matches_filters(session):
    Base.metadata.create_all(bind=session.get_bind())
    repo = JobRepo(session)

    # Create test jobs
    job1 = Job(
        title="Python Developer",
        company="PyCo",
        source="Linkedin",
        url="http://test.com/1",
        url_hash="hash1",
        description="Python backend role",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
        fit_score=90,
        score_data={
            "valid": True,
            "role": {"primary_stack_match": ["Python"], "is_ai_ml_role": False},
            "compensation": {"salary_min_usd_month": 5000}
        }
    )
    job2 = Job(
        title="Flutter Engineer",
        company="FlutterCo",
        source="WWR",
        url="http://test.com/2",
        url_hash="hash2",
        description="Flutter mobile role",
        tier=JobTier.B,
        status=JobStatus.QUEUED,
        fit_score=80,
        score_data={
            "valid": True,
            "role": {"is_flutter_role": True, "is_ai_ml_role": False},
            "compensation": {"salary_min_usd_month": 6000}
        }
    )
    job3 = Job(
        title="AI Researcher",
        company="AICo",
        source="Linkedin",
        url="http://test.com/3",
        url_hash="hash3",
        description="AI ML role",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
        fit_score=95,
        score_data={
            "valid": True,
            "role": {"is_ai_ml_role": True},
            "compensation": {"salary_min_usd_month": 8000}
        }
    )

    session.add_all([job1, job2, job3])
    session.commit()

    # Test Tier filter
    results = repo.list_new_matches(tiers=[JobTier.A])
    assert len(results) == 2
    assert all(j.tier == JobTier.A for j in results)

    # Test Source filter
    results = repo.list_new_matches(sources=["WWR"])
    assert len(results) == 1
    assert results[0].source == "WWR"

    # Test Min Score filter
    results = repo.list_new_matches(min_score=92)
    assert len(results) == 1
    assert results[0].fit_score == 95

    # Test Min Salary filter
    results = repo.list_new_matches(min_salary=7000)
    assert len(results) == 1
    assert results[0].title == "AI Researcher"

    # Test Stack filter
    results = repo.list_new_matches(stacks=["Flutter"])
    assert len(results) == 1
    assert results[0].title == "Flutter Engineer"

    results = repo.list_new_matches(stacks=["AI/ML"])
    assert len(results) == 1
    assert results[0].title == "AI Researcher"

    results = repo.list_new_matches(stacks=["Python"])
    assert len(results) == 1
    assert results[0].title == "Python Developer"

def test_get_dashboard_metrics(session):
    Base.metadata.create_all(bind=session.get_bind())
    repo = JobRepo(session)

    # Job from today
    job1 = Job(
        title="New Job", company="NewCo", source="src", url="u1", url_hash="h1",
        description="d", tier=JobTier.A, status=JobStatus.QUEUED,
        scraped_at=datetime.now(timezone.utc)
    )
    # Job from yesterday
    from datetime import timedelta
    job2 = Job(
        title="Old Job", company="OldCo", source="src", url="u2", url_hash="h2",
        description="d", tier=JobTier.A, status=JobStatus.QUEUED,
        scraped_at=datetime.now(timezone.utc) - timedelta(days=1)
    )

    session.add_all([job1, job2])
    session.commit()

    metrics = repo.get_dashboard_metrics()
    assert metrics["new_today"] == 1
    assert metrics["pending_a"] == 2
