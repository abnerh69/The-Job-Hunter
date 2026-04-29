from datetime import date, timedelta, datetime, timezone
from typing import Any
import pytest
from sqlalchemy.orm import Session
from jobhunter.db.models import Job, Application
from jobhunter.db.enums import JobTier, JobStatus, ApplicationStatus
from jobhunter.notify.digest import compute_digest_context, send_weekly_digest
from jobhunter.db.repos.notifications import NotificationsRepo


@pytest.mark.asyncio
async def test_compute_digest_context_with_data(session: Session) -> None:
    # Setup: Create some jobs and apps for the week
    week_ending = date.today()
    scraped_at = datetime.now(timezone.utc)

    job_a = Job(
        title="Software Engineer",
        company="Tech Corp",
        url="http://example.com/a",
        url_hash="hash_a",
        tier=JobTier.A,
        status=JobStatus.QUEUED,
        scraped_at=scraped_at,
        description="Desc A",
        source="linkedin",
    )
    job_b = Job(
        title="Frontend Developer",
        company="Design Studio",
        url="http://example.com/b",
        url_hash="hash_b",
        tier=JobTier.B,
        status=JobStatus.QUEUED,
        scraped_at=scraped_at,
        description="Desc B",
        source="linkedin",
    )
    job_c = Job(
        title="Backend dev",
        company="Cloud Services",
        url="http://example.com/c",
        url_hash="hash_c",
        tier=JobTier.C,
        status=JobStatus.MANUAL_REVIEW,
        scraped_at=scraped_at,
        description="Desc C",
        source="linkedin",
    )
    session.add_all([job_a, job_b, job_c])
    session.flush()

    app_a = Application(
        job_id=job_a.id,
        applied_at=datetime.now(timezone.utc),
        status=ApplicationStatus.APPLIED,
        next_action="Follow up",
        next_action_due=date.today() - timedelta(days=1),
    )
    session.add(app_a)
    session.commit()

    context = compute_digest_context(session, week_ending)

    assert context.end_date == week_ending
    assert context.metrics.new_jobs_total == 3
    assert context.metrics.new_jobs_tier_a == 1
    assert context.metrics.new_jobs_tier_b == 1
    assert context.metrics.new_jobs_tier_c == 1
    assert context.metrics.apps_sent_this_week == 1
    assert context.metrics.pending_followups_count == 1
    assert context.metrics.queued_tier_a_count == 1
    assert context.metrics.manual_review_tier_c_count == 1
    assert len(context.top_tier_a_queued) == 1
    assert context.top_tier_a_queued[0].title == "Software Engineer"
    assert len(context.followups_due) == 1
    assert context.followups_due[0].job_company == "Tech Corp"
    assert context.is_empty_pipeline is False


@pytest.mark.asyncio
async def test_compute_digest_context_empty(session: Session) -> None:
    week_ending = date.today()
    context = compute_digest_context(session, week_ending)

    assert context.metrics.new_jobs_total == 0
    assert context.metrics.apps_sent_this_week == 0
    assert context.is_empty_pipeline is True


@pytest.mark.asyncio
async def test_send_weekly_digest_idempotency(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Mock EmailNotifier.send to always succeed
    class MockResult:
        success: bool = True
        provider_message_id: str | None = "test-msg-id"
        error: str | None = None
        duration_ms: int = 100

    async def mock_send(self: Any, message: Any) -> MockResult:
        return MockResult()

    from jobhunter.notify.email import EmailNotifier

    monkeypatch.setattr(EmailNotifier, "send", mock_send)
    monkeypatch.setenv("SMTP_USER", "test@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("DIGEST_TO_EMAIL", "recipient@example.com")

    week_ending = date.today()

    # First send
    result1 = await send_weekly_digest(session, week_ending)
    assert result1 is not None
    assert result1.success is True

    # Second send (should be skipped)
    result2 = await send_weekly_digest(session, week_ending)
    assert result2 is None

    # Verify DB record
    iso_year, iso_week, _ = week_ending.isocalendar()
    dedup_key = f"digest:{iso_year}:{iso_week}"
    repo = NotificationsRepo(session)
    assert repo.was_sent("email", dedup_key) is True
