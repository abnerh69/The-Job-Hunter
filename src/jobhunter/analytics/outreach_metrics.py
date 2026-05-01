from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.orm import Session

from jobhunter.db.enums import (
    OutreachMarket,
    OutreachMessageStatus,
    OutreachStatus,
    OutreachTemplateType,
)
from jobhunter.db.models import OutreachContact, OutreachMessage


class TemplateStat(BaseModel):
    """Statistics for an outreach template."""

    template_type: OutreachTemplateType
    sent: int
    replied: int
    rate: float


class MarketStat(BaseModel):
    """Statistics for an outreach market."""

    market: Optional[OutreachMarket]
    sent: int
    replied: int
    rate: float


class QualityStat(BaseModel):
    """Statistics for outreach quality score bins."""

    score_bin: str
    sent: int
    replied: int
    rate: float


class OutreachPerformance(BaseModel):
    """Aggregated outreach performance metrics."""

    total_sent: int
    total_replied: int
    response_rate: float
    template_stats: List[TemplateStat]
    market_stats: List[MarketStat]
    quality_stats: List[QualityStat]
    mean_response_time: float
    status_counts: Dict[str, int]


class WarmContact(BaseModel):
    """A contact identified as 'warm' based on interactions."""

    name: str
    company: Optional[str]
    status: OutreachStatus
    last_contacted_at: Optional[datetime]


def get_outreach_performance(session: Session, start_date: datetime) -> OutreachPerformance:
    """
    Calculates detailed outreach performance metrics.

    Args:
        session: SQLAlchemy session.
        start_date: Start date for statistics.

    Returns:
        OutreachPerformance: The aggregated performance metrics.
    """
    # Sent messages count
    sent_stmt = select(func.count(OutreachMessage.id)).where(
        and_(
            OutreachMessage.status != OutreachMessageStatus.DRAFT,
            OutreachMessage.sent_at >= start_date,
        )
    )
    total_sent = session.scalar(sent_stmt) or 0

    # Replied messages count
    replied_stmt = select(func.count(OutreachMessage.id)).where(
        and_(
            OutreachMessage.status == OutreachMessageStatus.REPLIED,
            OutreachMessage.sent_at >= start_date,
        )
    )
    total_replied = session.scalar(replied_stmt) or 0

    # Global response rate
    response_rate = (total_replied / total_sent) if total_sent > 0 else 0.0

    # Template stats
    template_rows = session.execute(
        select(
            OutreachMessage.template_type,
            func.count(OutreachMessage.id).label("sent"),
            func.sum(
                case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
            ).label("replied"),
        )
        .where(
            and_(
                OutreachMessage.status != OutreachMessageStatus.DRAFT,
                OutreachMessage.sent_at >= start_date,
            )
        )
        .group_by(OutreachMessage.template_type)
    ).all()

    template_stats = [
        TemplateStat(
            template_type=row.template_type,
            sent=int(row.sent),
            replied=int(row.replied or 0),
            rate=(float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
        )
        for row in template_rows
    ]

    # Market stats
    market_rows = session.execute(
        select(
            OutreachContact.market,
            func.count(OutreachMessage.id).label("sent"),
            func.sum(
                case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
            ).label("replied"),
        )
        .join(OutreachContact, OutreachMessage.contact_id == OutreachContact.id)
        .where(
            and_(
                OutreachMessage.status != OutreachMessageStatus.DRAFT,
                OutreachMessage.sent_at >= start_date,
            )
        )
        .group_by(OutreachContact.market)
    ).all()

    market_stats = [
        MarketStat(
            market=row.market,
            sent=int(row.sent),
            replied=int(row.replied or 0),
            rate=(float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
        )
        for row in market_rows
    ]

    # Quality stats (binned: 1-2, 3-4, 5)
    quality_score_case = case(
        (OutreachContact.quality_score >= 5, "5"),
        (OutreachContact.quality_score >= 3, "3-4"),
        else_="1-2",
    ).label("score_bin")

    quality_rows = session.execute(
        select(
            quality_score_case,
            func.count(OutreachMessage.id).label("sent"),
            func.sum(
                case((OutreachMessage.status == OutreachMessageStatus.REPLIED, 1), else_=0)
            ).label("replied"),
        )
        .join(OutreachContact, OutreachMessage.contact_id == OutreachContact.id)
        .where(
            and_(
                OutreachMessage.status != OutreachMessageStatus.DRAFT,
                OutreachMessage.sent_at >= start_date,
            )
        )
        .group_by(text("score_bin"))
    ).all()

    quality_stats = [
        QualityStat(
            score_bin=row.score_bin,
            sent=int(row.sent),
            replied=int(row.replied or 0),
            rate=(float(row.replied or 0) / float(row.sent)) if row.sent > 0 else 0.0,
        )
        for row in quality_rows
    ]

    # Mean response time
    response_time_stmt = select(
        func.avg(
            func.julianday(OutreachMessage.replied_at) - func.julianday(OutreachMessage.sent_at)
        )
        * 86400
    ).where(
        and_(
            OutreachMessage.status == OutreachMessageStatus.REPLIED,
            OutreachMessage.sent_at >= start_date,
        )
    )

    if session.bind and session.bind.dialect.name == "postgresql":
        response_time_stmt = select(
            func.avg(
                func.extract("epoch", OutreachMessage.replied_at)
                - func.extract("epoch", OutreachMessage.sent_at)
            )
        ).where(
            and_(
                OutreachMessage.status == OutreachMessageStatus.REPLIED,
                OutreachMessage.sent_at >= start_date,
            )
        )

    mean_response_time = session.scalar(response_time_stmt)

    # Status counts
    status_counts_rows = session.execute(
        select(OutreachMessage.status, func.count(OutreachMessage.id))
        .where(OutreachMessage.status != OutreachMessageStatus.DISCARDED)
        .group_by(OutreachMessage.status)
    ).all()
    status_counts = {row[0]: int(row[1]) for row in status_counts_rows}

    return OutreachPerformance(
        total_sent=total_sent,
        total_replied=total_replied,
        response_rate=response_rate,
        template_stats=template_stats,
        market_stats=market_stats,
        quality_stats=quality_stats,
        mean_response_time=float(mean_response_time or 0),
        status_counts=status_counts,
    )


def get_warmest_contacts(session: Session, limit: int = 5) -> List[WarmContact]:
    """
    Retrieves the warmest contacts based on outreach status and interactions.

    Args:
        session: SQLAlchemy session.
        limit: Maximum number of contacts to return.

    Returns:
        List[WarmContact]: A list of warm contacts.
    """
    # Contacts with status REPLIED or WARM are considered warmest.
    # Order by last_contacted_at desc.
    stmt = (
        select(OutreachContact)
        .where(OutreachContact.status.in_([OutreachStatus.REPLIED, OutreachStatus.WARM]))
        .order_by(OutreachContact.last_contacted_at.desc())
        .limit(limit)
    )
    contacts = session.scalars(stmt).all()
    return [
        WarmContact(
            name=c.name,
            company=c.company,
            status=c.status,
            last_contacted_at=c.last_contacted_at,
        )
        for c in contacts
    ]
