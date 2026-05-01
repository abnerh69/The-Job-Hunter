from datetime import date
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from jobhunter.analytics import (
    cost_metrics,
    outreach_metrics,
    pipeline_metrics,
    quality_metrics,
    recommendations,
)
from jobhunter.db.enums import SourceState
from jobhunter.db.models import Job, SourceHealth


class MetricsService:
    """
    Service for calculating dashboard metrics and analytics.
    Delegates to the jobhunter.analytics package.
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
        """
        result = pipeline_metrics.get_funnel_metrics(self.session, start_date, end_date)
        return [stage.model_dump() for stage in result.stages]

    def get_source_metrics(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Calculates performance metrics per job source.
        """
        results = quality_metrics.get_source_performance(self.session, start_date, end_date)
        return [res.model_dump() for res in results]

    def get_temporal_trends(self, weeks: int = 8) -> List[Dict[str, Any]]:
        """
        Retrieves temporal trends.
        """
        results = pipeline_metrics.get_weekly_trends(self.session, weeks)
        return [res.model_dump() for res in results]

    def get_llm_cost_metrics(self, start_date: date, end_date: date) -> Dict[str, Any]:
        """
        Aggregates LLM cost and usage metrics.
        """
        result = cost_metrics.get_llm_costs(self.session, start_date, end_date)
        return result.model_dump()

    def get_tier_distribution(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        """
        Calculates the distribution of jobs across tiers.
        """
        result = quality_metrics.get_tier_distribution(self.session, start_date, end_date)
        return [item.model_dump() for item in result.distribution]

    def get_system_health(self) -> List[Dict[str, Any]]:
        """
        Retrieves current system health status.
        """
        # This remains here as it's more of a health check than an analytics metric
        from sqlalchemy import func, select

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
        """
        from datetime import datetime

        start_dt = datetime.combine(start_date, datetime.min.time())
        result = outreach_metrics.get_outreach_performance(self.session, start_dt)
        return result.model_dump()

    def get_warmest_contacts(self, limit: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves top warmest outreach contacts.
        """
        results = outreach_metrics.get_warmest_contacts(self.session, limit)
        return [res.model_dump() for res in results]

    def get_recommendations(self) -> List[Dict[str, Any]]:
        """
        Retrieves actionable recommendations.
        """
        results = recommendations.get_recommendations(self.session)
        return [res.model_dump() for res in results]


def get_metrics_service(session: Session) -> MetricsService:
    """
    Factory function to get a MetricsService instance.
    """
    return MetricsService(session)
