from enum import StrEnum
from typing import List
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import and_, func, select, case
from sqlalchemy.orm import Session

from jobhunter.db.enums import (
    JobStatus,
    JobTier,
    OutreachMessageStatus,
    SourceState,
    EmailMatchStatus,
)
from jobhunter.db.models import (
    Job,
    LLMCall,
    OutreachMessage,
    SourceHealth,
    EmailMessage,
)
from jobhunter.config import Settings


class Effort(StrEnum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Priority(StrEnum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Recommendation(BaseModel):
    """
    Represents a specific, actionable recommendation to improve recruitment performance.
    """

    action: str
    reason: str
    impact: str
    effort: Effort
    priority: Priority


def _check_template_zero_response(session: Session) -> List[Recommendation]:
    """
    Tasa de respuesta de un template = 0% en últimas 4 semanas con ≥10 sends → recomienda pausar.
    """
    four_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=4)

    stmt = (
        select(
            OutreachMessage.template_type,
            func.count(OutreachMessage.id).label("total_sent"),
            func.sum(
                case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
            ).label("replies"),
        )
        .where(
            and_(
                OutreachMessage.sent_at >= four_weeks_ago,
                OutreachMessage.status != OutreachMessageStatus.DRAFT,
            )
        )
        .group_by(OutreachMessage.template_type)
    )

    rows = session.execute(stmt).all()
    recommendations = []

    for row in rows:
        total_sent = row.total_sent
        replies = row.replies or 0
        if total_sent >= 10 and replies == 0:
            recommendations.append(
                Recommendation(
                    action=f"Pausar template '{row.template_type}'",
                    reason=f"El template tiene 0% de respuesta en las últimas 4 semanas con {total_sent} envíos.",
                    impact="Evita quemar contactos con un mensaje que no resuena.",
                    effort=Effort.LOW,
                    priority=Priority.P1,
                )
            )

    return recommendations


def _check_source_dry_spell(session: Session) -> List[Recommendation]:
    """
    Fuente sin producir A-tier en 14 días → recomienda revisar filtros o circuit breaker.
    """
    fourteen_days_ago = datetime.now(timezone.utc) - timedelta(days=14)

    # Get all sources that have been active (ingested jobs) in the last 14 days
    active_sources_stmt = select(Job.source).where(Job.scraped_at >= fourteen_days_ago).distinct()
    active_sources = session.scalars(active_sources_stmt).all()

    recommendations = []
    for source in active_sources:
        # Check if any of these are Tier A
        a_tier_count = (
            session.scalar(
                select(func.count(Job.id)).where(
                    and_(
                        Job.source == source,
                        Job.scraped_at >= fourteen_days_ago,
                        Job.tier == JobTier.A,
                    )
                )
            )
            or 0
        )

        if a_tier_count == 0:
            recommendations.append(
                Recommendation(
                    action=f"Revisar filtros de la fuente '{source}'",
                    reason="La fuente no ha producido ningún job Tier-A en los últimos 14 días.",
                    impact="Mejora la calidad de entrada y ahorra costos de procesamiento de jobs irrelevantes.",
                    effort=Effort.MEDIUM,
                    priority=Priority.P2,
                )
            )

    return recommendations


def _check_prompt_regression(session: Session) -> List[Recommendation]:
    """
    Prompt v actual con precision <80% en últimas 4 semanas (vs prev de 90%+) → recomienda rollback.
    Uses Email Matcher Precision as a proxy for 'precision' mentioned in the requirement.
    """
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(weeks=4)
    baseline_end = current_start
    baseline_start = baseline_end - timedelta(weeks=4)

    def calculate_precision(start: datetime, end: datetime) -> float:
        stmt = (
            select(EmailMessage.match_status, func.count(EmailMessage.id))
            .where(and_(EmailMessage.processed_at >= start, EmailMessage.processed_at <= end))
            .group_by(EmailMessage.match_status)
        )
        rows = session.execute(stmt).all()
        counts = {row[0]: row[1] for row in rows}

        auto = counts.get(EmailMatchStatus.AUTO_MATCHED, 0)
        ai = counts.get(EmailMatchStatus.AI_MATCHED, 0)
        confirmed = counts.get(EmailMatchStatus.USER_CONFIRMED, 0)
        rejected = counts.get(EmailMatchStatus.USER_REJECTED, 0)

        total_automated = auto + ai + confirmed + rejected
        if total_automated == 0:
            return 1.0  # No automated matches, assume perfect

        return float((auto + ai + confirmed) / total_automated)

    current_precision = calculate_precision(current_start, now)
    baseline_precision = calculate_precision(baseline_start, baseline_end)

    if current_precision < 0.8 and baseline_precision >= 0.9:
        recommendations = [
            Recommendation(
                action="Rollback del prompt de Email Matching",
                reason=f"La precisión actual ({current_precision:.1%}) ha caído por debajo del 80% (baseline {baseline_precision:.1%}).",
                impact="Mejora la confiabilidad de las sugerencias automáticas y reduce ruido.",
                effort=Effort.LOW,
                priority=Priority.P1,
            )
        ]
        return recommendations

    return []


def _check_manual_review_bottleneck(session: Session) -> List[Recommendation]:
    """
    30% de jobs en manual_review sin decisión > 7 días → recomienda revisar threshold de tier C.
    """
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    total_manual = (
        session.scalar(select(func.count(Job.id)).where(Job.status == JobStatus.MANUAL_REVIEW)) or 0
    )

    if total_manual == 0:
        return []

    old_manual = (
        session.scalar(
            select(func.count(Job.id)).where(
                and_(Job.status == JobStatus.MANUAL_REVIEW, Job.scraped_at <= seven_days_ago)
            )
        )
        or 0
    )

    if old_manual / total_manual > 0.3:
        return [
            Recommendation(
                action="Revisar threshold de Tier C",
                reason=f"Más del 30% de los jobs en Manual Review ({old_manual}/{total_manual}) llevan más de 7 días sin decisión.",
                impact="Descongestiona el pipeline de revisión manual ajustando qué jobs requieren atención humana.",
                effort=Effort.MEDIUM,
                priority=Priority.P2,
            )
        ]

    return []


def _check_budget_warning(session: Session) -> List[Recommendation]:
    """
    Costo LLM mensual >80% del budget → recomienda revisión de uso.
    """
    settings = Settings()  # type: ignore[call-arg]
    budget = settings.LLM_MONTHLY_BUDGET_USD

    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    current_cost = (
        session.scalar(
            select(func.sum(LLMCall.cost_usd)).where(LLMCall.called_at >= start_of_month)
        )
        or 0.0
    )

    if float(current_cost) > budget * 0.8:
        return [
            Recommendation(
                action="Revisar uso de LLM y modelos",
                reason=f"El gasto mensual actual (${current_cost:.2f}) supera el 80% del presupuesto (${budget:.2f}).",
                impact="Evita la interrupción del servicio por exceder el presupuesto mensual.",
                effort=Effort.MEDIUM,
                priority=Priority.P1,
            )
        ]

    return []


def _check_circuit_breaker_stuck(session: Session) -> List[Recommendation]:
    """
    Circuit breaker de fuente abierto >24h sin recuperación → recomienda investigar manualmente.
    """
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)

    stuck_breakers = session.scalars(
        select(SourceHealth).where(
            and_(
                SourceHealth.state == SourceState.OPEN,
                SourceHealth.last_failure_at <= twenty_four_hours_ago,
            )
        )
    ).all()

    recommendations = []
    for breaker in stuck_breakers:
        recommendations.append(
            Recommendation(
                action=f"Investigar fuente '{breaker.source_name}'",
                reason="El circuit breaker ha estado ABIERTO por más de 24 horas.",
                impact="Restaura la ingesta de jobs de una fuente potencialmente crítica.",
                effort=Effort.MEDIUM,
                priority=Priority.P1,
            )
        )

    return recommendations


def get_recommendations(session: Session) -> List[Recommendation]:
    """
    Engine that runs all heuristic recommendation checks and returns a consolidated list.
    """
    recommendations = []
    recommendations.extend(_check_template_zero_response(session))
    recommendations.extend(_check_source_dry_spell(session))
    recommendations.extend(_check_prompt_regression(session))
    recommendations.extend(_check_manual_review_bottleneck(session))
    recommendations.extend(_check_budget_warning(session))
    recommendations.extend(_check_circuit_breaker_stuck(session))
    return recommendations
