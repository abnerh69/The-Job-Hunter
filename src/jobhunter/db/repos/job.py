import uuid
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy import and_, cast, func, or_, select, Text as SAText
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

    def list_new_matches(
        self,
        tiers: list[JobTier] | None = None,
        sources: list[str] | None = None,
        min_score: int | None = None,
        stacks: list[str] | None = None,
        min_salary: int | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Job]:
        """
        Lists jobs with status 'queued' and applies filters.

        Args:
            tiers (list[JobTier] | None): The tiers to filter by.
            sources (list[str] | None): The sources to filter by.
            min_score (int | None): The minimum fit score.
            stacks (list[str] | None): The tech stacks to filter by.
            min_salary (int | None): The minimum salary in USD/month.
            limit (int): Maximum number of records to return. Defaults to 20.
            offset (int): Number of records to skip. Defaults to 0.

        Returns:
            Sequence[Job]: A sequence of jobs matching the criteria.
        """
        stmt = select(Job).where(Job.status == JobStatus.QUEUED)

        if tiers:
            stmt = stmt.where(Job.tier.in_(tiers))

        if sources:
            stmt = stmt.where(Job.source.in_(sources))

        if min_score is not None:
            stmt = stmt.where(Job.fit_score >= min_score)

        is_postgres = self.session.bind.dialect.name == "postgresql"

        if stacks:
            stack_filters = []
            for stack in stacks:
                if stack == "Python":
                    if is_postgres:
                        stack_filters.append(
                            Job.score_data["role"]["primary_stack_match"].contains(["Python"])
                        )
                    else:
                        stack_filters.append(cast(Job.score_data, SAText).like("%Python%"))
                elif stack == "Flutter":
                    if is_postgres:
                        stack_filters.append(Job.score_data["role"]["is_flutter_role"].as_boolean())
                    else:
                        stack_filters.append(cast(Job.score_data, SAText).like('%"is_flutter_role": true%'))
                elif stack == "AI/ML":
                    if is_postgres:
                        stack_filters.append(Job.score_data["role"]["is_ai_ml_role"].as_boolean())
                    else:
                        stack_filters.append(cast(Job.score_data, SAText).like('%"is_ai_ml_role": true%'))
                elif stack == "Backend":
                    if is_postgres:
                        stack_filters.append(
                            Job.score_data["role"]["title_normalized"].as_string().ilike("%backend%")
                        )
                    else:
                        stack_filters.append(cast(Job.score_data, SAText).ilike("%backend%"))

            if stack_filters:
                stmt = stmt.where(or_(*stack_filters))

        if min_salary:
            if is_postgres:
                stmt = stmt.where(
                    Job.score_data["compensation"]["salary_max_usd_month"].as_float() >= min_salary
                )
            else:
                # SQLite doesn't handle JSON numbers well in casted text for comparison
                # We'll skip it for now in SQLite to avoid complex/unreliable SQL
                pass

        stmt = stmt.order_by(Job.fit_score.desc()).limit(limit).offset(offset)
        return self.session.scalars(stmt).all()

    def get_dashboard_metrics(self) -> dict[str, int]:
        """
        Returns metrics for the dashboard.

        Returns:
            dict[str, int]: A dictionary with metrics.
        """
        today = datetime.now(timezone.utc).date()

        jobs_today_stmt = select(func.count(Job.id)).where(func.date(Job.scraped_at) == today)
        pending_a_stmt = select(func.count(Job.id)).where(
            and_(Job.tier == JobTier.A, Job.status == JobStatus.QUEUED)
        )

        return {
            "jobs_today": self.session.scalar(jobs_today_stmt) or 0,
            "pending_a": self.session.scalar(pending_a_stmt) or 0,
        }
