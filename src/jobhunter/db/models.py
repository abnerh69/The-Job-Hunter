import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    FetchedValue,
    Float,
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
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, object_session, relationship

from jobhunter.db.base import Base
from jobhunter.db.enums import (
    ABTestStatus,
    RecommendationStatus,
    ApplicationEventType,
    ApplicationStatus,
    AuditEventType,
    EmailMatchStatus,
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

    manually_promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manually_promoted_reason: Mapped[str | None] = mapped_column(Text)

    # Search vector (server-side generated)
    search_vector: Mapped[Any] = mapped_column(Text, FetchedValue(), deferred=True, nullable=True)

    # Relationships
    applications: Mapped[list["Application"]] = relationship(back_populates="job")
    profile_scores: Mapped[list["JobProfileScore"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )

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


class EmailMessage(Base):
    """
    SQLAlchemy model for the 'email_messages' table.
    Stores metadata for processed emails to track matches and ensure idempotency.
    """

    __tablename__ = "email_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    gmail_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    gmail_thread_id: Mapped[str | None] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    from_email: Mapped[str] = mapped_column(String(255), nullable=False)
    from_domain: Mapped[str | None] = mapped_column(String(255))
    subject: Mapped[str | None] = mapped_column(Text)
    snippet: Mapped[str | None] = mapped_column(String(200))
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    match_status: Mapped[EmailMatchStatus] = mapped_column(
        String(30), nullable=False, server_default=EmailMatchStatus.UNMATCHED
    )
    matched_application_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("applications.id"), nullable=True
    )
    matched_outreach_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("outreach_messages.id"), nullable=True
    )
    match_confidence: Mapped[float | None] = mapped_column(Float)
    match_reasoning: Mapped[str | None] = mapped_column(Text)
    suggested_status_change: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite")
    )
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    matched_application: Mapped["Application | None"] = relationship()
    matched_outreach_message: Mapped["OutreachMessage | None"] = relationship()

    # Indices and Constraints
    __table_args__ = (
        Index("idx_email_from_domain", from_domain),
        Index("idx_email_match_status", match_status),
        Index("idx_email_received_at", received_at.desc()),
        CheckConstraint(
            "(matched_application_id IS NULL) OR (matched_outreach_message_id IS NULL)",
            name="check_only_one_match_target",
        ),
    )

    def __repr__(self) -> str:
        return f"<EmailMessage(gmail_id={self.gmail_message_id}, status={self.match_status})>"


class ABTest(Base):
    """
    SQLAlchemy model for the 'ab_tests' table.
    Tracks A/B tests for prompts and templates.
    """

    __tablename__ = "ab_tests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    metric_target: Mapped[str] = mapped_column(String(100), nullable=False)
    variants: Mapped[dict[str, float]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[ABTestStatus] = mapped_column(
        String(20), nullable=False, server_default=ABTestStatus.ACTIVE
    )
    conclusion: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<ABTest(name={self.name}, status={self.status})>"


class FailedLoginAttempt(Base):
    """
    SQLAlchemy model for the 'failed_login_attempts' table.
    Tracks login attempts for rate limiting and abuse prevention.
    """

    __tablename__ = "failed_login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    user_agent: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)  # success | failure

    __table_args__ = (Index("idx_failed_login_ip_time", "ip_address", "attempted_at"),)

    def __repr__(self) -> str:
        return f"<FailedLoginAttempt(ip={self.ip_address}, outcome={self.outcome}, at={self.attempted_at})>"


class BlockedIP(Base):
    """
    SQLAlchemy model for the 'blocked_ips' table.
    Stores IPs that are currently blocked due to multiple failed login attempts.
    """

    __tablename__ = "blocked_ips"

    ip_address: Mapped[str] = mapped_column(String(45), primary_key=True)
    blocked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    unblock_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)

    def __repr__(self) -> str:
        return f"<BlockedIP(ip={self.ip_address}, unblock_at={self.unblock_at})>"


class RecommendationState(Base):
    """
    SQLAlchemy model for tracking the state of analytics recommendations.
    """

    __tablename__ = "recommendation_states"

    reco_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[RecommendationStatus] = mapped_column(
        String(20), nullable=False, server_default=RecommendationStatus.PENDING
    )
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AuditLog(Base):
    """
    SQLAlchemy model for the 'audit_log' table.
    Stores auditable events for compliance and security.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_type: Mapped[AuditEventType] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    target_entity: Mapped[str | None] = mapped_column(String(50))
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB().with_variant(JSON(), "sqlite"), nullable=True
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    # Indices
    __table_args__ = (
        Index("idx_audit_event_time", "event_type", created_at.desc()),
        Index("idx_audit_actor_time", "actor", created_at.desc()),
        Index("idx_audit_target", "target_entity", "target_id"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(event_type={self.event_type}, actor={self.actor}, action={self.action})>"


class CandidateProfile(Base):
    """
    SQLAlchemy model for the 'candidate_profiles' table.
    Represents the candidate's profile data.
    """

    __tablename__ = "candidate_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", default=True)

    seniority: Mapped[str | None] = mapped_column(String(50))
    years_experience: Mapped[int | None] = mapped_column(Integer)
    country: Mapped[str | None] = mapped_column(String(50))
    work_authorization: Mapped[str | None] = mapped_column(Text)
    timezone_home: Mapped[str | None] = mapped_column(String(50))
    overlap_max_hours_cet: Mapped[int | None] = mapped_column(Integer)
    preferred_overlap_cet: Mapped[int | None] = mapped_column(Integer)

    primary_stack: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    secondary_stack: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    domains: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    languages: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB().with_variant(JSON(), "sqlite"))
    )
    compensation: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB().with_variant(JSON(), "sqlite"))
    )
    contract_preferences: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    hard_blockers: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    soft_negatives: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    positive_signals: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    payment_methods_ok: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Relationships
    history: Mapped[list["CandidateProfileHistory"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )
    cv_variants: Mapped[list["CVVariant"]] = relationship(
        back_populates="profile", cascade="all, delete-orphan"
    )

    # Indices
    __table_args__ = (
        Index(
            "idx_profiles_is_active",
            "is_active",
            postgresql_where=is_active.is_(True),
        ),
    )

    def to_yaml_string(self) -> str:
        """
        Returns a YAML representation of the profile for prompt injection.
        """
        import yaml

        data = {
            "name": self.name,
            "seniority": self.seniority,
            "years_experience": self.years_experience,
            "location_legal": {
                "country": self.country,
                "work_authorization": self.work_authorization,
                "payment_methods_ok": self.payment_methods_ok,
            },
            "timezone": {
                "home": self.timezone_home,
                "overlap_max_acceptable_hours_with_CET": self.overlap_max_hours_cet,
                "preferred_overlap_CET": self.preferred_overlap_cet,
            },
            "primary_stack": self.primary_stack,
            "secondary_stack": self.secondary_stack,
            "domains": self.domains,
            "languages": self.languages,
            "compensation": self.compensation,
            "contract_preferences": self.contract_preferences,
            "hard_blockers": self.hard_blockers,
            "soft_negatives": self.soft_negatives,
            "positive_signals": self.positive_signals,
            "notes": self.notes,
        }
        # Filter out None values to keep YAML clean
        clean_data = {k: v for k, v in data.items() if v is not None}
        location_legal = clean_data.get("location_legal")
        if isinstance(location_legal, dict):
            clean_data["location_legal"] = {
                k: v for k, v in location_legal.items() if v is not None
            }

        timezone = clean_data.get("timezone")
        if isinstance(timezone, dict):
            clean_data["timezone"] = {k: v for k, v in timezone.items() if v is not None}

        return yaml.dump(clean_data, sort_keys=False, allow_unicode=True)

    def __repr__(self) -> str:
        return f"<CandidateProfile(name={self.name}, is_active={self.is_active})>"


class JobProfileScore(Base):
    """
    SQLAlchemy model for the 'job_profile_scores' table.
    Stores the fit score and tier of a job for a specific candidate profile.
    """

    __tablename__ = "job_profile_scores"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidate_profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    fit_score: Mapped[int | None] = mapped_column(Integer)
    tier: Mapped[JobTier | None] = mapped_column(String(10))
    score_data: Mapped[dict[str, Any] | None] = mapped_column(
        MutableDict.as_mutable(JSONB().with_variant(JSON(), "sqlite"))
    )

    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    scored_with_prompt_version: Mapped[str | None] = mapped_column(String(20))

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="profile_scores")
    profile: Mapped["CandidateProfile"] = relationship()

    # Indices
    __table_args__ = (
        Index("idx_job_profile_scores_job_id", "job_id"),
        Index("idx_job_profile_scores_profile_id", "profile_id"),
        Index("idx_job_profile_scores_tier", "tier"),
    )

    def __repr__(self) -> str:
        return f"<JobProfileScore(job_id={self.job_id}, profile_id={self.profile_id}, tier={self.tier})>"


class CandidateProfileHistory(Base):
    """
    SQLAlchemy model for the 'candidate_profile_history' table.
    Stores snapshots of candidate profiles before updates.
    """

    __tablename__ = "candidate_profile_history"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    changed_by: Mapped[str | None] = mapped_column(String(100))
    change_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    profile: Mapped["CandidateProfile"] = relationship(back_populates="history")

    # Indices
    __table_args__ = (
        Index("idx_profile_history_profile_id_changed_at", profile_id, changed_at.desc()),
    )

    def __repr__(self) -> str:
        return (
            f"<CandidateProfileHistory(profile_id={self.profile_id}, changed_at={self.changed_at})>"
        )


class CVVariant(Base):
    """
    SQLAlchemy model for the 'cv_variants' table.
    Represents a specific variant of a candidate's CV.
    """

    __tablename__ = "cv_variants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("candidate_profiles.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))

    target_role_keywords: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    target_stack: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    target_seniority: Mapped[str | None] = mapped_column(String(50))
    summary: Mapped[str | None] = mapped_column(Text)
    skills: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    raw_markdown: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<RecommendationState(reco_hash={self.reco_hash}, status={self.status})>"

    # Relationships
    profile: Mapped["CandidateProfile"] = relationship(back_populates="cv_variants")
    experiences: Mapped[list["CVVariantExperience"]] = relationship(
        back_populates="cv_variant",
        cascade="all, delete-orphan",
        order_by="CVVariantExperience.sort_order",
    )

    # Indices and Constraints
    __table_args__ = (
        Index("idx_cv_variants_profile_id", profile_id),
        CheckConstraint("profile_id IS NOT NULL", name="check_cv_variant_profile_id"),
    )

    def __repr__(self) -> str:
        return f"<CVVariant(name={self.name}, profile_id={self.profile_id})>"


class CVVariantExperience(Base):
    """
    SQLAlchemy model for the 'cv_variant_experiences' table.
    Represents professional experiences within a CV variant.
    """

    __tablename__ = "cv_variant_experiences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    cv_variant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cv_variants.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str | None] = mapped_column(String(200))
    company: Mapped[str | None] = mapped_column(String(200))
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    bullets: Mapped[list[str] | None] = mapped_column(
        MutableList.as_mutable(ARRAY(Text).with_variant(JSON(), "sqlite"))
    )
    sort_order: Mapped[int | None] = mapped_column(Integer)

    # Relationships
    cv_variant: Mapped["CVVariant"] = relationship(back_populates="experiences")

    # Indices
    __table_args__ = (Index("idx_cv_exp_variant_sort", cv_variant_id, sort_order),)

    def __repr__(self) -> str:
        return f"<CVVariantExperience(role={self.role}, company={self.company})>"


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
