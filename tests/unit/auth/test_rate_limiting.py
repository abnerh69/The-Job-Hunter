import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from jobhunter.db.repos.security import SecurityRepo
from jobhunter.db.models import FailedLoginAttempt, BlockedIP


@pytest.fixture
def security_repo(session: Session) -> SecurityRepo:
    return SecurityRepo(session)


def test_record_attempt(security_repo: SecurityRepo, session: Session) -> None:
    security_repo.record_attempt("1.2.3.4", "failure", "Mozilla/5.0")

    attempt = session.query(FailedLoginAttempt).first()
    assert attempt is not None
    assert attempt.ip_address == "1.2.3.4"
    assert attempt.outcome == "failure"
    assert attempt.user_agent == "Mozilla/5.0"


def test_is_ip_blocked(security_repo: SecurityRepo, session: Session) -> None:
    ip = "1.1.1.1"
    assert not security_repo.is_ip_blocked(ip)

    security_repo.block_ip(ip, 1, "Testing")
    assert security_repo.is_ip_blocked(ip)

    # Manually expire block
    block = session.query(BlockedIP).filter_by(ip_address=ip).one()
    block.unblock_at = datetime.now() - timedelta(seconds=1)
    session.commit()

    assert not security_repo.is_ip_blocked(ip)
    assert session.query(BlockedIP).filter_by(ip_address=ip).count() == 0


def test_failed_attempts_count(security_repo: SecurityRepo, session: Session) -> None:
    ip = "2.2.2.2"
    for _ in range(3):
        security_repo.record_attempt(ip, "failure")
    security_repo.record_attempt(ip, "success")
    security_repo.record_attempt("3.3.3.3", "failure")

    assert security_repo.get_failed_attempts_count(ip, 15) == 3


def test_is_new_ip(security_repo: SecurityRepo, session: Session) -> None:
    ip = "4.4.4.4"
    assert security_repo.is_new_ip(ip)

    security_repo.record_attempt(ip, "failure")
    assert security_repo.is_new_ip(ip)

    security_repo.record_attempt(ip, "success")
    assert not security_repo.is_new_ip(ip)


def test_distinct_failed_ips_count(security_repo: SecurityRepo, session: Session) -> None:
    security_repo.record_attempt("1.1.1.1", "failure")
    security_repo.record_attempt("1.1.1.1", "failure")
    security_repo.record_attempt("2.2.2.2", "failure")
    security_repo.record_attempt("3.3.3.3", "success")

    assert security_repo.get_distinct_failed_ips_count(60) == 2
