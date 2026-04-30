"""
Orchestrator for the jobhunter pipeline run-cycle.
"""

import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.enums import ApplicationStatus
from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.repos.application import ApplicationRepo
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.notify.base import NotificationMessage, NotificationResult
from jobhunter.notify.dispatcher import DispatchReport, dispatch_tier_a_notifications
from jobhunter.notify.telegram import TelegramNotifier
from jobhunter.notify.templates import render
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


class FollowupReport(BaseModel):
    """Consolidated report for follow-up and ghosting checks."""

    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_ms: int = 0
    pending_followups_count: int = 0
    ghosted_marked_count: int = 0
    notification_sent: bool = False
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

    # 4. Heartbeat
    if report.overall_status == RunCycleStatus.SUCCESS:
        try:
            repo = NotificationsRepo(session)
            repo.record_sent(
                channel="heartbeat",
                dedup_key="pipeline-cycle",
                job_id=None,
                result=NotificationResult(success=True, duration_ms=0),
            )
            session.commit()
        except Exception as e:
            logger.error("failed_to_record_pipeline_heartbeat", error=str(e))

    return report


async def run_followup_checks(session: Session) -> FollowupReport:
    """
    Orchestrates daily follow-up and ghosting checks for applications.

    Args:
        session: SQLAlchemy session.

    Returns:
        FollowupReport: Consolidated report of the checks.
    """
    start_time = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    today = started_at.date()
    report = FollowupReport(started_at=started_at)
    repo = ApplicationRepo(session)

    try:
        # 1. Detect pending follow-ups
        pending = repo.list_pending_followups(today)
        report.pending_followups_count = len(pending)

        # 2. Detect and auto-mark ghosted candidates
        ghosted = repo.list_ghosted_candidates(today)
        for app in ghosted:
            repo.transition_status(
                app.id,
                ApplicationStatus.GHOSTED,
                note="Auto-marked as ghosted after 21 days of inactivity.",
            )
            report.ghosted_marked_count += 1

        session.commit()

        # 3. Refresh weekly metrics
        try:
            refresh_weekly_metrics(session)
        except Exception as e:
            logger.error("failed_to_refresh_metrics_during_followup", error=str(e))
            report.errors.append(f"Metrics refresh failed: {str(e)}")

        # 4. Send Telegram notification if there are pending follow-ups
        if report.pending_followups_count > 0:
            try:
                settings = Settings()  # type: ignore[call-arg]
                notifier = TelegramNotifier()
                if notifier.is_enabled(settings):
                    body = render(
                        "notifications/followup_pending.md",
                        {"count": report.pending_followups_count, "applications": pending},
                    )
                    message = NotificationMessage(
                        channel="telegram",
                        body_text=body,
                        metadata={"type": "followup_check"},
                    )
                    result = await notifier.send(message)
                    if result.success:
                        report.notification_sent = True
                    else:
                        report.errors.append(f"Telegram notification failed: {result.error}")
            except Exception as e:
                logger.error("failed_to_send_followup_notification", error=str(e))
                report.errors.append(f"Notification failed: {str(e)}")

        logger.info(
            "followup_checks_completed",
            pending=report.pending_followups_count,
            ghosted=report.ghosted_marked_count,
            notification_sent=report.notification_sent,
        )

    except Exception as e:
        logger.exception("followup_checks_failed", error=str(e))
        report.errors.append(f"Follow-up checks failed: {str(e)}")
        session.rollback()

    report.finished_at = datetime.now(timezone.utc)
    report.duration_ms = int((time.perf_counter() - start_time) * 1000)

    # 5. Heartbeat
    if not report.errors:
        try:
            notif_repo = NotificationsRepo(session)
            notif_repo.record_sent(
                channel="heartbeat",
                dedup_key="followup-checks",
                job_id=None,
                result=NotificationResult(success=True, duration_ms=0),
            )
            session.commit()
        except Exception as e:
            logger.error("failed_to_record_followup_heartbeat", error=str(e))

    return report
