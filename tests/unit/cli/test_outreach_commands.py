import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from jobhunter.__main__ import app
from jobhunter.db.enums import OutreachStatus, OutreachTemplateType, OutreachMessageStatus
from jobhunter.db.models import OutreachContact, OutreachMessage

runner = CliRunner()


@pytest.fixture
def mock_session() -> Generator[MagicMock, None, None]:
    with patch("jobhunter.__main__.get_session") as mock:
        session = MagicMock()
        mock.return_value.__enter__.return_value = session
        yield session


def test_outreach_add_success(mock_session: MagicMock) -> None:
    """Test successful manual addition of an outreach contact."""
    mock_repo = MagicMock()
    mock_repo.find_by_linkedin_url.return_value = None

    with patch("jobhunter.__main__.OutreachRepo", return_value=mock_repo):
        result = runner.invoke(
            app,
            [
                "outreach",
                "add",
                "--name",
                "John Doe",
                "--linkedin-url",
                "https://linkedin.com/in/johndoe",
                "--company",
                "ACME Corp",
                "--role",
                "CTO",
                "--market",
                "germany",
            ],
        )

        assert result.exit_code == 0
        assert "Contact Created" in result.output
        assert "John Doe" in result.output
        assert "ACME Corp" in result.output
        mock_session.add.assert_called()
        mock_session.commit.assert_called()


def test_outreach_add_duplicate(mock_session: MagicMock) -> None:
    """Test error when adding a contact with an existing LinkedIn URL."""
    mock_repo = MagicMock()
    mock_repo.find_by_linkedin_url.return_value = OutreachContact(name="Existing")

    with patch("jobhunter.__main__.OutreachRepo", return_value=mock_repo):
        result = runner.invoke(
            app,
            [
                "outreach",
                "add",
                "--name",
                "John Doe",
                "--linkedin-url",
                "https://linkedin.com/in/existing",
            ],
        )

        assert result.exit_code == 1
        assert "already exists" in result.output


def test_outreach_candidates(mock_session: MagicMock) -> None:
    """Test listing prioritized candidates."""
    contacts = [
        OutreachContact(id=uuid.uuid4(), name="Alice", quality_score=5, status=OutreachStatus.NEW),
        OutreachContact(id=uuid.uuid4(), name="Bob", quality_score=4, status=OutreachStatus.NEW),
    ]
    mock_session.scalars.return_value.all.return_value = contacts

    result = runner.invoke(app, ["outreach", "candidates", "--limit", "5"])

    assert result.exit_code == 0
    assert "Outreach Candidates" in result.output
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_outreach_draft_success(mock_session: MagicMock) -> None:
    """Test successful draft generation."""
    contact_id = uuid.uuid4()
    contact = OutreachContact(id=contact_id, name="John Doe")
    mock_session.get.return_value = contact

    message = OutreachMessage(
        id=uuid.uuid4(),
        contact_id=contact_id,
        body="Hello John, I saw your post about AI...",
        status=OutreachMessageStatus.DRAFT,
    )

    with (
        patch("jobhunter.__main__.AnthropicLLMClient"),
        patch("jobhunter.__main__.asyncio.run", return_value=message),
    ):
        result = runner.invoke(
            app,
            [
                "outreach",
                "draft",
                str(contact_id),
                "--type",
                "A_inhouse",
                "--note",
                "Saw your recent post about LLM scaling and was impressed.",
            ],
        )

        assert result.exit_code == 0
        assert "Generated Message for John Doe" in result.output
        assert "Hello John" in result.output


def test_outreach_draft_note_too_short() -> None:
    """Test draft generation error when note is too short."""
    result = runner.invoke(
        app, ["outreach", "draft", str(uuid.uuid4()), "--type", "A_inhouse", "--note", "Too short"]
    )

    assert result.exit_code == 1
    assert "at least 20 characters long" in result.output


def test_outreach_sent_success(mock_session: MagicMock) -> None:
    """Test marking a message as sent."""
    message_id = uuid.uuid4()
    message = OutreachMessage(id=message_id, status=OutreachMessageStatus.DRAFT)

    mock_repo = MagicMock()
    mock_repo.get.return_value = message

    with patch("jobhunter.__main__.OutreachMessageRepo", return_value=mock_repo):
        result = runner.invoke(app, ["outreach", "sent", str(message_id)])

        assert result.exit_code == 0
        assert "marked as SENT" in result.output
        mock_repo.mark_sent.assert_called_once_with(message_id, sent_at=None)
        mock_session.commit.assert_called()


def test_outreach_replied_success(mock_session: MagicMock) -> None:
    """Test marking a message as replied."""
    message_id = uuid.uuid4()
    message = OutreachMessage(id=message_id, status=OutreachMessageStatus.SENT)

    mock_repo = MagicMock()
    mock_repo.get.return_value = message

    with patch("jobhunter.__main__.OutreachMessageRepo", return_value=mock_repo):
        result = runner.invoke(app, ["outreach", "replied", str(message_id)])

        assert result.exit_code == 0
        assert "marked as REPLIED" in result.output
        mock_repo.mark_replied.assert_called_once_with(message_id, replied_at=None)
        mock_session.commit.assert_called()


def test_outreach_list(mock_session: MagicMock) -> None:
    """Test listing outreach messages."""
    contact = OutreachContact(name="John")
    messages = [
        OutreachMessage(
            id=uuid.uuid4(),
            contact=contact,
            template_type=OutreachTemplateType.A_INHOUSE,
            status=OutreachMessageStatus.SENT,
            created_at=datetime.now(timezone.utc),
        )
    ]
    mock_session.scalars.return_value.all.return_value = messages

    result = runner.invoke(app, ["outreach", "list", "--status", "sent"])

    assert result.exit_code == 0
    assert "Outreach Messages" in result.output
    assert "John" in result.output
    assert "sent" in result.output
