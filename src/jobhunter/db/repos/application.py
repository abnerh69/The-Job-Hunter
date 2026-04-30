import uuid
from datetime import date, timedelta
from typing import Any, Sequence

from sqlalchemy import and_, extract, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationEventType, ApplicationStatus
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

    def list_pipeline(
        self,
        methods: list[str] | None = None,
        month: int | None = None,
        year: int | None = None,
        include_terminal: bool = False,
    ) -> Sequence[Application]:
        """
        Lists applications for the pipeline view with filtering.

        Args:
            methods (list[str] | None): Filter by application methods.
            month (int | None): Filter by application month (1-12).
            year (int | None): Filter by application year.
            include_terminal (bool): Whether to include terminal states (rejected, ghosted, etc).

        Returns:
            Sequence[Application]: A sequence of applications.
        """
        stmt = select(Application).join(Application.job)

        if not include_terminal:
            stmt = stmt.where(
                ~Application.status.in_(
                    [
                        ApplicationStatus.REJECTED,
                        ApplicationStatus.GHOSTED,
                        ApplicationStatus.WITHDRAWN,
                        ApplicationStatus.OFFER,
                    ]
                )
            )

        if methods:
            stmt = stmt.where(Application.application_method.in_(methods))

        if month:
            stmt = stmt.where(extract("month", Application.applied_at) == month)
        if year:
            stmt = stmt.where(extract("year", Application.applied_at) == year)

        stmt = stmt.order_by(Application.applied_at.desc())
        return self.session.scalars(stmt).all()

    def get_pipeline_metrics(self) -> dict[str, Any]:
        """
        Calculates metrics for the application pipeline.

        Returns:
            dict[str, Any]: A dictionary with total_active, mean_age_days, and urgent_actions.
        """
        active_statuses = [
            ApplicationStatus.APPLIED,
            ApplicationStatus.SCREENING,
            ApplicationStatus.INTERVIEW_1,
            ApplicationStatus.INTERVIEW_N,
        ]

        # Total active apps
        count_stmt = select(func.count(Application.id)).where(
            Application.status.in_(active_statuses)
        )
        total_active = self.session.scalar(count_stmt) or 0

        # Mean age in days
        mean_age = 0.0
        if total_active > 0:
            is_postgres = False
            if self.session.bind:
                is_postgres = self.session.bind.dialect.name == "postgresql"

            if is_postgres:
                age_stmt = select(func.avg(func.now() - Application.applied_at)).where(
                    Application.status.in_(active_statuses)
                )
                avg_interval = self.session.scalar(age_stmt)
                if avg_interval:
                    mean_age = float(avg_interval.days) + (avg_interval.seconds / 86400.0)
            else:
                # SQLite fallback
                age_stmt = select(
                    func.avg(func.julianday("now") - func.julianday(Application.applied_at))
                ).where(Application.status.in_(active_statuses))
                mean_age = float(self.session.scalar(age_stmt) or 0.0)

        # Urgent actions
        urgent_stmt = (
            select(Application)
            .where(
                and_(
                    Application.status.in_(active_statuses),
                    Application.next_action_due.is_not(None),
                )
            )
            .order_by(Application.next_action_due.asc())
            .limit(3)
        )
        urgent_apps = self.session.scalars(urgent_stmt).all()
        urgent_actions = [
            {"company": app.job.company, "action": app.next_action, "due": app.next_action_due}
            for app in urgent_apps
        ]

        return {
            "total_active": total_active,
            "mean_age_days": round(mean_age, 1),
            "urgent_actions": urgent_actions,
        }

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
