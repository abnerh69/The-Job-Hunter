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
