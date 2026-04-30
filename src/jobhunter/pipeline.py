"""
Orchestrator for the jobhunter pipeline run-cycle.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.notify.dispatcher import DispatchReport, dispatch_tier_a_notifications
from jobhunter.scoring.pipeline import ScoringBatchReport, score_pending_jobs
from jobhunter.scoring.scorer import JobScorer
from jobhunter.sources.orchestrator import IngestionReport, run_ingestion
from jobhunter.sources.registry import get_all_sources

logger = structlog.get_logger(__name__)


class RunCycleStatus(str, Enum):
    """Overall status of the pipeline run cycle."""

    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    TOTAL_FAILURE = "total_failure"


class RunCycleReport(BaseModel):
    """Consolidated report for a pipeline run cycle."""

    started_at: datetime
    finished_at: Optional[datetime] = None
    total_duration_ms: int = 0
    overall_status: RunCycleStatus
    ingestion: Optional[IngestionReport] = None
    scoring: Optional[ScoringBatchReport] = None
    dispatch: Optional[DispatchReport] = None
    errors: List[str] = Field(default_factory=list)


async def run_cycle(
    session: Session,
    skip_steps: Optional[List[str]] = None,
    since: Optional[datetime] = None,
    scoring_limit: int = 100,
    scoring_concurrency: int = 5,
    ingest_limit: Optional[int] = None,
    ingest_sources: Optional[List[str]] = None,
) -> RunCycleReport:
    """
    Executes the full pipeline cycle: ingest -> score -> dispatch.

    Args:
        session: SQLAlchemy session.
        skip_steps: List of steps to skip (ingest, score, notify).
        since: Datetime for ingestion (defaults to 7 days ago).
        scoring_limit: Max jobs to score.
        scoring_concurrency: Max concurrent LLM calls.
        ingest_limit: Optional maximum number of jobs to fetch per source.
        ingest_sources: Optional list of source names to include.

    Returns:
        RunCycleReport: Consolidated report of all steps.
    """
    started_at = datetime.now(timezone.utc)
    report = RunCycleReport(started_at=started_at, overall_status=RunCycleStatus.SUCCESS)
    skip_steps = skip_steps or []

    # 1. Ingestion
    if "ingest" not in skip_steps:
        logger.info("pipeline_cycle_step_start", step="ingest")
        if since is None:
            since = datetime.now(timezone.utc) - timedelta(days=7)

        try:
            all_source_classes = get_all_sources()
            if ingest_sources:
                source_map = {cls.__name__.lower(): cls for cls in all_source_classes}
                selected_classes = []
                for s in ingest_sources:
                    cls = source_map.get(s.lower())
                    if cls:
                        selected_classes.append(cls)
                    else:
                        logger.warning("pipeline_cycle_source_not_found", source=s)
                sources = [cls() for cls in selected_classes]
            else:
                sources = [cls() for cls in all_source_classes]

            ingestion_report = await run_ingestion(
                sources=sources,
                since=since,
                session=session,
                limit=ingest_limit,
            )
            report.ingestion = ingestion_report
            if ingestion_report.total_errors > 0:
                report.overall_status = RunCycleStatus.PARTIAL_FAILURE
                report.errors.append(f"Ingestion had {ingestion_report.total_errors} errors")
        except Exception as e:
            logger.exception("pipeline_cycle_step_failed", step="ingest", error=str(e))
            report.overall_status = RunCycleStatus.PARTIAL_FAILURE
            report.errors.append(f"Ingestion failed: {str(e)}")
            # If it's a DB error, we might want to flag it as total failure later,
            # but per spec: "If a step fails, the following are executed anyway (except if DB-related)".
            # Determining if an exception is "DB-related" can be tricky, but usually SQLAlchemy errors.
            if "sqlalchemy" in str(type(e)).lower() or "psycopg" in str(type(e)).lower():
                report.overall_status = RunCycleStatus.TOTAL_FAILURE
                report.finished_at = datetime.now(timezone.utc)
                report.total_duration_ms = int(
                    (report.finished_at - report.started_at).total_seconds() * 1000
                )
                return report

    # 2. Scoring
    if "score" not in skip_steps:
        logger.info("pipeline_cycle_step_start", step="score")
        try:
            settings = Settings()  # type: ignore[call-arg]
            llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
            scorer = JobScorer(llm_client=llm_client)

            scoring_report = await score_pending_jobs(
                session=session,
                scorer=scorer,
                limit=scoring_limit,
                concurrency=scoring_concurrency,
            )
            report.scoring = scoring_report
            if scoring_report.failed_count > 0:
                if report.overall_status != RunCycleStatus.TOTAL_FAILURE:
                    report.overall_status = RunCycleStatus.PARTIAL_FAILURE
                report.errors.append(f"Scoring had {scoring_report.failed_count} failures")
        except Exception as e:
            logger.exception("pipeline_cycle_step_failed", step="score", error=str(e))
            report.overall_status = RunCycleStatus.PARTIAL_FAILURE
            report.errors.append(f"Scoring failed: {str(e)}")
            if "sqlalchemy" in str(type(e)).lower() or "psycopg" in str(type(e)).lower():
                report.overall_status = RunCycleStatus.TOTAL_FAILURE
                report.finished_at = datetime.now(timezone.utc)
                report.total_duration_ms = int(
                    (report.finished_at - report.started_at).total_seconds() * 1000
                )
                return report

    # 3. Notification Dispatch
    if "notify" not in skip_steps:
        logger.info("pipeline_cycle_step_start", step="notify")
        try:
            dispatch_report = await dispatch_tier_a_notifications(session=session)
            report.dispatch = dispatch_report
            if dispatch_report.failure_count > 0:
                if report.overall_status != RunCycleStatus.TOTAL_FAILURE:
                    report.overall_status = RunCycleStatus.PARTIAL_FAILURE
                report.errors.append(f"Dispatch had {dispatch_report.failure_count} failures")
        except Exception as e:
            logger.exception("pipeline_cycle_step_failed", step="notify", error=str(e))
            report.overall_status = RunCycleStatus.PARTIAL_FAILURE
            report.errors.append(f"Dispatch failed: {str(e)}")
            if "sqlalchemy" in str(type(e)).lower() or "psycopg" in str(type(e)).lower():
                report.overall_status = RunCycleStatus.TOTAL_FAILURE
                report.finished_at = datetime.now(timezone.utc)
                report.total_duration_ms = int(
                    (report.finished_at - report.started_at).total_seconds() * 1000
                )
                return report

    report.finished_at = datetime.now(timezone.utc)
    report.total_duration_ms = int((report.finished_at - report.started_at).total_seconds() * 1000)

    return report
