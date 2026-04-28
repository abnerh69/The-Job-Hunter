import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from jobhunter.db.base import Base
from jobhunter.db.enums import JobStatus, JobTier


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

    # Indices
    __table_args__ = (
        Index("idx_jobs_status", "status"),
        Index("idx_jobs_tier", "tier"),
        Index("idx_jobs_scraped_at", scraped_at.desc()),
        Index("idx_jobs_company", "company"),
    )

    def __repr__(self) -> str:
        return f"<Job(title={self.title}, company={self.company}, status={self.status})>"
