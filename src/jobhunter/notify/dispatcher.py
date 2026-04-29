import time
import structlog
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.enums import JobTier
from jobhunter.db.models import Job, NotificationSent
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.notify.telegram import TelegramNotifier
from jobhunter.notify.templates import render
from jobhunter.notify.base import NotificationMessage, NotificationResult

logger = structlog.get_logger(__name__)


class DispatchReport(BaseModel):
    """
    Model representing the result of a notification dispatch process.
    """

    total_pending: int = 0
    success_count: int = 0
    failure_count: int = 0
    errors: list[str] = []
    duration_ms: int = 0


async def dispatch_tier_a_notifications(session: Session) -> DispatchReport:
    """
    Dispatches notifications for Tier-A jobs that haven't been notified via Telegram yet.

    Args:
        session: The SQLAlchemy database session.

    Returns:
        DispatchReport: A report summarizing the dispatch operation.
    """
    start_time = time.perf_counter()
    settings = Settings()  # type: ignore[call-arg]
    notifier = TelegramNotifier()
    repo = NotificationsRepo(session)

    # 1. Identify pending jobs
    # We look for Tier-A jobs that don't have ANY notification recorded
    # (success or failure) for the 'telegram' channel with a Tier-A alert dedup key.
    # This follows the "no-retry" policy to avoid infinite loops.
    # We use a subquery matching on job_id and channel to be robust across different
    # database types where casting UUID to string for dedup_key matching might differ.
    subq = select(NotificationSent.job_id).where(
        NotificationSent.channel == "telegram",
        NotificationSent.dedup_key.like("tier_a:%"),
    )

    stmt = select(Job).where(
        Job.tier == JobTier.A,
        Job.id.notin_(subq),
    )

    pending_jobs = session.scalars(stmt).all()
    total_pending = len(pending_jobs)

    report = DispatchReport(total_pending=total_pending)

    def finish_report() -> DispatchReport:
        report.duration_ms = int((time.perf_counter() - start_time) * 1000)
        return report

    # 2. Check if Telegram is enabled
    if not notifier.is_enabled(settings):
        if total_pending > 0:
            logger.warning(
                "Telegram notifier is disabled, skipping dispatch for Tier-A jobs",
                pending_count=total_pending,
            )
        return finish_report()

    if total_pending == 0:
        return finish_report()

    # 3. Dispatch notifications
    for job in pending_jobs:
        dedup_key = f"tier_a:{job.id}"

        try:
            # Render template
            body = render("notifications/tier_a_match_telegram.md", {"job": job})

            message = NotificationMessage(
                channel="telegram",
                body_text=body,
                metadata={"job_id": str(job.id)},
            )

            # Send notification
            result = await notifier.send(message)

            # Record result in database (even if it failed)
            repo.record_sent(
                channel="telegram",
                dedup_key=dedup_key,
                job_id=job.id,
                result=result,
            )

            if result.success:
                report.success_count += 1
                logger.info(
                    "Tier-A notification sent",
                    job_id=job.id,
                    message_id=result.provider_message_id,
                )
            else:
                report.failure_count += 1
                report.errors.append(f"Job {job.id}: {result.error}")
                logger.error("Tier-A notification failed", job_id=job.id, error=result.error)

            # Commit after each job to ensure idempotency if the process crashes mid-batch
            session.commit()

        except Exception as e:
            error_msg = f"Unexpected error dispatching job {job.id}: {str(e)}"
            logger.exception("Error in Tier-A dispatch loop", job_id=job.id)

            report.failure_count += 1
            report.errors.append(error_msg)

            # Record internal failure to avoid infinite loops as per MVP policy
            repo.record_sent(
                channel="telegram",
                dedup_key=dedup_key,
                job_id=job.id,
                result=NotificationResult(
                    success=False,
                    error=error_msg,
                    duration_ms=0,
                ),
            )
            session.commit()

    logger.info(
        "Tier-A notification dispatch complete",
        total=total_pending,
        success=report.success_count,
        failure=report.failure_count,
    )

    return finish_report()
