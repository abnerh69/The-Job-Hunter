from enum import StrEnum


class JobStatus(StrEnum):
    """Enumeration of possible statuses for a job."""

    NEW = "new"
    SCORED = "scored"
    QUEUED = "queued"
    APPLIED = "applied"
    MANUAL_REVIEW = "manual_review"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class JobTier(StrEnum):
    """Enumeration of possible tiers for a job based on fit score."""

    A = "A"
    B = "B"
    C = "C"
    REJECT = "REJECT"


class ApplicationStatus(StrEnum):
    """Enumeration of possible statuses for an application."""

    APPLIED = "applied"
    SCREENING = "screening"
    INTERVIEW_1 = "interview_1"
    INTERVIEW_N = "interview_n"
    OFFER = "offer"
    REJECTED = "rejected"
    GHOSTED = "ghosted"
    WITHDRAWN = "withdrawn"


class ApplicationEventType(StrEnum):
    """Enumeration of possible event types for an application event."""

    STATUS_CHANGE = "status_change"
    FOLLOW_UP_SENT = "follow_up_sent"
    INTERVIEW_SCHEDULED = "interview_scheduled"


class OutreachMarket(StrEnum):
    """Enumeration of possible markets for outreach."""

    GERMANY = "germany"
    EU_WIDE = "eu_wide"
    UK = "uk"
    NETHERLANDS = "netherlands"
    OTHER = "other"


class OutreachStatus(StrEnum):
    """Enumeration of possible statuses for an outreach contact."""

    NEW = "new"
    CONTACTED = "contacted"
    REPLIED = "replied"
    GHOSTED = "ghosted"
    WARM = "warm"


class OutreachTemplateType(StrEnum):
    """Enumeration of possible outreach template types."""

    A_INHOUSE = "A_inhouse"
    B_BOUTIQUE = "B_boutique"
    C_SENIOR = "C_senior"
    D_FOLLOWUP = "D_followup"
    CUSTOM = "custom"


class OutreachMessageStatus(StrEnum):
    """Enumeration of possible statuses for an outreach message."""

    DRAFT = "draft"
    SENT = "sent"
    REPLIED = "replied"
    GHOSTED = "ghosted"
    DISCARDED = "discarded"


class SourceState(StrEnum):
    """Enumeration of possible states for a circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LLMPurpose(StrEnum):
    """Enumeration of possible purposes for an LLM call."""

    SCORING = "scoring"
    COVER_LETTER = "cover_letter"
    OUTREACH = "outreach"
    OUTREACH_MESSAGE = "outreach_message"
    ATS_KEYWORDS = "ats_keywords"
    CV_TWEAKS = "cv_tweaks"
    EMAIL_MATCH = "email_match"
    ANALYTICS_REPORT = "analytics_report"
    RESUME_PARSING = "resume_parsing"
    PROFILE_GENERATION = "profile_generation"


class EmailMatchStatus(StrEnum):
    """Enumeration of possible match statuses for an email message."""

    UNMATCHED = "unmatched"
    AUTO_MATCHED = "auto_matched"
    AI_MATCHED = "ai_matched"
    USER_CONFIRMED = "user_confirmed"
    USER_REJECTED = "user_rejected"
    IGNORED_MARKETING = "ignored_marketing"


class ABTestStatus(StrEnum):
    """Enumeration of possible statuses for an A/B test."""

    ACTIVE = "active"
    CONCLUDED = "concluded"
    ABORTED = "aborted"


class AuditEventType(StrEnum):
    """Enumeration of possible event types for an audit log."""

    LOGIN = "login"
    LOGOUT = "logout"
    DATA_ACCESS = "data_access"
    DATA_MUTATION = "data_mutation"
    CONFIG_CHANGE = "config_change"
    SECRET_ROTATED = "secret_rotated"
    BACKUP_CREATED = "backup_created"
    RESTORE_EXECUTED = "restore_executed"
    BULK_DELETE = "bulk_delete"
