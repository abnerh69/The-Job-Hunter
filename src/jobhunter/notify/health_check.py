"""
Service for running system health checks and sending alerts.
"""

import unicodedata
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.enums import SourceState
from jobhunter.db.models import NotificationSent, SourceHealth
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.notify.base import NotificationMessage
from jobhunter.notify.telegram import TelegramNotifier

logger = structlog.get_logger(__name__)


async def run_health_checks(session: Session) -> list[str]:
    """
    Runs various health checks and returns a list of alert messages.

    Args:
        session: SQLAlchemy session.

    Returns:
        list[str]: A list of alert messages for any failed health checks.
    """
    alerts = []
    settings = Settings()  # type: ignore[call-arg]

    # 1. Pipeline Heartbeat (> 16h)
    stmt_pipeline = (
        select(NotificationSent.sent_at)
        .where(
            NotificationSent.channel == "heartbeat",
            NotificationSent.dedup_key == "pipeline-cycle",
            NotificationSent.success.is_(True),
        )
        .order_by(NotificationSent.sent_at.desc())
        .limit(1)
    )
    last_pipeline: datetime | None = session.scalar(stmt_pipeline)
    if not last_pipeline or last_pipeline < datetime.now(timezone.utc) - timedelta(hours=16):
        time_str = last_pipeline.strftime("%Y-%m-%d %H:%M") if last_pipeline else "NEVER"
        alerts.append(f"Última corrida exitosa de pipeline-cycle: {time_str} (alerta si > 16h)")

    # 2. Followup Heartbeat (> 36h)
    stmt_followup = (
        select(NotificationSent.sent_at)
        .where(
            NotificationSent.channel == "heartbeat",
            NotificationSent.dedup_key == "followup-checks",
            NotificationSent.success.is_(True),
        )
        .order_by(NotificationSent.sent_at.desc())
        .limit(1)
    )
    last_followup: datetime | None = session.scalar(stmt_followup)
    if not last_followup or last_followup < datetime.now(timezone.utc) - timedelta(hours=36):
        time_str = last_followup.strftime("%Y-%m-%d %H:%M") if last_followup else "NEVER"
        alerts.append(f"Última corrida exitosa de followup-checks: {time_str} (alerta si > 36h)")

    # 3. Circuit Breakers (2+ open)
    stmt_breakers = select(SourceHealth).where(SourceHealth.state == SourceState.OPEN)
    open_sources = list(session.scalars(stmt_breakers).all())
    if len(open_sources) >= 2:
        source_names = ", ".join([s.source_name for s in open_sources])
        alerts.append(
            f"Estado de circuit breakers: {len(open_sources)} fuentes abiertas ({source_names})"
        )

    # 4. LLM Cost (> 80% budget)
    llm_repo = LLMCallRepo(session)
    now = datetime.now(timezone.utc)
    monthly_cost = llm_repo.monthly_total_usd(now.year, now.month)
    budget = settings.LLM_MONTHLY_BUDGET_USD
    if monthly_cost > budget * 0.8:
        alerts.append(f"Costo LLM mensual: ${monthly_cost:.2f} / ${budget:.2f} (> 80% budget)")

    return alerts


async def dispatch_health_alerts(session: Session) -> int:
    """
    Runs health checks and dispatches alerts via Telegram with anti-spam logic.

    Args:
        session: SQLAlchemy session.

    Returns:
        int: The number of alerts sent.
    """
    alerts = await run_health_checks(session)
    if not alerts:
        return 0

    settings = Settings()  # type: ignore[call-arg]
    notifier = TelegramNotifier()
    if not notifier.is_enabled(settings):
        logger.warning("health_check_telegram_disabled")
        return 0

    repo = NotificationsRepo(session)
    sent_count = 0
    now = datetime.now(timezone.utc)

    # 6h deduplication block
    hour_block = now.hour // 6
    date_hour = f"{now.strftime('%Y%m%d')}_{hour_block}"

    for alert_text in alerts:
        # Simple alert type extraction from text
        # Ensure only ASCII alphanumeric and underscores for dedup_key
        alert_type = alert_text.split(":")[0].strip().lower()
        # Normalize unicode characters to ASCII (e.g., ú -> u)
        alert_type = (
            unicodedata.normalize("NFKD", alert_type).encode("ascii", "ignore").decode("ascii")
        )
        alert_type = "".join(c if c.isalnum() else "_" for c in alert_type)
        dedup_key = f"health_check:{alert_type}:{date_hour}"

        # We check both success=True AND exists at all to prevent duplicates on failure
        # because the spec says: "Si la misma alerta ya se envió en las últimas 6 horas, no re-enviar."
        # This includes failed attempts that we recorded to track them.
        stmt = (
            select(NotificationSent)
            .where(
                NotificationSent.channel == "telegram",
                NotificationSent.dedup_key == dedup_key,
            )
            .limit(1)
        )
        existing = session.scalar(stmt)

        if not existing:
            message = NotificationMessage(
                channel="telegram",
                body_text=f"🚨 *Health Check Alert*\n\n{alert_text}",
                metadata={"type": "health_check", "alert_type": alert_type},
            )
            result = await notifier.send(message)
            repo.record_sent("telegram", dedup_key, None, result)
            session.commit()
            if result.success:
                sent_count += 1
        else:
            logger.info("health_check_alert_deduplicated", dedup_key=dedup_key)

    return sent_count
