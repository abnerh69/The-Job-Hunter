import uuid
from datetime import datetime, timezone
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from telegram import Message, Update, CallbackQuery

from jobhunter.config import Settings
from jobhunter.db.base import Base
from jobhunter.db.enums import ApplicationStatus, EmailMatchStatus
from jobhunter.db.models import Application, EmailMessage, Job
from jobhunter.notify.base import NotificationMessage
from jobhunter.notify.telegram import Button, TelegramNotifier


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def settings_mock() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        TELEGRAM_BOT_TOKEN=SecretStr("bot_token"),
        TELEGRAM_CHAT_ID="chat_id",
    )


@pytest.fixture
def notifier(settings_mock: Settings) -> TelegramNotifier:
    n = TelegramNotifier()
    n._get_settings = MagicMock(return_value=settings_mock)  # type: ignore[method-assign]
    return n


@pytest.mark.asyncio
async def test_send_with_buttons(notifier: TelegramNotifier) -> None:
    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.return_value.message_id = 123

        msg = NotificationMessage(channel="telegram", body_text="Hello with buttons")
        buttons = [
            Button(text="Approve", callback_data="approve:123"),
            Button(text="Reject", callback_data="reject:123"),
        ]

        result = await notifier.send_with_buttons(msg, buttons)

        assert result.success is True
        assert result.provider_message_id == "123"

        # Verify reply_markup
        _args, kwargs = mock_bot_instance.send_message.call_args
        reply_markup = kwargs["reply_markup"]
        assert len(reply_markup.inline_keyboard[0]) == 2
        assert reply_markup.inline_keyboard[0][0].text == "Approve"
        assert reply_markup.inline_keyboard[0][0].callback_data == "approve:123"


@pytest.mark.asyncio
async def test_process_callback_updates_approve_app(
    notifier: TelegramNotifier, test_db: Session
) -> None:
    # 1. Setup DB
    job = Job(
        title="Dev",
        company="Tech",
        description="...",
        url="http://tech.dev",
        url_hash="123",
        source="linkedin",
    )
    test_db.add(job)
    test_db.flush()

    app = Application(job_id=job.id, status=ApplicationStatus.APPLIED)
    test_db.add(app)
    test_db.flush()

    email_id = uuid.uuid4()
    email_msg = EmailMessage(
        id=email_id,
        gmail_message_id="msg_123",
        received_at=datetime.now(timezone.utc),
        from_email="hr@tech.dev",
        body_hash="abc",
        match_status=EmailMatchStatus.AUTO_MATCHED,
        matched_application_id=app.id,
        suggested_status_change={"status": ApplicationStatus.SCREENING},
    )
    test_db.add(email_msg)
    test_db.commit()

    # 2. Mock Telegram Update
    mock_update = MagicMock(spec=Update)
    mock_query = MagicMock(spec=CallbackQuery)
    mock_message = MagicMock(spec=Message)

    mock_update.callback_query = mock_query
    mock_query.data = f"approve:{email_id}"
    mock_query.message = mock_message
    mock_query.id = "query_id_123"

    mock_message.chat_id = 999
    mock_message.message_id = 888

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.get_updates = AsyncMock(return_value=[mock_update])
        mock_bot_instance.answer_callback_query = AsyncMock()
        mock_bot_instance.edit_message_text = AsyncMock()

        # 3. Process
        count = await notifier.process_callback_updates(test_db)

        assert count == 1
        test_db.refresh(app)
        test_db.refresh(email_msg)

        # 4. Assertions
        assert app.status == ApplicationStatus.SCREENING
        assert email_msg.match_status == EmailMatchStatus.USER_CONFIRMED
        mock_bot_instance.edit_message_text.assert_called_once()
        assert "Aplicado" in mock_bot_instance.edit_message_text.call_args[1]["text"]


@pytest.mark.asyncio
async def test_process_callback_updates_reject(
    notifier: TelegramNotifier, test_db: Session
) -> None:
    # 1. Setup DB
    email_id = uuid.uuid4()
    email_msg = EmailMessage(
        id=email_id,
        gmail_message_id="msg_123",
        received_at=datetime.now(timezone.utc),
        from_email="hr@tech.dev",
        body_hash="abc",
        match_status=EmailMatchStatus.AI_MATCHED,
    )
    test_db.add(email_msg)
    test_db.commit()

    # 2. Mock Telegram Update
    mock_update = MagicMock(spec=Update)
    mock_query = MagicMock(spec=CallbackQuery)
    mock_message = MagicMock(spec=Message)

    mock_update.callback_query = mock_query
    mock_query.data = f"reject:{email_id}"
    mock_query.message = mock_message

    mock_message.chat_id = 999
    mock_message.message_id = 888

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.get_updates = AsyncMock(return_value=[mock_update])
        mock_bot_instance.answer_callback_query = AsyncMock()
        mock_bot_instance.edit_message_text = AsyncMock()

        # 3. Process
        await notifier.process_callback_updates(test_db)

        test_db.refresh(email_msg)

        # 4. Assertions
        assert email_msg.match_status == EmailMatchStatus.USER_REJECTED
        mock_bot_instance.edit_message_text.assert_called_once_with(
            chat_id=999, message_id=888, text="❌ Rechazado", parse_mode="MarkdownV2"
        )


@pytest.mark.asyncio
async def test_process_callback_idempotency(notifier: TelegramNotifier, test_db: Session) -> None:
    # 1. Setup DB with already confirmed status
    email_id = uuid.uuid4()
    email_msg = EmailMessage(
        id=email_id,
        gmail_message_id="msg_123",
        received_at=datetime.now(timezone.utc),
        from_email="hr@tech.dev",
        body_hash="abc",
        match_status=EmailMatchStatus.USER_CONFIRMED,
    )
    test_db.add(email_msg)
    test_db.commit()

    # 2. Mock Telegram Update
    mock_update = MagicMock(spec=Update)
    mock_query = MagicMock(spec=CallbackQuery)
    mock_message = MagicMock(spec=Message)

    mock_update.callback_query = mock_query
    mock_query.data = f"approve:{email_id}"
    mock_query.message = mock_message

    mock_message.text_markdown_v2 = "Original Text"

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.get_updates = AsyncMock(return_value=[mock_update])
        mock_bot_instance.edit_message_text = AsyncMock()

        # 3. Process
        await notifier.process_callback_updates(test_db)

        # 4. Assertions
        # Should call edit_message_text with "Already processed"
        args, kwargs = mock_bot_instance.edit_message_text.call_args
        assert "Already processed" in kwargs["text"]


@pytest.mark.asyncio
async def test_handle_context(notifier: TelegramNotifier, test_db: Session) -> None:
    # 1. Setup DB
    email_id = uuid.uuid4()
    email_msg = EmailMessage(
        id=email_id,
        gmail_message_id="msg_123",
        received_at=datetime.now(timezone.utc),
        from_email="hr@tech.dev",
        body_hash="abc",
        match_reasoning="Because of domain",
        snippet="Hi there...",
    )
    test_db.add(email_msg)
    test_db.commit()

    # 2. Mock Telegram Update
    mock_update = MagicMock(spec=Update)
    mock_query = MagicMock(spec=CallbackQuery)
    mock_message = MagicMock(spec=Message)

    mock_update.callback_query = mock_query
    mock_query.data = f"context:{email_id}"
    mock_query.message = mock_message

    mock_message.chat_id = 999

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.get_updates = AsyncMock(return_value=[mock_update])
        mock_bot_instance.send_message = AsyncMock()

        # 3. Process
        await notifier.process_callback_updates(test_db)

        # 4. Assertions
        # Should send a new message with reasoning and snippet
        args, kwargs = mock_bot_instance.send_message.call_args
        assert "Because of domain" in kwargs["text"]
        assert "Hi there\\.\\.\\." in kwargs["text"]
        assert kwargs["parse_mode"] == "MarkdownV2"
