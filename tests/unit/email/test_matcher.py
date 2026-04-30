import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from jobhunter.db.enums import ApplicationStatus, EmailMatchStatus, OutreachMessageStatus
from jobhunter.db.models import Application, Job, OutreachContact, OutreachMessage
from jobhunter.email.matcher import match_email
from jobhunter.email.schemas import GmailMessageDetail


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_match_email_marketing(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    email = GmailMessageDetail(
        id="msg1",
        threadId="thread1",
        received_at=datetime.now(),
        from_email="newsletter@company.com",
        subject="Our Weekly Newsletter",
        snippet="Check out our latest updates!",
        body_text="If you want to stop receiving these emails, please unsubscribe here.",
    )

    result = await match_email(email, mock_session, mock_llm_client)

    assert result.match_status == EmailMatchStatus.IGNORED_MARKETING
    assert result.confidence == 1.0
    mock_llm_client.complete.assert_not_called()


@pytest.mark.asyncio
async def test_match_email_heuristic_application(
    mock_session: MagicMock, mock_llm_client: MagicMock
) -> None:
    email = GmailMessageDetail(
        id="msg2",
        threadId="thread2",
        received_at=datetime.now(),
        from_email="hr@techcorp.com",
        subject="Re: Your application at TechCorp",
        snippet="We'd like to invite you for an interview.",
        body_text="Hi, we saw your application and would like to schedule a call.",
    )

    # Mock DB response for Heuristic 1
    job = Job(company="TechCorp", title="Software Engineer")
    import uuid

    app_id = uuid.uuid4()
    app = Application(id=app_id, job=job, contact_email="hr@techcorp.com")

    mock_session.scalars.return_value.all.side_effect = [[app], []]  # apps, contacts

    result = await match_email(email, mock_session, mock_llm_client)

    assert result.match_status == EmailMatchStatus.AUTO_MATCHED
    assert result.application_id == app_id
    assert result.confidence == 0.95  # 0.9 + subject match
    assert (
        result.suggested_change and result.suggested_change["status"] == ApplicationStatus.SCREENING
    )
    mock_llm_client.complete.assert_not_called()


@pytest.mark.asyncio
async def test_match_email_rejection(mock_session: MagicMock, mock_llm_client: MagicMock) -> None:
    email = GmailMessageDetail(
        id="msg3",
        threadId="thread3",
        received_at=datetime.now(),
        from_email="talent@startup.io",
        subject="Update on your application",
        snippet="Thank you for your interest, but...",
        body_text="We have decided to move forward with other candidates.",
    )

    import uuid

    job = Job(company="Startup IO", title="Backend Dev")
    app = Application(id=uuid.uuid4(), job=job, contact_email="talent@startup.io")

    mock_session.scalars.return_value.all.side_effect = [[app], []]

    result = await match_email(email, mock_session, mock_llm_client)

    assert (
        result.suggested_change and result.suggested_change["status"] == ApplicationStatus.REJECTED
    )


@pytest.mark.asyncio
async def test_match_email_outreach_reply(
    mock_session: MagicMock, mock_llm_client: MagicMock
) -> None:
    email = GmailMessageDetail(
        id="msg4",
        threadId="thread4",
        received_at=datetime.now(),
        from_email="ceo@target.com",
        subject="Re: Inquiry about engineering roles",
        snippet="Thanks for reaching out, let's chat.",
        body_text="Hi Jules, thanks for your message. I'm interested.",
    )

    import uuid

    contact_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    contact = OutreachContact(
        id=contact_id, name="John Doe", company="Target Corp", email="ceo@target.com"
    )
    message = OutreachMessage(id=msg_id, contact_id=contact.id, status=OutreachMessageStatus.SENT)

    mock_session.scalars.return_value.all.side_effect = [[], [contact]]  # apps, contacts
    mock_session.scalar.return_value = message  # latest outreach message

    result = await match_email(email, mock_session, mock_llm_client)

    assert result.match_status == EmailMatchStatus.AUTO_MATCHED
    assert result.outreach_message_id == message.id
    assert (
        result.suggested_change
        and result.suggested_change["status"] == OutreachMessageStatus.REPLIED
    )


@pytest.mark.asyncio
async def test_match_email_ai_escalation(
    mock_session: MagicMock, mock_llm_client: MagicMock
) -> None:
    email = GmailMessageDetail(
        id="msg5",
        threadId="thread5",
        received_at=datetime.now(),
        from_email="ambiguous@service.com",
        subject="Quick question",
        snippet="Is this still available?",
        body_text="Hello, I wanted to follow up on our previous conversation.",
    )

    # Mock no heuristic matches
    mock_session.scalars.return_value.all.side_effect = [
        [],
        [],  # Heuristic 1: apps, contacts
        [],
        [],  # AI context: candidate apps, candidate contacts
    ]

    # Mock AI response
    import json
    import uuid

    target_app_id = str(uuid.uuid4())
    mock_llm_client.complete.return_value = MagicMock(
        text=json.dumps(
            {
                "match_status": "ai_matched",
                "application_id": target_app_id,
                "outreach_contact_id": None,
                "confidence": 0.85,
                "reasoning": "AI logic matched the company name mentioned in thread history.",
            }
        ),
        model="claude-3-haiku-20240307",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=500,
    )

    result = await match_email(email, mock_session, mock_llm_client)

    assert result.match_status == EmailMatchStatus.AI_MATCHED
    assert str(result.application_id) == target_app_id
    assert result.confidence == 0.85
    mock_llm_client.complete.assert_called_once()
