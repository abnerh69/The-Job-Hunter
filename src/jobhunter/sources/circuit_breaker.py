import structlog
from datetime import datetime, timedelta, timezone

from jobhunter.db.enums import SourceState
from jobhunter.db.repos.source_health import SourceHealthRepo

logger = structlog.get_logger(__name__)


class CircuitBreaker:
    """
    Implements a circuit breaker pattern for job sources.
    Persistence is handled via SourceHealthRepo.
    """

    FAILURE_THRESHOLD = 3
    PAUSE_DURATION = timedelta(hours=24)
    HALF_OPEN_PROBE_COUNT = 1

    def __init__(self, repo: SourceHealthRepo):
        """
        Initializes the CircuitBreaker.

        Args:
            repo (SourceHealthRepo): The repository for source health.
        """
        self.repo = repo

    def allow_request(self, source_name: str) -> bool:
        """
        Checks if a request to the source is allowed based on its health state.

        Args:
            source_name (str): The name of the source.

        Returns:
            bool: True if the request is allowed, False otherwise.
        """
        health = self.repo.get_or_create(source_name)
        now = datetime.now(timezone.utc)

        if health.state == SourceState.CLOSED:
            return True

        if health.state == SourceState.OPEN:
            if health.opened_until and now >= health.opened_until:
                # Transition to HALF_OPEN
                logger.info("circuit_breaker_transition_half_open", source_name=source_name)
                health.state = SourceState.HALF_OPEN
                self.repo.session.flush()
                return True
            return False

        if health.state == SourceState.HALF_OPEN:
            # In simple custom implementation, we allow requests in HALF_OPEN
            # and decide next state based on success/failure.
            return True

        return True

    def record_success(self, source_name: str) -> None:
        """
        Records a successful request to the source, potentially closing the breaker.

        Args:
            source_name (str): The name of the source.
        """
        health = self.repo.get_or_create(source_name)

        if health.state != SourceState.CLOSED:
            logger.info("circuit_breaker_closed", source_name=source_name)

        health.state = SourceState.CLOSED
        health.failure_count = 0
        health.last_failure_at = None
        health.opened_until = None
        self.repo.session.flush()

    def record_failure(self, source_name: str) -> None:
        """
        Records a failed request to the source, potentially opening the breaker.

        Args:
            source_name (str): The name of the source.
        """
        health = self.repo.get_or_create(source_name)
        now = datetime.now(timezone.utc)

        health.failure_count += 1
        health.last_failure_at = now

        if health.state == SourceState.CLOSED:
            if health.failure_count >= self.FAILURE_THRESHOLD:
                logger.warning(
                    "circuit_breaker_opened",
                    source_name=source_name,
                    failure_count=health.failure_count,
                )
                health.state = SourceState.OPEN
                health.opened_until = now + self.PAUSE_DURATION
        elif health.state == SourceState.HALF_OPEN:
            logger.warning("circuit_breaker_reopened_from_half_open", source_name=source_name)
            health.state = SourceState.OPEN
            health.opened_until = now + self.PAUSE_DURATION

        self.repo.session.flush()
