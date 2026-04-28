from typing import Any

import pytest
from datetime import date, datetime
from sqlalchemy.orm import Session
from sqlalchemy import event

from jobhunter.db.models import Job, Application, ApplicationEvent
from jobhunter.db.enums import ApplicationStatus, ApplicationEventType
from jobhunter.db.repos.application import ApplicationRepo


@pytest.fixture
def app_repo(db_session: Session) -> ApplicationRepo:
    return ApplicationRepo(db_session)


def test_create_for_job(app_repo: ApplicationRepo, sample_job: Job) -> None:
    # When
    app = app_repo.create_for_job(
        sample_job.id,
        application_method="LinkedIn",
        cv_variant="Senior",
    )

    # Then
    assert app.id is not None
    assert app.job_id == sample_job.id
    assert app.status == ApplicationStatus.APPLIED
    assert app.application_method == "LinkedIn"
    assert app.cv_variant == "Senior"


def test_transition_status_creates_event_with_note(
    app_repo: ApplicationRepo, sample_application: Application
) -> None:
    # Given
    app_id = sample_application.id

    # When
    event = app_repo.transition_status(app_id, ApplicationStatus.SCREENING, note="Good first call")

    # Then
    assert sample_application.status == ApplicationStatus.SCREENING
    assert event.application_id == app_id
    assert event.event_type == ApplicationEventType.STATUS_CHANGE
    assert event.event_data is not None
    assert event.event_data["old_status"] == ApplicationStatus.APPLIED
    assert event.event_data["new_status"] == ApplicationStatus.SCREENING
    assert event.event_data["note"] == "Good first call"


def test_transition_status_atomicity(
    app_repo: ApplicationRepo, sample_application: Application, db_session: Session
) -> None:
    # Given
    app_id = sample_application.id
    db_session.commit()  # Start a fresh transaction for the test

    # Simulate failure during event creation by adding a listener that raises an error
    @event.listens_for(ApplicationEvent, "before_insert")
    def fail_insert(mapper: Any, connection: Any, target: ApplicationEvent) -> None:
        if target.application_id == app_id:
            raise RuntimeError("Simulated failure")

    # When / Then
    # We use a savepoint (nested transaction) to allow rolling back ONLY the transition
    with pytest.raises(RuntimeError, match="Simulated failure"):
        with db_session.begin_nested():
            app_repo.transition_status(app_id, ApplicationStatus.INTERVIEW_1)

    # Verify rollback: status should still be 'applied' and no event should exist
    db_session.expire_all()
    refreshed_app = app_repo.get(app_id)
    assert refreshed_app is not None
    assert refreshed_app.status == ApplicationStatus.APPLIED

    events = db_session.query(ApplicationEvent).filter_by(application_id=app_id).all()
    # There might be 0 events or only those created before the failed transition
    assert all(
        e.event_data is not None and e.event_data.get("new_status") != ApplicationStatus.INTERVIEW_1
        for e in events
    )

    # Clean up the failing listener
    event.remove(ApplicationEvent, "before_insert", fail_insert)


def test_list_pending_followups(
    app_repo: ApplicationRepo, sample_job: Job, db_session: Session
) -> None:
    # Given
    today = date(2024, 1, 15)

    # 8 days ago -> Should be included (between 7 and 10)
    app1 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        status_updated_at=datetime(2024, 1, 7, 12, 0),
    )
    # 5 days ago -> Too recent
    app2 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        status_updated_at=datetime(2024, 1, 10, 12, 0),
    )
    # 12 days ago -> Too old
    app3 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        status_updated_at=datetime(2024, 1, 3, 12, 0),
    )
    # 8 days ago but different status
    app4 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.SCREENING,
        status_updated_at=datetime(2024, 1, 7, 12, 0),
    )

    db_session.add_all([app1, app2, app3, app4])
    db_session.flush()

    # When
    pending = app_repo.list_pending_followups(today)

    # Then
    assert len(pending) == 1
    assert pending[0].id == app1.id


def test_list_ghosted_candidates(
    app_repo: ApplicationRepo, sample_job: Job, db_session: Session
) -> None:
    # Given
    today = date(2024, 1, 25)

    # 22 days ago -> Should be included (> 21)
    app1 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        status_updated_at=datetime(2024, 1, 2, 12, 0),
    )
    # 20 days ago -> Not yet ghosted
    app2 = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        status_updated_at=datetime(2024, 1, 5, 12, 0),
    )

    db_session.add_all([app1, app2])
    db_session.flush()

    # When
    ghosted = app_repo.list_ghosted_candidates(today)

    # Then
    assert len(ghosted) == 1
    assert ghosted[0].id == app1.id
