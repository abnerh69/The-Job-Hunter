from datetime import datetime, timezone

from sqlalchemy.orm import Session

from jobhunter.analytics import outreach_metrics
from jobhunter.db.enums import OutreachMessageStatus, OutreachStatus, OutreachTemplateType
from jobhunter.db.models import OutreachContact, OutreachMessage


def test_get_outreach_performance(session: Session) -> None:
    contact = OutreachContact(
        name="Test Contact",
        company="Test Co",
        status=OutreachStatus.CONTACTED,
    )
    session.add(contact)
    session.flush()

    message = OutreachMessage(
        contact_id=contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        status=OutreachMessageStatus.REPLIED,
        sent_at=datetime.now(timezone.utc),
        replied_at=datetime.now(timezone.utc),
        body="body",
    )
    session.add(message)
    session.commit()

    start_date = datetime(2020, 1, 1, tzinfo=timezone.utc)
    result = outreach_metrics.get_outreach_performance(session, start_date)

    assert result.total_sent == 1
    assert result.total_replied == 1
    assert result.response_rate == 1.0
    assert len(result.template_stats) == 1
    assert result.template_stats[0].template_type == OutreachTemplateType.A_INHOUSE


def test_get_warmest_contacts(session: Session) -> None:
    contact = OutreachContact(
        name="Warm Contact",
        status=OutreachStatus.REPLIED,
        last_contacted_at=datetime.now(timezone.utc),
    )
    session.add(contact)
    session.commit()

    results = outreach_metrics.get_warmest_contacts(session, limit=5)
    assert len(results) == 1
    assert results[0].name == "Warm Contact"
