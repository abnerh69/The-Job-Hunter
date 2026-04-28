import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from jobhunter.db.enums import SourceState
from jobhunter.db.models import SourceHealth
from jobhunter.db.repos.source_health import SourceHealthRepo
from jobhunter.sources.circuit_breaker import CircuitBreaker


@pytest.fixture
def mock_repo():
    repo = MagicMock(spec=SourceHealthRepo)
    repo.session = MagicMock()
    return repo


def test_allow_request_closed(mock_repo):
    mock_repo.get_or_create.return_value = SourceHealth(
        source_name="test", state=SourceState.CLOSED
    )
    cb = CircuitBreaker(mock_repo)
    assert cb.allow_request("test") is True


def test_allow_request_open_not_expired(mock_repo):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    mock_repo.get_or_create.return_value = SourceHealth(
        source_name="test", state=SourceState.OPEN, opened_until=future
    )
    cb = CircuitBreaker(mock_repo)
    assert cb.allow_request("test") is False


def test_allow_request_open_expired_transitions_to_half_open(mock_repo):
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    health = SourceHealth(source_name="test", state=SourceState.OPEN, opened_until=past)
    mock_repo.get_or_create.return_value = health
    cb = CircuitBreaker(mock_repo)

    assert cb.allow_request("test") is True
    assert health.state == SourceState.HALF_OPEN


def test_record_failure_opens_circuit(mock_repo):
    health = SourceHealth(source_name="test", state=SourceState.CLOSED, failure_count=2)
    mock_repo.get_or_create.return_value = health
    cb = CircuitBreaker(mock_repo)

    cb.record_failure("test")

    assert health.failure_count == 3
    assert health.state == SourceState.OPEN
    assert health.opened_until is not None


def test_record_success_closes_circuit(mock_repo):
    health = SourceHealth(
        source_name="test",
        state=SourceState.OPEN,
        failure_count=3,
        opened_until=datetime.now(timezone.utc),
    )
    mock_repo.get_or_create.return_value = health
    cb = CircuitBreaker(mock_repo)

    cb.record_success("test")

    assert health.state == SourceState.CLOSED
    assert health.failure_count == 0
    assert health.opened_until is None


def test_half_open_failure_reopens_circuit(mock_repo):
    health = SourceHealth(source_name="test", state=SourceState.HALF_OPEN, failure_count=0)
    mock_repo.get_or_create.return_value = health
    cb = CircuitBreaker(mock_repo)

    cb.record_failure("test")

    assert health.state == SourceState.OPEN
    assert health.failure_count == 1
