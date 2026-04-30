import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from jobhunter.db.base import Base
from jobhunter.db.enums import (
    ApplicationEventType,
    ApplicationStatus,
    JobStatus,
    JobTier,
    LLMPurpose,
    OutreachMarket,
    OutreachMessageStatus,
    OutreachStatus,
    OutreachTemplateType,
    SourceState,
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
        default=uuid.uuid4,
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

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column()

    # Scoring (populated by SCORING LAYER)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    score_model: Mapped[str | None] = mapped_column(String(50))
    score_version: Mapped[str | None] = mapped_column(String(20))
    fit_score: Mapped[int | None] = mapped_column(Integer)
    tier: Mapped[JobTier | None] = mapped_column(String(10))
    score_data: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB().with_variant(JSON(), "sqlite"))
    )

    status: Mapped[JobStatus] = mapped_column(
        String(30), nullable=False, server_default=JobStatus.NEW
    )

    # Search vector (server-side generated)
    search_vector: Mapped[Any] = mapped_column(Text, FetchedValue(), deferred=True, nullable=True)

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
        default=uuid.uuid4,
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

    # Search vector (server-side generated)
    search_vector: Mapped[Any] = mapped_column(Text, FetchedValue(), deferred=True, nullable=True)

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
            postgresql_where=~status.in_(
                [
                    ApplicationStatus.REJECTED,
                    ApplicationStatus.GHOSTED,
                    ApplicationStatus.WITHDRAWN,
                    ApplicationStatus.OFFER,
                ]
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
        default=uuid.uuid4,
    )
    application_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False
    )
    event_type: Mapped[ApplicationEventType] = mapped_column(String(50), nullable=False)
    event_data: Mapped[dict[str, Any] | None] = mapped_column()
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    application: Mapped["Application"] = relationship(back_populates="events")

    # Indices
    __table_args__ = (Index("idx_events_app", "application_id", occurred_at.desc()),)

    def __repr__(self) -> str:
        return f"<ApplicationEvent(application_id={self.application_id}, event_type={self.event_type})>"


class OutreachContact(Base):
    """
    SQLAlchemy model for the 'outreach_contacts' table.
    Represents a contact for proactive outreach.
    """

    __tablename__ = "outreach_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text, unique=True)
    email: Mapped[str | None] = mapped_column(Text)

    market: Mapped[OutreachMarket | None] = mapped_column(String(50))
    specialty_stack: Mapped[str | None] = mapped_column(String(100))
    quality_score: Mapped[int | None] = mapped_column(Integer)

    first_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contact_count: Mapped[int] = mapped_column(Integer, server_default="0")

    status: Mapped[OutreachStatus] = mapped_column(
        String(30), nullable=False, server_default=OutreachStatus.NEW
    )
    notes: Mapped[str | None] = mapped_column(Text)

    # Search vector (server-side generated)
    search_vector: Mapped[Any] = mapped_column(Text, FetchedValue(), deferred=True, nullable=True)

    # Relationships
    messages: Mapped[list["OutreachMessage"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan"
    )

    # Indices
    __table_args__ = (Index("idx_outreach_followup", "status", "last_contacted_at"),)

    def __repr__(self) -> str:
        return f"<OutreachContact(name={self.name}, status={self.status})>"


class OutreachMessage(Base):
    """
    SQLAlchemy model for the 'outreach_messages' table.
    Tracks messages sent to outreach contacts.
    """

    __tablename__ = "outreach_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_contacts.id", ondelete="CASCADE"), nullable=False
    )
    template_type: Mapped[OutreachTemplateType] = mapped_column(String(50), nullable=False)
    template_version: Mapped[str | None] = mapped_column(String(20))
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    body_edited_by_user: Mapped[bool] = mapped_column(Boolean, server_default="false")
    research_notes: Mapped[str | None] = mapped_column(Text)
    model_used: Mapped[str | None] = mapped_column(String(50))
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))

    status: Mapped[OutreachMessageStatus] = mapped_column(
        String(30), nullable=False, server_default=OutreachMessageStatus.DRAFT
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    parent_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_messages.id"), nullable=True
    )

    # Relationships
    contact: Mapped["OutreachContact"] = relationship(back_populates="messages")
    parent_message: Mapped["OutreachMessage | None"] = relationship(
        remote_side=[id], backref="followups"
    )

    # Indices
    __table_args__ = (
        Index("idx_outreach_messages_contact_created", "contact_id", created_at.desc()),
        Index(
            "idx_outreach_messages_status_sent",
            "status",
            "sent_at",
            postgresql_where=status.in_([OutreachMessageStatus.SENT, OutreachMessageStatus.DRAFT]),
        ),
    )

    def __repr__(self) -> str:
        return f"<OutreachMessage(contact_id={self.contact_id}, status={self.status})>"


class SourceHealth(Base):
    """
    SQLAlchemy model for the 'source_health' table.
    Tracks the health and circuit breaker state of each job source.
    """

    __tablename__ = "source_health"

    source_name: Mapped[str] = mapped_column(String(50), primary_key=True)
    state: Mapped[SourceState] = mapped_column(
        String(20), nullable=False, server_default=SourceState.CLOSED
    )
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:
        return f"<SourceHealth(source_name={self.source_name}, state={self.state}, failures={self.failure_count})>"


class LLMCall(Base):
    """
    SQLAlchemy model for the 'llm_calls' table.
    Tracks individual calls to LLM APIs for cost and performance monitoring.
    """

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    purpose: Mapped[LLMPurpose] = mapped_column(String(30), nullable=False)
    prompt_version: Mapped[str | None] = mapped_column(String(20))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    job: Mapped["Job"] = relationship()

    def __repr__(self) -> str:
        return f"<LLMCall(model={self.model}, cost_usd={self.cost_usd}, success={self.success})>"


class NotificationSent(Base):
    """
    SQLAlchemy model for the 'notifications_sent' table.
    Tracks sent notifications to ensure idempotency and for auditing.
    """

    __tablename__ = "notifications_sent"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=True
    )
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    provider_message_id: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    # Relationships
    job: Mapped["Job"] = relationship()

    # Indices and Constraints
    __table_args__ = (
        Index("idx_notifications_sent_dedup", "channel", "dedup_key", unique=True),
        Index("idx_notifications_sent_job_channel", "job_id", "channel"),
    )

    def __repr__(self) -> str:
        return f"<NotificationSent(channel={self.channel}, dedup_key={self.dedup_key}, success={self.success})>"


class OAuthToken(Base):
    """
    SQLAlchemy model for the 'oauth_tokens' table.
    Stores encrypted OAuth2 tokens for various providers.
    """

    __tablename__ = "oauth_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    account_email: Mapped[str] = mapped_column(String(255), nullable=False)

    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scopes: Mapped[list[str] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index("idx_oauth_provider_email", "provider", "account_email", unique=True),)

    def __repr__(self) -> str:
        return f"<OAuthToken(provider={self.provider}, email={self.account_email})>"


@event.listens_for(Application.status, "set")
def receive_status_change(target: Application, value: str, oldvalue: Any, initiator: Any) -> None:
    """
    Automatically creates an ApplicationEvent when the status of an Application changes.
    """
    # Filter out initial values or non-changes.
    # We check if the target has an ID to ensure it's an existing record being updated,
    # rather than a new record being initialized with a default status.
    if (
        target.id is None
        or oldvalue is None
        or str(oldvalue) in ("NO_VALUE", "NEVER_SET")
        or value == oldvalue
    ):
        return

    session = object_session(target)

    note = getattr(target, "_transition_note", None)
    event_data = {"old_status": str(oldvalue), "new_status": str(value)}
    if note:
        event_data["note"] = note

    event_log = ApplicationEvent(
        application_id=target.id,
        event_type=ApplicationEventType.STATUS_CHANGE,
        event_data=event_data,
    )

    if session:
        session.add(event_log)
    else:
        # If no session, add to the collection to be persisted when the parent is saved
        if target.events is None:
            target.events = []
        target.events.append(event_log)
