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
