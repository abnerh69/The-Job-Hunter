from datetime import date, datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from jobhunter.db.enums import (
    ApplicationStatus,
    JobStatus,
    JobTier,
    SourceState,
)
from jobhunter.db.models import Application, Job, LLMCall, SourceHealth
from jobhunter.db.repos.outreach import OutreachRepo
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo


class MetricsService:
    """
    Service for calculating dashboard metrics and analytics.
    Uses Streamlit caching to optimize performance.
    """

    def __init__(self, session: Session):
        """
        Initializes the MetricsService.

        Args:
            session (Session): The SQLAlchemy session.
        """
        self.session = session

    def get_funnel_metrics(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Aggregates metrics for the recruitment funnel.

        Args:
            start_date: Start of the period.
            end_date: End of the period.

        Returns:
            A list of dictionaries representing funnel stages and counts.
        """
        # Ingested: jobs scraped in period
        ingested_stmt = select(func.count(Job.id)).where(
            and_(
                func.date(Job.scraped_at) >= start_date,
                func.date(Job.scraped_at) <= end_date,
            )
        )
        ingested_count = self.session.scalar(ingested_stmt) or 0

        # Scored: jobs scored in period
        scored_stmt = select(func.count(Job.id)).where(
            and_(
                Job.scored_at.is_not(None),
                func.date(Job.scored_at) >= start_date,
                func.date(Job.scored_at) <= end_date,
            )
        )
        scored_count = self.session.scalar(scored_stmt) or 0

        # Queued: jobs that reached QUEUED status in period
        # Since we don't have full history, we count jobs that are currently QUEUED or beyond
        # and were scraped in this period.
        queued_stmt = select(func.count(Job.id)).where(
            and_(
                Job.status.in_([JobStatus.QUEUED, JobStatus.APPLIED, JobStatus.MANUAL_REVIEW]),
                func.date(Job.scraped_at) >= start_date,
                func.date(Job.scraped_at) <= end_date,
            )
        )
        queued_count = self.session.scalar(queued_stmt) or 0

        # Applied: applications created in period
        applied_stmt = select(func.count(Application.id)).where(
            and_(
                func.date(Application.applied_at) >= start_date,
                func.date(Application.applied_at) <= end_date,
            )
        )
        applied_count = self.session.scalar(applied_stmt) or 0

        # Screening: apps that reached screening or further
        screening_stmt = select(func.count(Application.id)).where(
            and_(
                Application.status.in_(
                    [
                        ApplicationStatus.SCREENING,
                        ApplicationStatus.INTERVIEW_1,
                        ApplicationStatus.INTERVIEW_N,
                        ApplicationStatus.OFFER,
                    ]
                ),
                func.date(Application.applied_at) >= start_date,
                func.date(Application.applied_at) <= end_date,
            )
        )
        screening_count = self.session.scalar(screening_stmt) or 0

        # Interview: apps that reached interview 1 or further
        interview_stmt = select(func.count(Application.id)).where(
            and_(
                Application.status.in_(
                    [
                        ApplicationStatus.INTERVIEW_1,
                        ApplicationStatus.INTERVIEW_N,
                        ApplicationStatus.OFFER,
                    ]
                ),
                func.date(Application.applied_at) >= start_date,
                func.date(Application.applied_at) <= end_date,
            )
        )
        interview_count = self.session.scalar(interview_stmt) or 0

        # Offer: apps that reached offer
        offer_stmt = select(func.count(Application.id)).where(
            and_(
                Application.status == ApplicationStatus.OFFER,
                func.date(Application.applied_at) >= start_date,
                func.date(Application.applied_at) <= end_date,
            )
        )
        offer_count = self.session.scalar(offer_stmt) or 0

        return [
            {"stage": "1. Ingested", "count": ingested_count},
            {"stage": "2. Scored", "count": scored_count},
            {"stage": "3. Queued", "count": queued_count},
            {"stage": "4. Applied", "count": applied_count},
            {"stage": "5. Screening", "count": screening_count},
            {"stage": "6. Interview", "count": interview_count},
            {"stage": "7. Offer", "count": offer_count},
        ]

    def get_source_metrics(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Calculates performance metrics per job source.

        Args:
            start_date: Start of the period.
            end_date: End of the period.

        Returns:
            A list of dictionaries with metrics per source.
        """
        # This query is more complex, might be better to do it in multiple steps or a joined query
        sources_stmt = select(Job.source).distinct()
        sources = self.session.scalars(sources_stmt).all()

        results = []
        for source in sources:
            # Total ingested
            ingested = (
                self.session.scalar(
                    select(func.count(Job.id)).where(
                        and_(
                            Job.source == source,
                            func.date(Job.scraped_at) >= start_date,
                            func.date(Job.scraped_at) <= end_date,
                        )
                    )
                )
                or 0
            )

            # Tier A
            tier_a = (
                self.session.scalar(
                    select(func.count(Job.id)).where(
                        and_(
                            Job.source == source,
                            Job.tier == JobTier.A,
                            func.date(Job.scraped_at) >= start_date,
                            func.date(Job.scraped_at) <= end_date,
                        )
                    )
                )
                or 0
            )

            # Applied
            applied = (
                self.session.scalar(
                    select(func.count(Application.id))
                    .join(Job)
                    .where(
                        and_(
                            Job.source == source,
                            func.date(Application.applied_at) >= start_date,
                            func.date(Application.applied_at) <= end_date,
                        )
                    )
                )
                or 0
            )

            # Response rate
            responded = (
                self.session.scalar(
                    select(func.count(Application.id))
                    .join(Job)
                    .where(
                        and_(
                            Job.source == source,
                            Application.status.notin_(
                                [
                                    ApplicationStatus.APPLIED,
                                    ApplicationStatus.GHOSTED,
                                    ApplicationStatus.WITHDRAWN,
                                ]
                            ),
                            func.date(Application.applied_at) >= start_date,
                            func.date(Application.applied_at) <= end_date,
                        )
                    )
                )
                or 0
            )

            results.append(
                {
                    "source": source,
                    "ingested": ingested,
                    "tier_a_pct": (tier_a / ingested * 100) if ingested > 0 else 0,
                    "applied": applied,
                    "response_rate": (responded / applied * 100) if applied > 0 else 0,
                }
            )

        return sorted(results, key=lambda x: x["ingested"], reverse=True)

    def get_temporal_trends(self, weeks: int = 8) -> List[Dict[str, Any]]:
        """
        Retrieves temporal trends from the weekly_metrics materialized view.
        Falls back to raw SQL/ORM if view is missing or on non-PostgreSQL.

        Args:
            weeks: Number of weeks to retrieve.

        Returns:
            A list of dictionaries with weekly metrics.
        """
        is_postgres = self.session.bind.dialect.name == "postgresql" if self.session.bind else False

        if is_postgres:
            try:
                stmt_text = text(
                    "SELECT * FROM weekly_metrics ORDER BY week DESC LIMIT :limit"
                ).bindparams(limit=weeks)
                rows = self.session.execute(stmt_text).fetchall()
                return [
                    {
                        "week": row.week,
                        "apps_sent": row.apps_sent,
                        "apps_with_response": row.apps_with_response,
                        "interviews": row.interviews,
                        "offers": row.offers,
                        "response_rate": (row.apps_with_response / row.apps_sent * 100)
                        if row.apps_sent > 0
                        else 0,
                    }
                    for row in rows
                ]
            except Exception:
                # Fallback to calculation if view fails
                pass

        # Manual calculation (simplified)
        end_date = date.today()
        start_date = end_date - timedelta(weeks=weeks)

        # In a real scenario, this would be a single complex query.
        # For now, let's just return an empty list or a basic one if we have apps.
        if is_postgres:
            stmt_select = select(
                func.date_trunc("week", Application.applied_at).label("week"),
                func.count(Application.id).label("apps_sent"),
            ).where(func.date(Application.applied_at) >= start_date)
        else:
            # SQLite version of date_trunc to week (Monday start)
            # strftime('%Y-%W', ...) is not exactly the same but let's use a simpler approach
            # for the dashboard on SQLite (mostly for dev/test)
            stmt_select = select(
                func.date(Application.applied_at, "weekday 0", "-6 days").label("week"),
                func.count(Application.id).label("apps_sent"),
            ).where(func.date(Application.applied_at) >= start_date)

        stmt_select = stmt_select.group_by(text("week")).order_by(text("week DESC"))

        rows = self.session.execute(stmt_select).all()
        return [
            {
                "week": row.week
                if isinstance(row.week, (date, datetime))
                else date.fromisoformat(row.week),
                "apps_sent": row.apps_sent,
                "response_rate": 0,  # Placeholder for simplified fallback
            }
            for row in rows
        ]

    def get_llm_cost_metrics(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Aggregates LLM cost and usage metrics.

        Args:
            start_date: Start of the period.
            end_date: End of the period.

        Returns:
            A dictionary with total cost, purpose breakdown, and daily trend.
        """
        # Total cost
        total_cost_stmt = select(func.sum(LLMCall.cost_usd)).where(
            and_(
                func.date(LLMCall.called_at) >= start_date,
                func.date(LLMCall.called_at) <= end_date,
            )
        )
        total_cost = float(self.session.scalar(total_cost_stmt) or 0.0)

        # Breakdown by purpose
        purpose_stmt = (
            select(LLMCall.purpose, func.sum(LLMCall.cost_usd))
            .where(
                and_(
                    func.date(LLMCall.called_at) >= start_date,
                    func.date(LLMCall.called_at) <= end_date,
                )
            )
            .group_by(LLMCall.purpose)
        )
        purpose_rows = self.session.execute(purpose_stmt).all()
        purpose_breakdown = {row[0]: float(row[1] or 0.0) for row in purpose_rows}

        # Daily trend
        daily_stmt = (
            select(func.date(LLMCall.called_at).label("day"), func.sum(LLMCall.cost_usd))
            .where(
                and_(
                    func.date(LLMCall.called_at) >= start_date,
                    func.date(LLMCall.called_at) <= end_date,
                )
            )
            .group_by(text("day"))
            .order_by(text("day"))
        )
        daily_rows = self.session.execute(daily_stmt).all()
        daily_trend = [
            {
                "day": row[0] if isinstance(row[0], date) else date.fromisoformat(row[0]),
                "cost": float(row[1] or 0.0),
            }
            for row in daily_rows
        ]

        return {
            "total_cost_usd": total_cost,
            "purpose_breakdown": purpose_breakdown,
            "daily_trend": daily_trend,
        }

    def get_tier_distribution(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Calculates the distribution of jobs across tiers.

        Args:
            start_date: Start of the period.
            end_date: End of the period.

        Returns:
            A list of dictionaries with tier counts.
        """
        stmt = (
            select(Job.tier, func.count(Job.id))
            .where(
                and_(
                    func.date(Job.scraped_at) >= start_date,
                    func.date(Job.scraped_at) <= end_date,
                    Job.tier.is_not(None),
                )
            )
            .group_by(Job.tier)
        )
        rows = self.session.execute(stmt).all()
        return [{"tier": row[0], "count": row[1]} for row in rows]

    def get_system_health(self) -> List[Dict[str, Any]]:
        """
        Retrieves current system health status.

        Returns:
            A list of dictionaries with source health info.
        """
        stmt = select(SourceHealth)
        health_records = self.session.scalars(stmt).all()

        # Also get last ingestion time per source
        last_ingest_stmt = select(Job.source, func.max(Job.scraped_at)).group_by(Job.source)
        last_ingest_rows = self.session.execute(last_ingest_stmt).all()
        last_ingest_map = {row[0]: row[1] for row in last_ingest_rows}

        results = []
        for hr in health_records:
            results.append(
                {
                    "source": hr.source_name,
                    "state": hr.state,
                    "failures": hr.failure_count,
                    "last_failure": hr.last_failure_at,
                    "last_ingest": last_ingest_map.get(hr.source_name),
                }
            )

        # Add sources that might not have health records yet
        for source, last_time in last_ingest_map.items():
            if not any(r["source"] == source for r in results):
                results.append(
                    {
                        "source": source,
                        "state": SourceState.CLOSED,
                        "failures": 0,
                        "last_failure": None,
                        "last_ingest": last_time,
                    }
                )

        return results

    def get_outreach_stats(self, start_date: date) -> Dict[str, Any]:
        """
        Retrieves outreach statistics.

        Args:
            start_date: Start of the period for stats.

        Returns:
            A dictionary with outreach metrics.
        """
        msg_repo = OutreachMessageRepo(self.session)
        # Convert date to datetime at start of day
        start_dt = datetime.combine(start_date, datetime.min.time())
        return msg_repo.get_stats(start_dt)

    def get_warmest_contacts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top warmest outreach contacts.

        Args:
            limit: Maximum number of contacts to return.

        Returns:
            A list of dictionaries with contact info.
        """
        outreach_repo = OutreachRepo(self.session)
        contacts = outreach_repo.list_warmest_contacts(limit=limit)
        return [
            {
                "name": c.name,
                "company": c.company,
                "status": c.status,
                "last_contacted_at": c.last_contacted_at,
            }
            for c in contacts
        ]


def get_metrics_service(session: Session) -> MetricsService:
    """
    Factory function to get a MetricsService instance.
    """
    return MetricsService(session)
