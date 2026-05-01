from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from jobhunter.db.models import FailedLoginAttempt, BlockedIP

logger = structlog.get_logger(__name__)


class SecurityRepo:
    """
    Repository for security-related database operations.
    """

    def __init__(self, session: Session):
        self.session = session

    def record_attempt(
        self, ip_address: str, outcome: str, user_agent: str | None = None
    ) -> FailedLoginAttempt:
        """
        Records a login attempt (success or failure).
        """
        attempt = FailedLoginAttempt(
            ip_address=ip_address,
            outcome=outcome,
            user_agent=user_agent,
            attempted_at=datetime.now(),
        )
        self.session.add(attempt)
        self.session.commit()

        logger.info(
            "security_event",
            event_type="login_attempt",
            ip_address=ip_address,
            outcome=outcome,
            user_agent=user_agent,
        )
        return attempt

    def is_ip_blocked(self, ip_address: str) -> bool:
        """
        Checks if an IP address is currently blocked.
        Also cleans up expired blocks for the given IP.
        """
        now = datetime.now()

        # Clean up expired blocks for this IP
        expired_stmt = select(BlockedIP).where(
            and_(BlockedIP.ip_address == ip_address, BlockedIP.unblock_at <= now)
        )
        expired_blocks = self.session.scalars(expired_stmt).all()
        for block in expired_blocks:
            self.session.delete(block)

        if expired_blocks:
            self.session.commit()

        # Check if still blocked
        stmt = select(BlockedIP).where(
            and_(BlockedIP.ip_address == ip_address, BlockedIP.unblock_at > now)
        )
        return self.session.scalar(stmt) is not None

    def get_failed_attempts_count(self, ip_address: str, since_minutes: int) -> int:
        """
        Returns the number of failed login attempts for an IP address within a timeframe.
        """
        since = datetime.now() - timedelta(minutes=since_minutes)
        stmt = select(func.count(FailedLoginAttempt.id)).where(
            and_(
                FailedLoginAttempt.ip_address == ip_address,
                FailedLoginAttempt.outcome == "failure",
                FailedLoginAttempt.attempted_at >= since,
            )
        )
        return self.session.scalar(stmt) or 0

    def block_ip(self, ip_address: str, duration_hours: int, reason: str) -> None:
        """
        Blocks an IP address for a specified duration.
        """
        unblock_at = datetime.now() + timedelta(hours=duration_hours)

        # Upsert blocked IP
        stmt = select(BlockedIP).where(BlockedIP.ip_address == ip_address)
        blocked = self.session.scalar(stmt)

        if blocked:
            blocked.unblock_at = unblock_at
            blocked.reason = reason
            blocked.blocked_at = datetime.now()
        else:
            blocked = BlockedIP(
                ip_address=ip_address,
                unblock_at=unblock_at,
                reason=reason,
                blocked_at=datetime.now(),
            )
            self.session.add(blocked)

        self.session.commit()

        logger.warning(
            "security_event",
            event_type="ip_blocked",
            ip_address=ip_address,
            duration_hours=duration_hours,
            reason=reason,
            unblock_at=unblock_at.isoformat(),
        )

    def is_new_ip(self, ip_address: str, days: int = 30) -> bool:
        """
        Checks if an IP address has successfully logged in within the last N days.
        """
        since = datetime.now() - timedelta(days=days)
        stmt = (
            select(FailedLoginAttempt.id)
            .where(
                and_(
                    FailedLoginAttempt.ip_address == ip_address,
                    FailedLoginAttempt.outcome == "success",
                    FailedLoginAttempt.attempted_at >= since,
                )
            )
            .limit(1)
        )
        return self.session.scalar(stmt) is None

    def get_distinct_failed_ips_count(self, since_minutes: int) -> int:
        """
        Returns the number of distinct IP addresses that have failed login attempts.
        Used for detecting distributed attacks.
        """
        since = datetime.now() - timedelta(minutes=since_minutes)
        stmt = select(func.count(func.distinct(FailedLoginAttempt.ip_address))).where(
            and_(FailedLoginAttempt.outcome == "failure", FailedLoginAttempt.attempted_at >= since)
        )
        return self.session.scalar(stmt) or 0
