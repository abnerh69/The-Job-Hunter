from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr
from telegram.error import BadRequest, NetworkError, RetryAfter

from jobhunter.config import Settings
from jobhunter.notify.base import NotificationMessage
from jobhunter.notify.telegram import TelegramNotifier, escape_telegram_markdown_v2


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
    # Mock _get_settings to return our test settings
    n._get_settings = MagicMock(return_value=settings_mock)  # type: ignore[method-assign]
    return n


def test_is_enabled(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    assert notifier.is_enabled(settings_mock) is True

    settings_disabled = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        TELEGRAM_BOT_TOKEN=None,
        TELEGRAM_CHAT_ID=None,
    )
    assert notifier.is_enabled(settings_disabled) is False


def test_escape_telegram_markdown_v2() -> None:
    input_text = "Salary: $5,500. Apply!"
    # The current implementation DOES NOT escape '$' as it's not in the list
    # List: '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'
    expected = "Salary: $5,500\\. Apply\\!"
    assert escape_telegram_markdown_v2(input_text) == expected


@pytest.mark.asyncio
async def test_send_success(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.return_value.message_id = 123

        msg = NotificationMessage(channel="telegram", body_text="Hello. World!")
        result = await notifier.send(msg)

        assert result.success is True
        assert result.provider_message_id == "123"
        # Verify it was escaped
        mock_bot_instance.send_message.assert_called_once_with(
            chat_id="chat_id", text="Hello\\. World\\!", parse_mode="MarkdownV2", reply_markup=None
        )


@pytest.mark.asyncio
async def test_send_retry_after(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    with (
        patch("jobhunter.notify.telegram.Bot") as MockBot,
        patch("jobhunter.notify.telegram.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()

        # First call raises RetryAfter, second call succeeds
        mock_bot_instance.send_message.side_effect = [
            RetryAfter(retry_after=5),
            MagicMock(message_id=456),
        ]

        msg = NotificationMessage(channel="telegram", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is True
        assert result.provider_message_id == "456"
        assert mock_bot_instance.send_message.call_count == 2
        mock_sleep.assert_called_once_with(5.0)


@pytest.mark.asyncio
async def test_send_retry_after_exhausted(
    notifier: TelegramNotifier, settings_mock: Settings
) -> None:
    with (
        patch("jobhunter.notify.telegram.Bot") as MockBot,
        patch("jobhunter.notify.telegram.asyncio.sleep", AsyncMock()) as mock_sleep,
    ):
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()

        # Always raises RetryAfter
        mock_bot_instance.send_message.side_effect = RetryAfter(retry_after=5)

        msg = NotificationMessage(channel="telegram", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is False
        assert "Rate limited" in (result.error or "")
        assert mock_bot_instance.send_message.call_count == 2  # 1 initial + 1 retry
        assert mock_sleep.call_count == 1


@pytest.mark.asyncio
async def test_send_bad_request(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.side_effect = BadRequest("Malformed")

        msg = NotificationMessage(channel="telegram", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is False
        assert "Bad request" in (result.error or "")


@pytest.mark.asyncio
async def test_send_network_error(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.side_effect = NetworkError("Timeout")

        msg = NotificationMessage(channel="telegram", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is False
        assert "Network error" in (result.error or "")


@pytest.mark.asyncio
async def test_truncation(notifier: TelegramNotifier, settings_mock: Settings) -> None:
    long_text = "A" * 5000
    msg = NotificationMessage(channel="telegram", body_text=long_text)

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.return_value.message_id = 999

        await notifier.send(msg)

        _args, kwargs = mock_bot_instance.send_message.call_args
        sent_text = kwargs["text"]
        assert len(sent_text) == 4096
        assert sent_text.endswith("…")


@pytest.mark.asyncio
async def test_truncation_escaping_boundary(
    notifier: TelegramNotifier, settings_mock: Settings
) -> None:
    # A text where truncation would leave a trailing backslash
    body = "A" * 4094 + "."  # Escaped: A...A\. (len 4096)
    # If we had "A" * 4095 + "." -> Escaped: A...A\. (len 4097) -> truncated to 4095: A...A\
    body = "A" * 4095 + "."
    msg = NotificationMessage(channel="telegram", body_text=body)

    with patch("jobhunter.notify.telegram.Bot") as MockBot:
        mock_bot_instance = MockBot.return_value
        mock_bot_instance.send_message = AsyncMock()
        mock_bot_instance.send_message.return_value.message_id = 999

        await notifier.send(msg)

        _args, kwargs = mock_bot_instance.send_message.call_args
        sent_text = kwargs["text"]
        assert len(sent_text) <= 4096
        assert not sent_text.endswith("\\…")
        assert sent_text.endswith("A…")
