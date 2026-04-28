import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Sequence

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.db.models import Job
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.source_health import SourceHealthRepo
from jobhunter.sources.base import BaseSource, RawJob
from jobhunter.sources.circuit_breaker import CircuitBreaker
from jobhunter.sources.url_utils import compute_url_hash

logger = logging.getLogger(__name__)


class SourceResult(BaseModel):
    """
    Result of an ingestion from a single source.
    """

    source_name: str
    status: str  # "success", "failed", "skipped_breaker"
    new_jobs: int = 0
    duplicates: int = 0
    error: str | None = None
    duration_ms: int = 0


class IngestionReport(BaseModel):
    """
    Aggregated report of an ingestion run.
    """

    source_results: list[SourceResult] = Field(default_factory=list)
    total_new: int = 0
    total_duplicates: int = 0
    total_errors: int = 0
    started_at: datetime
    finished_at: datetime | None = None


async def run_ingestion(
    sources: Sequence[BaseSource],
    since: datetime,
    session: Session,
    dry_run: bool = False,
    limit: int | None = None,
) -> IngestionReport:
    """
    Orchestrates the ingestion of jobs from multiple sources in parallel.

    Args:
        sources: A sequence of job source instances.
        since: The datetime from which to fetch jobs.
        session: The SQLAlchemy session for persistence.
        dry_run: If True, jobs are fetched but not saved to the database.
        limit: Optional maximum number of jobs to fetch per source.

    Returns:
        IngestionReport: A report containing details and metrics of the ingestion run.
    """
    started_at = datetime.now(timezone.utc)
    report = IngestionReport(started_at=started_at)

    health_repo = SourceHealthRepo(session)
    breaker = CircuitBreaker(health_repo)
    job_repo = JobRepo(session)

    tasks = []
    for source in sources:
        source_name = source.__class__.__name__
        if dry_run or breaker.allow_request(source_name):
            tasks.append(_ingest_from_source(source, since, job_repo, breaker, dry_run, limit))
        else:
            logger.info("Source %s: skipped by circuit breaker", source_name)
            report.source_results.append(
                SourceResult(source_name=source_name, status="skipped_breaker")
            )

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, SourceResult):
                report.source_results.append(result)
                report.total_new += result.new_jobs
                report.total_duplicates += result.duplicates
                if result.status == "failed":
                    report.total_errors += 1
            elif isinstance(result, Exception):
                # This should ideally not happen as _ingest_from_source catches exceptions
                logger.exception("Unexpected exception in ingestion task: %s", result)
                report.total_errors += 1

    report.finished_at = datetime.now(timezone.utc)

    # Log summary
    duration = (report.finished_at - report.started_at).total_seconds()
    logger.info(
        "Ingestion completed in %.2fs. New: %d, Duplicates: %d, Errors: %d",
        duration,
        report.total_new,
        report.total_duplicates,
        report.total_errors,
    )

    return report


async def _ingest_from_source(
    source: BaseSource,
    since: datetime,
    job_repo: JobRepo,
    breaker: CircuitBreaker,
    dry_run: bool = False,
    limit: int | None = None,
) -> SourceResult:
    """
    Ingests jobs from a single source, handles errors and persistence.
    """
    source_name = source.__class__.__name__
    start_time = time.perf_counter()
    raw_jobs: list[RawJob] = []

    try:
        async for job in source.fetch(since):
            raw_jobs.append(job)
            if limit is not None and len(raw_jobs) >= limit:
                break

        # Convert RawJobs to Job models
        job_models = [
            Job(
                source=job.source_name,
                source_id=job.source_id,
                url=job.url,
                url_hash=compute_url_hash(job.url),
                title=job.title,
                company=job.company,
                location_raw=job.location_raw,
                description=job.description,
                posted_at=job.posted_at,
                raw_payload=job.raw_payload,
            )
            for job in raw_jobs
        ]

        if dry_run:
            new_jobs_count = len(job_models)
            duplicates_count = 0
            logger.info("Source %s: dry run, skipping persistence", source_name)
        else:
            inserted_ids = job_repo.bulk_create_skipping_duplicates(job_models)
            new_jobs_count = len(inserted_ids)
            duplicates_count = len(job_models) - new_jobs_count
            breaker.record_success(source_name)

        return SourceResult(
            source_name=source_name,
            status="success",
            new_jobs=new_jobs_count,
            duplicates=duplicates_count,
            duration_ms=int((time.perf_counter() - start_time) * 1000),
        )

    except Exception as e:
        logger.exception("Error ingesting from source %s: %s", source_name, e)
        if not dry_run:
            breaker.record_failure(source_name)
        return SourceResult(
            source_name=source_name,
            status="failed",
            error=str(e),
            duration_ms=int((time.perf_counter() - start_time) * 1000),
        )
