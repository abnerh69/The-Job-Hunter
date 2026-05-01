from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import email_metrics
from jobhunter.db.enums import EmailMatchStatus
from jobhunter.db.models import EmailMessage


def test_get_matcher_metrics(session: Session) -> None:
    msg1 = EmailMessage(
        gmail_message_id="id1",
        received_at=datetime.now(timezone.utc),
        from_email="test@example.com",
        body_hash="hash1",
        match_status=EmailMatchStatus.USER_CONFIRMED,
        processed_at=datetime.now(timezone.utc),
    )
    msg2 = EmailMessage(
        gmail_message_id="id2",
        received_at=datetime.now(timezone.utc),
        from_email="test@example.com",
        body_hash="hash2",
        match_status=EmailMatchStatus.USER_REJECTED,
        processed_at=datetime.now(timezone.utc),
    )
    session.add_all([msg1, msg2])
    session.commit()

    today = date.today()
    result = email_metrics.get_matcher_metrics(session, today, today)

    assert result.total_processed == 2
    assert result.user_confirmed == 1
    assert result.user_rejected == 1
    assert result.precision == 0.5
