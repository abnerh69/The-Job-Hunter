import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.models import Job
from jobhunter.db.repos.base import BaseRepo


class JobRepo(BaseRepo[Job]):
    """
    Repository for Job model specific operations.
    """

    def __init__(self, session: Session):
        """
        Initializes the JobRepo.

        Args:
            session (Session): The SQLAlchemy session.
        """
        super().__init__(Job, session)

    def find_by_url_hash(self, url_hash: str) -> Job | None:
        """
        Finds a job by its URL hash.

        Args:
            url_hash (str): The SHA256 hash of the canonical URL.

        Returns:
            Job | None: The job if found, None otherwise.
        """
        stmt = select(Job).where(Job.url_hash == url_hash)
        return self.session.scalar(stmt)

    def list_by_status(self, status: JobStatus, limit: int = 100) -> Sequence[Job]:
        """
        Lists jobs by their status.

        Args:
            status (JobStatus): The status to filter by.
            limit (int): Maximum number of records to return. Defaults to 100.

        Returns:
            Sequence[Job]: A sequence of jobs matching the status.
        """
        stmt = select(Job).where(Job.status == status).limit(limit)
        return self.session.scalars(stmt).all()

    def list_by_tier(self, tier: JobTier, limit: int = 100) -> Sequence[Job]:
        """
        Lists jobs by their tier.

        Args:
            tier (JobTier): The tier to filter by.
            limit (int): Maximum number of records to return. Defaults to 100.

        Returns:
            Sequence[Job]: A sequence of jobs matching the tier.
        """
        stmt = select(Job).where(Job.tier == tier).limit(limit)
        return self.session.scalars(stmt).all()

    def mark_status(self, job_id: uuid.UUID, new_status: JobStatus) -> None:
        """
        Updates the status of a job.

        Args:
            job_id (uuid.UUID): The ID of the job to update.
            new_status (JobStatus): The new status to set.
        """
        self.update(job_id, status=new_status)

    def bulk_create_skipping_duplicates(self, jobs: list[Job]) -> list[uuid.UUID]:
        """
        Bulk creates jobs, skipping those with a duplicate url_hash.

        Args:
            jobs (list[Job]): The list of jobs to create.

        Returns:
            list[uuid.UUID]: A list of IDs of the inserted jobs.
        """
        if not jobs:
            return []

        # Prepare values for insertion
        values = []
        for job in jobs:
            # We need to extract all data from the job object
            # Note: id might be None if not pre-assigned, Postgres will generate it
            job_data = {
                "source": job.source,
                "source_id": job.source_id,
                "url": job.url,
                "url_hash": job.url_hash,
                "title": job.title,
                "company": job.company,
                "location_raw": job.location_raw,
                "description": job.description,
                "posted_at": job.posted_at,
                "tier": job.tier,
                "raw_payload": job.raw_payload,
                "status": job.status or JobStatus.NEW,
            }
            if job.id:
                job_data["id"] = job.id  # type: ignore[assignment]
            values.append(job_data)

        # Build ON CONFLICT DO NOTHING statement
        stmt = (
            pg_insert(Job)
            .values(values)
            .on_conflict_do_nothing(index_elements=["url_hash"])
            .returning(Job.id)
        )

        result = self.session.execute(stmt)
        inserted_ids = [row[0] for row in result.all()]
        self.session.flush()
        return inserted_ids
