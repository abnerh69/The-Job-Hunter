from datetime import datetime, timedelta, timezone
from typing import Dict, List

from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, EmailMatchStatus, JobTier, OutreachMessageStatus
from jobhunter.db.models import (
    Application,
    EmailMessage,
    Job,
    LLMCall,
    NotificationSent,
    OutreachMessage,
)


class MetricValue(BaseModel):
    """Value of a metric for a specific period."""

    name: str
    current_value: float
    baseline_value: float
    change_pct: float
    change_absolute: float
    is_regression: bool = False
    is_anomaly: bool = False


class RegressionReport(BaseModel):
    """Full report of regressions and anomalies."""

    metrics: List[MetricValue]
    inferred_context: Dict[str, List[str]]
    detected_at: datetime = datetime.now(timezone.utc)


def calculate_tier_a_rate(session: Session, start: datetime, end: datetime) -> float:
    """% of jobs ingested that end up as Tier A."""
    total = (
        session.scalar(
            select(func.count(Job.id)).where(and_(Job.scraped_at >= start, Job.scraped_at <= end))
        )
        or 0
    )
    if total == 0:
        return 0.0
    tier_a = (
        session.scalar(
            select(func.count(Job.id)).where(
                and_(Job.scraped_at >= start, Job.scraped_at <= end, Job.tier == JobTier.A)
            )
        )
        or 0
    )
    return (tier_a / total) * 100


def calculate_application_rate(session: Session, start: datetime, end: datetime) -> float:
    """% of Tier A jobs that are applied to."""
    tier_a_jobs = select(Job.id).where(
        and_(Job.scraped_at >= start, Job.scraped_at <= end, Job.tier == JobTier.A)
    )
    total_tier_a = session.scalar(select(func.count()).select_from(tier_a_jobs.subquery())) or 0
    if total_tier_a == 0:
        return 0.0

    applied = (
        session.scalar(
            select(func.count(Application.id))
            .join(Job)
            .where(and_(Job.scraped_at >= start, Job.scraped_at <= end, Job.tier == JobTier.A))
        )
        or 0
    )
    return (applied / total_tier_a) * 100


def calculate_response_rate(session: Session, start: datetime, end: datetime) -> float:
    """% of applications with any response."""
    total_apps = (
        session.scalar(
            select(func.count(Application.id)).where(
                and_(Application.applied_at >= start, Application.applied_at <= end)
            )
        )
        or 0
    )
    if total_apps == 0:
        return 0.0

    responded = (
        session.scalar(
            select(func.count(Application.id)).where(
                and_(
                    Application.applied_at >= start,
                    Application.applied_at <= end,
                    Application.status.notin_(
                        [
                            ApplicationStatus.APPLIED,
                            ApplicationStatus.GHOSTED,
                            ApplicationStatus.WITHDRAWN,
                        ]
                    ),
                )
            )
        )
        or 0
    )
    return (responded / total_apps) * 100


def calculate_outreach_response_rate(session: Session, start: datetime, end: datetime) -> float:
    """% of outreach messages with a reply."""
    total_sent = (
        session.scalar(
            select(func.count(OutreachMessage.id)).where(
                and_(
                    OutreachMessage.sent_at >= start,
                    OutreachMessage.sent_at <= end,
                    OutreachMessage.status != OutreachMessageStatus.DRAFT,
                )
            )
        )
        or 0
    )
    if total_sent == 0:
        return 0.0

    replied = (
        session.scalar(
            select(func.count(OutreachMessage.id)).where(
                and_(
                    OutreachMessage.sent_at >= start,
                    OutreachMessage.sent_at <= end,
                    OutreachMessage.status == OutreachMessageStatus.REPLIED,
                )
            )
        )
        or 0
    )
    return (replied / total_sent) * 100


def calculate_email_matcher_precision(session: Session, start: datetime, end: datetime) -> float:
    """Proportion of automated matches that were correct."""
    # Matches that were either AUTO/AI matched (and not rejected) or confirmed
    stmt = (
        select(EmailMessage.match_status, func.count(EmailMessage.id))
        .where(and_(EmailMessage.processed_at >= start, EmailMessage.processed_at <= end))
        .group_by(EmailMessage.match_status)
    )

    rows = session.execute(stmt).all()
    counts = {row[0]: row[1] for row in rows}

    auto: int = counts.get(EmailMatchStatus.AUTO_MATCHED, 0)
    ai: int = counts.get(EmailMatchStatus.AI_MATCHED, 0)
    confirmed: int = counts.get(EmailMatchStatus.USER_CONFIRMED, 0)
    rejected: int = counts.get(EmailMatchStatus.USER_REJECTED, 0)

    total_automated = auto + ai + confirmed + rejected
    if total_automated == 0:
        return 0.0

    return float((auto + ai + confirmed) / total_automated * 100)


def calculate_pipeline_success_rate(session: Session, start: datetime, end: datetime) -> float:
    """% of successful pipeline cycles."""
    # Use heartbeats from NotificationSent
    total_attempts = (
        session.scalar(
            select(func.count(NotificationSent.id)).where(
                and_(
                    NotificationSent.sent_at >= start,
                    NotificationSent.sent_at <= end,
                    NotificationSent.dedup_key.like("pipeline-cycle%"),
                    NotificationSent.channel == "heartbeat",
                )
            )
        )
        or 0
    )

    if total_attempts == 0:
        # Fallback to LLM success rate if no heartbeats found
        total_llm = (
            session.scalar(
                select(func.count(LLMCall.id)).where(
                    and_(LLMCall.called_at >= start, LLMCall.called_at <= end)
                )
            )
            or 0
        )
        if total_llm == 0:
            return 100.0  # No activity is not a failure

        success_llm: int = (
            session.scalar(
                select(func.count(LLMCall.id)).where(
                    and_(LLMCall.called_at >= start, LLMCall.called_at <= end, LLMCall.success)
                )
            )
            or 0
        )
        return float((success_llm / total_llm) * 100)

    success_attempts: int = (
        session.scalar(
            select(func.count(NotificationSent.id)).where(
                and_(
                    NotificationSent.sent_at >= start,
                    NotificationSent.sent_at <= end,
                    NotificationSent.dedup_key.like("pipeline-cycle%"),
                    NotificationSent.channel == "heartbeat",
                    NotificationSent.success,
                )
            )
        )
        or 0
    )

    return float((success_attempts / total_attempts) * 100)


def get_inferred_context(session: Session, start: datetime) -> Dict[str, List[str]]:
    """Infers context by looking at recent prompt versions and models used."""
    context = {}

    # Prompt versions used in last 7 days
    prompts_stmt = select(LLMCall.prompt_version).where(LLMCall.called_at >= start).distinct()
    context["prompt_versions"] = [p for p in session.scalars(prompts_stmt).all() if p]

    # Models used
    models_stmt = select(LLMCall.model).where(LLMCall.called_at >= start).distinct()
    context["models"] = [m for m in session.scalars(models_stmt).all() if m]

    return context


def check_metrics(session: Session) -> RegressionReport:
    """Calculates all metrics and identifies regressions/anomalies."""
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=7)
    baseline_end = current_start
    baseline_start = baseline_end - timedelta(days=28)

    # Debug: log the periods
    # print(f"Checking metrics: current={current_start} to {now}, baseline={baseline_start} to {baseline_end}")

    metrics_to_check = [
        ("Tier A Rate", calculate_tier_a_rate),
        ("Application Rate", calculate_application_rate),
        ("Response Rate", calculate_response_rate),
        ("Outreach Response Rate", calculate_outreach_response_rate),
        ("Email Matcher Precision", calculate_email_matcher_precision),
        ("Pipeline Success Rate", calculate_pipeline_success_rate),
    ]

    results = []
    for name, func_calc in metrics_to_check:
        current = func_calc(session, current_start, now)
        baseline = func_calc(session, baseline_start, baseline_end)

        change_abs = current - baseline
        change_rel = (change_abs / baseline * 100) if baseline > 0 else 0.0

        # Regression: drop > 30% relative OR drop > 5pp absolute
        # We take the greater drop.
        # A drop means change_abs is negative.
        is_regression = False
        if baseline > 0:
            if change_rel <= -30 or change_abs <= -5:
                is_regression = True

        # Anomaly: upward spike > 50% relative
        is_anomaly = False
        if baseline > 0 and change_rel >= 50:
            is_anomaly = True
        elif baseline == 0 and current > 0:
            is_anomaly = True  # Suddent activity after nothing

        results.append(
            MetricValue(
                name=name,
                current_value=current,
                baseline_value=baseline,
                change_pct=change_rel,
                change_absolute=change_abs,
                is_regression=is_regression,
                is_anomaly=is_anomaly,
            )
        )

    return RegressionReport(
        metrics=results, inferred_context=get_inferred_context(session, current_start)
    )
