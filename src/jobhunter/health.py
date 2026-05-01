"""
Health check service for Job Hunter EU.
"""

import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Literal

import structlog
from pydantic import BaseModel
from sqlalchemy import text, select
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.models import NotificationSent, SourceHealth, OAuthToken, LLMCall
from jobhunter.db.enums import SourceState
from jobhunter.db.repos.llm_calls import LLMCallRepo

logger = structlog.get_logger(__name__)

HealthStatus = Literal["healthy", "degraded", "unhealthy"]


class ComponentStatus(BaseModel):
    status: Literal["ok", "warning", "error"]
    latency_ms: Optional[float] = None
    last_call_at: Optional[str] = None
    message: Optional[str] = None


class SystemMetrics(BaseModel):
    last_pipeline_run_at: str
    active_circuit_breakers: List[str]
    monthly_cost_usd: float
    budget_pct_used: float


class HealthReport(BaseModel):
    status: HealthStatus
    checks: Dict[str, ComponentStatus]
    metrics: SystemMetrics


def get_health_report(session: Session, settings: Settings) -> HealthReport:
    """
    Generates a full health report of the system.
    """
    checks: Dict[str, ComponentStatus] = {}

    # 1. Database Check
    start_time = time.perf_counter()
    db_ok = False
    db_msg = None
    try:
        session.execute(text("SELECT 1")).scalar()
        db_ok = True
    except Exception as e:
        db_msg = str(e)
    latency_db = (time.perf_counter() - start_time) * 1000

    # Check migrations
    migrations_ok = True
    try:
        # Get current head from alembic_version table
        current_rev = session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # We don't easily know the "expected" head without complex alembic calls,
        # but we can check if the table exists and has a value.
        if not current_rev:
            migrations_ok = False
            db_msg = "No migrations found in alembic_version"
    except Exception:
        migrations_ok = False
        db_msg = "Could not check alembic_version"

    checks["db"] = ComponentStatus(
        status="ok" if db_ok and migrations_ok else "error",
        latency_ms=round(latency_db, 2),
        message=db_msg,
    )

    # 2. Anthropic API Check (via DB history)
    last_llm_call = session.execute(
        select(LLMCall).order_by(LLMCall.called_at.desc()).limit(1)
    ).scalar()

    anthropic_status: Literal["ok", "warning", "error"] = "ok"
    if not last_llm_call:
        anthropic_status = "warning"
        anthropic_msg = "No LLM calls recorded yet"
    elif last_llm_call.called_at < datetime.now(timezone.utc) - timedelta(days=1):
        # If no calls in 24h, maybe it's just inactivity, but worth a warning?
        # Actually, maybe only if it's failed.
        anthropic_status = "ok"  # Inactivity is not necessarily an error
        anthropic_msg = "No calls in last 24h"
    else:
        anthropic_msg = None

    checks["anthropic_api"] = ComponentStatus(
        status=anthropic_status,
        last_call_at=str(last_llm_call.called_at.isoformat()) if last_llm_call else None,
        message=anthropic_msg,
    )

    # 3. Telegram Check
    telegram_configured = bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)
    last_telegram_notif = session.execute(
        select(NotificationSent)
        .where(NotificationSent.channel == "telegram")
        .order_by(NotificationSent.sent_at.desc())
        .limit(1)
    ).scalar()

    telegram_status: Literal["ok", "warning", "error"] = "ok"
    if not telegram_configured:
        telegram_status = "error"
        telegram_msg = "Telegram not configured"
    elif last_telegram_notif and not last_telegram_notif.success:
        telegram_status = "warning"
        telegram_msg = f"Last notification failed: {last_telegram_notif.error}"
    else:
        telegram_msg = None

    checks["telegram"] = ComponentStatus(status=telegram_status, message=telegram_msg)

    # 4. Gmail Check
    gmail_tokens = session.execute(select(OAuthToken).filter_by(provider="gmail")).scalars().all()
    gmail_status: Literal["ok", "warning", "error"] = "ok"
    gmail_msg = None

    if not gmail_tokens:
        gmail_status = "warning"
        gmail_msg = "No Gmail accounts authenticated"
    else:
        # Check if any token is expired and doesn't have a refresh token
        # (Though our handler handles refresh, if it's missing it's an error)
        expired_count = 0
        for token in gmail_tokens:
            if (
                token.expires_at
                and token.expires_at < datetime.now(timezone.utc)
                and not token.refresh_token
            ):
                expired_count += 1

        if expired_count > 0:
            gmail_status = "error"
            gmail_msg = f"{expired_count} Gmail accounts have expired tokens and no refresh token"

    checks["gmail"] = ComponentStatus(status=gmail_status, message=gmail_msg)

    # Metrics
    # Last pipeline run
    last_pipeline_heartbeat = session.execute(
        select(NotificationSent)
        .where(
            NotificationSent.channel == "heartbeat", NotificationSent.dedup_key == "pipeline-cycle"
        )
        .order_by(NotificationSent.sent_at.desc())
        .limit(1)
    ).scalar()

    if last_pipeline_heartbeat:
        diff = datetime.now(timezone.utc) - last_pipeline_heartbeat.sent_at
        if diff.total_seconds() < 3600:
            last_run_str = f"{int(diff.total_seconds() // 60)}m ago"
        elif diff.total_seconds() < 86400:
            last_run_str = f"{int(diff.total_seconds() // 3600)}h ago"
        else:
            last_run_str = f"{diff.days}d ago"
    else:
        last_run_str = "never"

    # Circuit breakers
    open_sources = (
        session.execute(select(SourceHealth).where(SourceHealth.state == SourceState.OPEN))
        .scalars()
        .all()
    )
    active_circuit_breakers = [s.source_name for s in open_sources]

    # Costs
    llm_repo = LLMCallRepo(session)
    now = datetime.now(timezone.utc)
    monthly_cost = llm_repo.monthly_total_usd(now.year, now.month)
    budget = settings.LLM_MONTHLY_BUDGET_USD
    budget_pct = (monthly_cost / budget * 100) if budget > 0 else 0

    metrics = SystemMetrics(
        last_pipeline_run_at=last_run_str,
        active_circuit_breakers=active_circuit_breakers,
        monthly_cost_usd=round(monthly_cost, 4),
        budget_pct_used=round(budget_pct, 1),
    )

    # Overall Status
    overall_status: HealthStatus = "healthy"

    # Critical components that make it unhealthy if they fail
    unhealthy_components = ["db"]

    warning_count = sum(1 for c in checks.values() if c.status == "warning")

    is_unhealthy = any(checks[name].status == "error" for name in unhealthy_components)

    if is_unhealthy:
        overall_status = "unhealthy"
    elif warning_count > 0 or len(active_circuit_breakers) > 0:
        overall_status = "degraded"

    return HealthReport(status=overall_status, checks=checks, metrics=metrics)
