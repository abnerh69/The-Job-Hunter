from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.models import LLMCall
from jobhunter.db.repos.base import BaseRepo


class LLMCallRepo(BaseRepo[LLMCall]):
    """
    Repository for managing LLMCall records.
    """

    def __init__(self, session: Session):
        """
        Initializes the repository with the LLMCall model.

        Args:
            session: The SQLAlchemy session.
        """
        super().__init__(LLMCall, session)

    def record_call(
        self,
        model: str,
        purpose: LLMPurpose,
        success: bool,
        job_id: UUID | None = None,
        prompt_version: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cost_usd: float | None = None,
        duration_ms: int | None = None,
    ) -> LLMCall:
        """
        Records an LLM call.

        Args:
            model: The LLM model name.
            purpose: The purpose of the call.
            success: Whether the call was successful.
            job_id: The ID of the job associated with the call, if any.
            prompt_version: The version of the prompt used.
            input_tokens: The number of input tokens used.
            output_tokens: The number of output tokens used.
            cost_usd: The cost of the call in USD.
            duration_ms: The duration of the call in milliseconds.

        Returns:
            The created LLMCall instance.
        """
        call = LLMCall(
            model=model,
            purpose=purpose,
            success=success,
            job_id=job_id,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            called_at=datetime.now(timezone.utc),
        )
        return self.create(call)

    def monthly_total_usd(self, year: int, month: int) -> float:
        """
        Calculates the total cost of LLM calls for a given month.

        Args:
            year: The year.
            month: The month (1-12).

        Returns:
            The total cost in USD.
        """
        start_date = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc)

        stmt = select(func.sum(LLMCall.cost_usd)).where(
            LLMCall.called_at >= start_date,
            LLMCall.called_at < end_date,
        )
        result = self.session.scalar(stmt)
        return float(result or 0.0)

    def weekly_total_usd(self, date_in_week: datetime) -> float:
        """
        Calculates the total cost of LLM calls for the week containing the given date.
        Assumes the week starts on Monday.

        Args:
            date_in_week: A datetime within the desired week.

        Returns:
            The total cost in USD.
        """
        # Normalize to start of day
        dt = date_in_week.replace(hour=0, minute=0, second=0, microsecond=0)
        # Find Monday (weekday 0)
        monday = dt - timedelta(days=dt.weekday())
        sunday_end = monday + timedelta(days=7)

        stmt = select(func.sum(LLMCall.cost_usd)).where(
            LLMCall.called_at >= monday,
            LLMCall.called_at < sunday_end,
        )
        result = self.session.scalar(stmt)
        return float(result or 0.0)

    def get_stats_by_model(self, start_date: datetime, end_date: datetime) -> list[dict[str, Any]]:
        """
        Retrieves statistics broken down by model for a given period.

        Args:
            start_date: The start of the period.
            end_date: The end of the period.

        Returns:
            A list of dictionaries with model statistics.
        """
        from sqlalchemy import case as sa_case

        stmt = (
            select(
                LLMCall.model,
                func.count(LLMCall.id).label("total_calls"),
                func.sum(sa_case((LLMCall.success == True, 1), else_=0)).label("success_count"),
                func.sum(LLMCall.cost_usd).label("total_cost"),
            )
            .where(
                LLMCall.called_at >= start_date,
                LLMCall.called_at < end_date,
            )
            .group_by(LLMCall.model)
        )

        results = self.session.execute(stmt).all()
        return [
            {
                "model": row.model,
                "total_calls": row.total_calls,
                "success_count": row.success_count,
                "total_cost": float(row.total_cost or 0.0),
            }
            for row in results
        ]
