import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from jobhunter.db.models import Job
from jobhunter.db.session import get_session
from jobhunter.db.enums import JobStatus


def test_create_job() -> None:
    """
    Smoke test to verify that a Job can be created and persisted.
    """
    unique_id = str(uuid.uuid4())
    with get_session() as session:
        new_job = Job(
            source="test_source",
            url=f"https://example.com/job_{unique_id}",
            url_hash=f"hash_{unique_id}",
            title="Software Engineer",
            company="Tech Corp",
            description="A great job",
            status=JobStatus.NEW,
        )
        session.add(new_job)
        session.commit()

        # Query the job back
        job = session.query(Job).filter_by(url_hash=f"hash_{unique_id}").first()
        assert job is not None
        assert job.title == "Software Engineer"
        assert job.company == "Tech Corp"
        assert job.status == JobStatus.NEW
        assert job.id is not None


def test_job_unique_url_hash() -> None:
    """
    Smoke test to verify the UNIQUE constraint on url_hash.
    """
    unique_id = str(uuid.uuid4())
    with get_session() as session:
        job1 = Job(
            source="test_source",
            url=f"https://example.com/job_{unique_id}_1",
            url_hash=f"duplicate_hash_{unique_id}",
            title="Job 1",
            company="Company 1",
            description="Description 1",
        )
        session.add(job1)
        session.commit()

        job2 = Job(
            source="test_source",
            url=f"https://example.com/job_{unique_id}_2",
            url_hash=f"duplicate_hash_{unique_id}",
            title="Job 2",
            company="Company 2",
            description="Description 2",
        )
        session.add(job2)
        try:
            session.commit()
            pytest.fail("Should have raised IntegrityError")
        except IntegrityError:
            session.rollback()


def test_job_jsonb_fields() -> None:
    """
    Smoke test to verify JSONB fields and MutableDict behavior.
    """
    unique_id = str(uuid.uuid4())
    with get_session() as session:
        job = Job(
            source="test_source",
            url=f"https://example.com/job_{unique_id}",
            url_hash=f"hash_{unique_id}",
            title="AI Engineer",
            company="AI Corp",
            description="AI job",
            raw_payload={"original": "data"},
            score_data={"score": 85, "details": {"fit": "high"}},
        )
        session.add(job)
        session.commit()

        # Update JSONB field in-place
        assert job.score_data is not None
        job.score_data["score"] = 90
        session.commit()

        # Re-fetch and verify
        session.expire(job)
        updated_job = session.query(Job).filter_by(url_hash=f"hash_{unique_id}").first()
        assert updated_job is not None
        assert updated_job.score_data is not None
        assert updated_job.score_data["score"] == 90
        assert updated_job.raw_payload is not None
        assert updated_job.raw_payload["original"] == "data"
