import pytest
import uuid
from datetime import datetime
from unittest.mock import MagicMock

from jobhunter.db.enums import (
    ApplicationStatus,
    EmailMatchStatus,
)
from jobhunter.db.models import Application, EmailMessage
from jobhunter.email.suggester import (
    StateSuggestion,
    SuggestionStatus,
    _requires_confirmation,
    suggest_state_changes,
)


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock()
    # Mock session.get to return appropriate objects
    return session


def test_requires_confirmation_auto_apply() -> None:
    suggestion = StateSuggestion(
        email_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        current_state=ApplicationStatus.APPLIED,
        suggested_state=ApplicationStatus.SCREENING,
        confidence=0.95,
        status=SuggestionStatus.PENDING,
    )
    # Heuristic match + High Confidence + Positive Transition -> NO confirmation
    assert _requires_confirmation(suggestion, EmailMatchStatus.AUTO_MATCHED) is False


def test_requires_confirmation_low_confidence() -> None:
    suggestion = StateSuggestion(
        email_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        current_state=ApplicationStatus.APPLIED,
        suggested_state=ApplicationStatus.SCREENING,
        confidence=0.85,
        status=SuggestionStatus.PENDING,
    )
    assert _requires_confirmation(suggestion, EmailMatchStatus.AUTO_MATCHED) is True


def test_requires_confirmation_ai_match() -> None:
    suggestion = StateSuggestion(
        email_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        current_state=ApplicationStatus.APPLIED,
        suggested_state=ApplicationStatus.SCREENING,
        confidence=0.95,
        status=SuggestionStatus.PENDING,
    )
    # AI Match always requires confirmation even with high confidence
    assert _requires_confirmation(suggestion, EmailMatchStatus.AI_MATCHED) is True


def test_requires_confirmation_rejected_policy() -> None:
    suggestion = StateSuggestion(
        email_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        current_state=ApplicationStatus.SCREENING,
        suggested_state=ApplicationStatus.REJECTED,
        confidence=0.99,
        status=SuggestionStatus.PENDING,
    )
    # REJECTED always requires confirmation
    assert _requires_confirmation(suggestion, EmailMatchStatus.AUTO_MATCHED) is True


def test_requires_confirmation_offer_policy() -> None:
    suggestion = StateSuggestion(
        email_id=uuid.uuid4(),
        application_id=uuid.uuid4(),
        current_state=ApplicationStatus.INTERVIEW_1,
        suggested_state=ApplicationStatus.OFFER,
        confidence=0.99,
        status=SuggestionStatus.PENDING,
    )
    # OFFER always requires confirmation
    assert _requires_confirmation(suggestion, EmailMatchStatus.AUTO_MATCHED) is True


@pytest.mark.asyncio
async def test_suggest_state_changes_auto_apply_path(mock_session: MagicMock) -> None:
    email_id = uuid.uuid4()
    app_id = uuid.uuid4()

    email = EmailMessage(
        id=email_id,
        gmail_message_id="gmail1",
        received_at=datetime.now(),
        from_email="hr@test.com",
        body_hash="hash1",
        match_status=EmailMatchStatus.AUTO_MATCHED,
        match_confidence=0.95,
        matched_application_id=app_id,
        suggested_status_change={"status": ApplicationStatus.SCREENING},
    )

    app = Application(id=app_id, status=ApplicationStatus.APPLIED)

    mock_session.scalars.return_value.all.return_value = [email]
    mock_session.get.side_effect = lambda model, id: (
        app if model == Application and id == app_id else None
    )

    results = await suggest_state_changes(mock_session)

    assert len(results) == 1
    assert results[0].status == SuggestionStatus.AUTO_APPLIED
    assert app.status == ApplicationStatus.SCREENING
    assert email.suggested_status_change is not None
    assert email.suggested_status_change["suggester_processed"] is True
    assert email.suggested_status_change["suggestion_status"] == SuggestionStatus.AUTO_APPLIED
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_suggest_state_changes_requires_confirm_path(mock_session: MagicMock) -> None:
    email_id = uuid.uuid4()
    app_id = uuid.uuid4()

    email = EmailMessage(
        id=email_id,
        gmail_message_id="gmail2",
        received_at=datetime.now(),
        from_email="hr@test.com",
        body_hash="hash2",
        match_status=EmailMatchStatus.AUTO_MATCHED,
        match_confidence=0.95,
        matched_application_id=app_id,
        suggested_status_change={"status": ApplicationStatus.REJECTED},
    )

    app = Application(id=app_id, status=ApplicationStatus.SCREENING)

    mock_session.scalars.return_value.all.return_value = [email]
    mock_session.get.side_effect = lambda model, id: (
        app if model == Application and id == app_id else None
    )

    results = await suggest_state_changes(mock_session)

    assert len(results) == 1
    assert results[0].status == SuggestionStatus.PENDING
    assert app.status == ApplicationStatus.SCREENING  # No change
    assert email.suggested_status_change is not None
    assert email.suggested_status_change["suggester_processed"] is True
    assert email.suggested_status_change["suggestion_status"] == SuggestionStatus.PENDING


@pytest.mark.asyncio
async def test_suggest_state_changes_idempotency(mock_session: MagicMock) -> None:
    email_id = uuid.uuid4()

    email = EmailMessage(
        id=email_id,
        gmail_message_id="gmail3",
        received_at=datetime.now(),
        from_email="hr@test.com",
        body_hash="hash3",
        match_status=EmailMatchStatus.AUTO_MATCHED,
        match_confidence=0.95,
        suggested_status_change={
            "status": ApplicationStatus.SCREENING,
            "suggester_processed": True,
        },
    )

    mock_session.scalars.return_value.all.return_value = [email]

    results = await suggest_state_changes(mock_session)

    assert len(results) == 0
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_suggest_state_changes_silent_path(mock_session: MagicMock) -> None:
    # confidence < 0.7 are not even queried by the function

    # The SQL query in the function filters this out, but we mock the result of scalars().all()
    mock_session.scalars.return_value.all.return_value = []

    results = await suggest_state_changes(mock_session)
    assert len(results) == 0
