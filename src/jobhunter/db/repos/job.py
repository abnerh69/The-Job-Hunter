import uuid
from typing import Sequence

from datetime import datetime, timezone
from sqlalchemy import select, and_, or_, func, Numeric
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
        return self.session.scalar(stmt)  # type: ignore[no-any-return]

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
        return self.session.scalars(stmt).all()  # type: ignore[no-any-return]

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
        return self.session.scalars(stmt).all()  # type: ignore[no-any-return]

    def list_new_matches(
        self,
        tiers: list[JobTier] | None = None,
        sources: list[str] | None = None,
        min_score: int | None = None,
        min_salary: int | None = None,
        stacks: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[Job]:
        """
        Lists jobs with status='queued' with complex filtering.

        Args:
            tiers: List of tiers to include.
            sources: List of sources to include.
            min_score: Minimum fit score.
            min_salary: Minimum monthly salary in USD.
            stacks: List of stacks to filter by (Python, Flutter, AI/ML, Backend).
            limit: Maximum number of records to return.
            offset: Number of records to skip.

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

        if min_salary is not None:
            # Salary is in score_data['compensation']['salary_min_usd_month']
            salary_path = ["compensation", "salary_min_usd_month"]
            if self.session.bind and self.session.bind.dialect.name == "sqlite":
                # SQLite doesn't support as_numeric or astext.cast(Numeric) well via SA's JSON
                # We use a more basic approach for SQLite if needed, or just skip filtering for tests
                # Actually, SA 2.0 has some support. Let's try to be cross-dialect.
                stmt = stmt.where(Job.score_data[salary_path].as_integer() >= min_salary)
            else:
                stmt = stmt.where(Job.score_data[salary_path].astext.cast(Numeric) >= min_salary)

        if stacks:
            stack_filters = []
            for stack in stacks:
                if stack == "AI/ML":
                    stack_filters.append(Job.score_data["role"]["is_ai_ml_role"].as_boolean())
                elif stack == "Flutter":
                    stack_filters.append(Job.score_data["role"]["is_flutter_role"].as_boolean())
                elif stack == "Python":
                    # Check if "Python" is in primary_stack_match list
                    if self.session.bind and self.session.bind.dialect.name == "sqlite":
                        # SQLite doesn't support .contains() for JSON arrays easily in SA without extra setup
                        # We use cast(Text) to avoid #>> operator which SQLite dialect might try to use
                        from sqlalchemy import Text as SAText

                        stack_filters.append(
                            Job.score_data["role"]["primary_stack_match"]
                            .cast(SAText)
                            .ilike('%"Python"%')
                        )
                    else:
                        stack_filters.append(
                            Job.score_data["role"]["primary_stack_match"].contains(["Python"])
                        )
                elif stack == "Backend":
                    # Heuristic for backend: title contains "Backend" or "Full Stack"
                    stack_filters.append(
                        or_(
                            Job.title.ilike("%Backend%"),
                            Job.score_data["role"]["is_full_stack"].as_boolean(),
                        )
                    )
            if stack_filters:
                stmt = stmt.where(or_(*stack_filters))

        stmt = stmt.order_by(Job.fit_score.desc()).limit(limit).offset(offset)
        return self.session.scalars(stmt).all()  # type: ignore[no-any-return]

    def count_new_matches(
        self,
        tiers: list[JobTier] | None = None,
        sources: list[str] | None = None,
        min_score: int | None = None,
        min_salary: int | None = None,
        stacks: list[str] | None = None,
    ) -> int:
        """Counts the total number of jobs matching the criteria (for pagination)."""
        stmt = select(func.count()).select_from(Job).where(Job.status == JobStatus.QUEUED)

        if tiers:
            stmt = stmt.where(Job.tier.in_(tiers))
        if sources:
            stmt = stmt.where(Job.source.in_(sources))
        if min_score is not None:
            stmt = stmt.where(Job.fit_score >= min_score)
        if min_salary is not None:
            salary_path = ["compensation", "salary_min_usd_month"]
            if self.session.bind and self.session.bind.dialect.name == "sqlite":
                stmt = stmt.where(Job.score_data[salary_path].as_integer() >= min_salary)
            else:
                stmt = stmt.where(Job.score_data[salary_path].astext.cast(Numeric) >= min_salary)
        if stacks:
            stack_filters = []
            for stack in stacks:
                if stack == "AI/ML":
                    stack_filters.append(Job.score_data["role"]["is_ai_ml_role"].as_boolean())
                elif stack == "Flutter":
                    stack_filters.append(Job.score_data["role"]["is_flutter_role"].as_boolean())
                elif stack == "Python":
                    if self.session.bind and self.session.bind.dialect.name == "sqlite":
                        from sqlalchemy import Text as SAText

                        stack_filters.append(
                            Job.score_data["role"]["primary_stack_match"]
                            .cast(SAText)
                            .ilike('%"Python"%')
                        )
                    else:
                        stack_filters.append(
                            Job.score_data["role"]["primary_stack_match"].contains(["Python"])
                        )
                elif stack == "Backend":
                    stack_filters.append(
                        or_(
                            Job.title.ilike("%Backend%"),
                            Job.score_data["role"]["is_full_stack"].as_boolean(),
                        )
                    )
            if stack_filters:
                stmt = stmt.where(or_(*stack_filters))

        return self.session.scalar(stmt) or 0

    def get_dashboard_metrics(self) -> dict[str, int]:
        """
        Calculates metrics for the dashboard:
        - new_today: jobs scraped today.
        - pending_a: jobs with tier A and status 'queued'.
        """
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        new_today_stmt = select(func.count()).select_from(Job).where(Job.scraped_at >= today_start)
        pending_a_stmt = (
            select(func.count())
            .select_from(Job)
            .where(and_(Job.tier == JobTier.A, Job.status == JobStatus.QUEUED))
        )

        return {
            "new_today": self.session.scalar(new_today_stmt) or 0,
            "pending_a": self.session.scalar(pending_a_stmt) or 0,
        }

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
                job_data["id"] = job.id
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
