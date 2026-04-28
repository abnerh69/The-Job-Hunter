import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, event, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship, attributes, object_session

from jobhunter.db.base import Base
from jobhunter.db.enums import (
    ApplicationEventType,
    ApplicationStatus,
    JobStatus,
    JobTier,
)


class Job(Base):
    """
    SQLAlchemy model for the 'jobs' table.
    Represents a job offer ingested from various sources.
    """

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text, nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    location_raw: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Scoring (populated by SCORING LAYER)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_model: Mapped[str | None] = mapped_column(String(50))
    score_version: Mapped[str | None] = mapped_column(String(20))
    fit_score: Mapped[int | None] = mapped_column(Integer)
    tier: Mapped[JobTier | None] = mapped_column(String(10))
    score_data: Mapped[dict[str, Any] | None] = mapped_column(MutableDict.as_mutable(JSONB))

    status: Mapped[JobStatus] = mapped_column(
        String(30), nullable=False, server_default=JobStatus.NEW
    )

    # Relationships
    applications: Mapped[list["Application"]] = relationship(back_populates="job")

    # Indices
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_tier", "tier"),
        Index("idx_jobs_scraped_at", scraped_at.desc()),
        Index("idx_jobs_company", "company"),
    )

    def __repr__(self) -> str:
        return f"<Job(title={self.title}, company={self.company}, status={self.status})>"


class Application(Base):
    """
    SQLAlchemy model for the 'applications' table.
    Represents an application submitted for a job.
    """

    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False
    )

    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    application_method: Mapped[str | None] = mapped_column(String(50))
    cv_variant: Mapped[str | None] = mapped_column(String(50))

    cover_letter_text: Mapped[str | None] = mapped_column(Text)
    cover_letter_model: Mapped[str | None] = mapped_column(String(50))

    contact_name: Mapped[str | None] = mapped_column(Text)
    contact_email: Mapped[str | None] = mapped_column(Text)
    contact_linkedin: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ApplicationStatus] = mapped_column(
        String(30), nullable=False, server_default=ApplicationStatus.APPLIED
    )
    status_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    next_action: Mapped[str | None] = mapped_column(Text)
    next_action_due: Mapped[date | None] = mapped_column(Date)

    salary_offered_min: Mapped[int | None] = mapped_column(Integer)
    salary_offered_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(10))
    contract_type: Mapped[str | None] = mapped_column(String(20))

    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="applications")
    events: Mapped[list["ApplicationEvent"]] = relationship(
        back_populates="application", cascade="all, delete-orphan"
    )

    # Indices
    __table_args__ = (
        Index("idx_apps_status", "status"),
        Index(
            "idx_apps_next_action_due",
            "next_action_due",
            postgresql_where=(
                status.in_(
                    [
                        ApplicationStatus.REJECTED,
                        ApplicationStatus.GHOSTED,
                        ApplicationStatus.WITHDRAWN,
                        ApplicationStatus.OFFER,
                    ]
                )
                == False
            ),
        ),
    )

    def __repr__(self) -> str:
        return f"<Application(job_id={self.job_id}, status={self.status})>"


class ApplicationEvent(Base):
    """
    SQLAlchemy model for the 'application_events' table.
    Audit log for application status changes and other events.
    """

    __tablename__ = "application_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    event_type: Mapped[ApplicationEventType] = mapped_column(String(50), nullable=False)
    event_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    application: Mapped["Application"] = relationship(back_populates="events")

    # Indices
    __table_args__ = (
        Index("idx_events_app", "application_id", occurred_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<ApplicationEvent(application_id={self.application_id}, event_type={self.event_type})>"


@event.listens_for(Application.status, "set")
def receive_status_change(target: Application, value: str, oldvalue: str, initiator: Any) -> None:
    """
    Automatically creates an ApplicationEvent when the status of an Application changes.
    """
    if oldvalue == attributes.NO_VALUE or value == oldvalue:
        return

    session = object_session(target)

    event_log = ApplicationEvent(
        application_id=target.id,
        event_type=ApplicationEventType.STATUS_CHANGE,
        event_data={"old_status": str(oldvalue), "new_status": str(value)},
    )

    if session:
        session.add(event_log)
    else:
        # If no session, add to the collection to be persisted when the parent is saved
        if target.events is None:
            target.events = []
        target.events.append(event_log)
