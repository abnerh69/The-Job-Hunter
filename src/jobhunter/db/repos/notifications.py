import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobhunter.db.models import NotificationSent
from jobhunter.db.repos.base import BaseRepo
from jobhunter.notify.base import NotificationResult


class NotificationsRepo(BaseRepo[NotificationSent]):
    """
    Repository for managing NotificationSent records.
    """

    def __init__(self, session: Session):
        """
        Initializes the NotificationsRepo.

        Args:
            session: The SQLAlchemy session.
        """
        super().__init__(NotificationSent, session)

    def was_sent(self, channel: str, dedup_key: str) -> bool:
        """
        Checks if a notification has already been successfully sent for a given channel and dedup key.

        Args:
            channel: The notification channel (e.g., 'telegram', 'email').
            dedup_key: The unique deduplication key.

        Returns:
            bool: True if a successful notification exists, False otherwise.
        """
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.channel == channel,
                self.model.dedup_key == dedup_key,
                self.model.success.is_(True),
            )
        )
        count = self.session.scalar(stmt)
        return bool(count and count > 0)

    def record_sent(
        self, channel: str, dedup_key: str, job_id: uuid.UUID | None, result: NotificationResult
    ) -> NotificationSent:
        """
        Records a notification attempt in the database.

        Args:
            channel: The notification channel.
            dedup_key: The deduplication key.
            job_id: Optional ID of the associated job.
            result: The result of the notification attempt.

        Returns:
            NotificationSent: The created record.
        """
        notification = NotificationSent(
            channel=channel,
            dedup_key=dedup_key,
            job_id=job_id,
            provider_message_id=result.provider_message_id,
            success=result.success,
            error=result.error,
        )
        return self.create(notification)

    def failures_in_last(self, hours: int) -> int:
        """
        Counts the number of failed notification attempts in the last N hours.

        Args:
            hours: The number of hours to look back.

        Returns:
            int: The count of failed notifications.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.success.is_(False), self.model.sent_at >= since)
        )
        return self.session.scalar(stmt) or 0

    def get_recent(self, limit: int = 10) -> list[NotificationSent]:
        """
        Retrieves the most recent notification attempts.

        Args:
            limit: The maximum number of records to retrieve.

        Returns:
            list[NotificationSent]: The list of recent notifications.
        """
        stmt = select(self.model).order_by(self.model.sent_at.desc()).limit(limit)
        return list(self.session.scalars(stmt).all())

    def get_failure_breakdown(self, hours: int = 24) -> dict[str, int]:
        """
        Retrieves the number of failures per channel in the last N hours.

        Args:
            hours: The number of hours to look back.

        Returns:
            dict[str, int]: A dictionary mapping channel names to failure counts.
        """
        since = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(self.model.channel, func.count())
            .where(self.model.success.is_(False), self.model.sent_at >= since)
            .group_by(self.model.channel)
        )
        results = self.session.execute(stmt).all()
        return {row[0]: row[1] for row in results}
