import uuid
from datetime import date, timedelta
from typing import Any, Sequence

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, ApplicationEventType
from jobhunter.db.models import Application, ApplicationEvent
from jobhunter.db.repos.base import BaseRepo


class ApplicationRepo(BaseRepo[Application]):
    """
    Repository for Application model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the ApplicationRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(Application, session)

    def create_for_job(self, job_id: uuid.UUID, **kwargs: Any) -> Application:
        """
        Creates a new application for a specific job.

        Args:
            job_id (uuid.UUID): The ID of the job.
            **kwargs (Any): Additional fields for the application.

        Returns:
            Application: The created application.
        """
        app = Application(job_id=job_id, **kwargs)
        return self.create(app)

    def transition_status(
        self, app_id: uuid.UUID, new_status: ApplicationStatus, note: str | None = None
    ) -> ApplicationEvent:
        """
        Transitions the status of an application and creates an audit event.
        This operation is atomic within a transaction.

        Args:
            app_id (uuid.UUID): The ID of the application.
            new_status (ApplicationStatus): The new status to transition to.
            note (str | None): An optional note to include in the event data.

        Returns:
            ApplicationEvent: The created status change event.

        Raises:
            ValueError: If the application is not found.
        """
        app = self.get(app_id)
        if not app:
            raise ValueError(f"Application with id {app_id} not found")

        # Pass the note to the listener via a temporary attribute
        if note:
            setattr(app, "_transition_note", note)

        # This will trigger the listener in models.py which creates the ApplicationEvent
        app.status = new_status
        self.session.flush()

        # Find the newly created event to return it
        stmt = (
            select(ApplicationEvent)
            .where(
                and_(
                    ApplicationEvent.application_id == app_id,
                    ApplicationEvent.event_type == ApplicationEventType.STATUS_CHANGE,
                )
            )
            .order_by(ApplicationEvent.occurred_at.desc())
            .limit(1)
        )
        event = self.session.scalar(stmt)
        if not event:
            # Fallback in case listener didn't fire as expected (though it should)
            event_data = {
                "old_status": "UNKNOWN",  # Ideally we should have kept old_status
                "new_status": str(new_status),
            }
            if note:
                event_data["note"] = note
            event = ApplicationEvent(
                application_id=app_id,
                event_type=ApplicationEventType.STATUS_CHANGE,
                event_data=event_data,
            )
            self.session.add(event)
            self.session.flush()

        return event

    def list_pending_followups(self, today: date) -> Sequence[Application]:
        """
        Lists applications that are pending a follow-up.
        Criteria: status='applied' AND status_updated_at between 7 and 10 days ago.

        Args:
            today (date): The reference date for the follow-up check.

        Returns:
            Sequence[Application]: A sequence of applications due for follow-up.
        """
        start_date = today - timedelta(days=10)
        end_date = today - timedelta(days=7)

        stmt = select(Application).where(
            and_(
                Application.status == ApplicationStatus.APPLIED,
                func.date(Application.status_updated_at) >= start_date,
                func.date(Application.status_updated_at) <= end_date,
            )
        )
        return self.session.scalars(stmt).all()

    def list_ghosted_candidates(self, today: date) -> Sequence[Application]:
        """
        Lists applications that are considered ghosted.
        Criteria: status='applied' AND status_updated_at > 21 days ago.

        Args:
            today (date): The reference date for the ghosting check.

        Returns:
            Sequence[Application]: A sequence of ghosted applications.
        """
        threshold_date = today - timedelta(days=21)

        stmt = select(Application).where(
            and_(
                Application.status == ApplicationStatus.APPLIED,
                func.date(Application.status_updated_at) < threshold_date,
            )
        )
        return self.session.scalars(stmt).all()
