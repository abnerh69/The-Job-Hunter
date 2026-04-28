import pytest
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from jobhunter.db.models import Job, Application, ApplicationEvent
from jobhunter.db.enums import (
    ApplicationEventType,
    ApplicationStatus,
    JobStatus,
)


def test_create_job(session: Session) -> None:
    """
    Smoke test to verify that a Job can be created and persisted.
    """
    unique_id = str(uuid.uuid4())
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
    session.flush()

    # Query the job back
    job = session.query(Job).filter_by(url_hash=f"hash_{unique_id}").first()
    assert job is not None
    assert job.title == "Software Engineer"
    assert job.company == "Tech Corp"
    assert job.status == JobStatus.NEW
    assert job.id is not None


def test_job_unique_url_hash(session: Session) -> None:
    """
    Smoke test to verify the UNIQUE constraint on url_hash.
    """
    unique_id = str(uuid.uuid4())
    job1 = Job(
        source="test_source",
        url=f"https://example.com/job_{unique_id}_1",
        url_hash=f"duplicate_hash_{unique_id}",
        title="Job 1",
        company="Company 1",
        description="Description 1",
    )
    session.add(job1)
    session.flush()

    job2 = Job(
        source="test_source",
        url=f"https://example.com/job_{unique_id}_2",
        url_hash=f"duplicate_hash_{unique_id}",
        title="Job 2",
        company="Company 2",
        description="Description 2",
    )
    session.add(job2)
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


def test_job_jsonb_fields(session: Session) -> None:
    """
    Smoke test to verify JSONB fields and MutableDict behavior.
    """
    unique_id = str(uuid.uuid4())
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
    session.flush()

    # Update JSONB field in-place
    assert job.score_data is not None
    job.score_data["score"] = 90
    session.flush()

    # Re-fetch and verify
    session.expire(job)
    updated_job = session.query(Job).filter_by(url_hash=f"hash_{unique_id}").first()
    assert updated_job is not None
    assert updated_job.score_data is not None
    assert isinstance(updated_job.score_data, dict)
    assert updated_job.score_data["score"] == 90
    assert updated_job.raw_payload is not None
    assert isinstance(updated_job.raw_payload, dict)
    assert updated_job.raw_payload["original"] == "data"


def test_application_workflow(session: Session) -> None:
    """
    Test the creation of an Application and the automatic generation of ApplicationEvents.
    """
    unique_id = str(uuid.uuid4())
    # Create a Job
    job = Job(
        source="test_source",
        url=f"https://example.com/job_{unique_id}",
        url_hash=f"hash_{unique_id}",
        title="Workflow Engineer",
        company="Workflow Corp",
        description="A job for testing workflow",
    )
    session.add(job)
    session.flush()

    # Create an Application
    app = Application(
        job=job,
        status=ApplicationStatus.APPLIED,
    )
    session.add(app)
    session.flush()

    # Verify Application creation
    assert app.id is not None
    assert app.job_id == job.id
    assert app.status == ApplicationStatus.APPLIED
    assert len(app.events) == 0  # Initial set should not trigger event in this implementation

    # Update status
    app.status = ApplicationStatus.SCREENING
    session.flush()
    session.refresh(app)

    # Verify Event creation
    assert len(app.events) == 1
    event_obj = app.events[0]
    assert event_obj.event_type == ApplicationEventType.STATUS_CHANGE
    assert isinstance(event_obj.event_data, dict)
    assert event_obj.event_data["old_status"] == ApplicationStatus.APPLIED
    assert event_obj.event_data["new_status"] == ApplicationStatus.SCREENING

    # Cascade delete test
    session.delete(app)
    session.flush()

    # Verify Application and Events are deleted
    deleted_app = session.get(Application, app.id)
    assert deleted_app is None
    deleted_event = session.get(ApplicationEvent, event_obj.id)
    assert deleted_event is None
