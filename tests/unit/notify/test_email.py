from unittest.mock import AsyncMock, MagicMock, patch

import aiosmtplib
import pytest
from pydantic import SecretStr

from jobhunter.config import Settings
from jobhunter.notify.base import NotificationMessage
from jobhunter.notify.email import EmailNotifier


@pytest.fixture
def settings_mock() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        SMTP_USER="user@example.com",
        SMTP_PASSWORD=SecretStr("password"),
        DIGEST_TO_EMAIL="recipient@example.com",
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
    )


@pytest.fixture
def notifier(settings_mock: Settings) -> EmailNotifier:
    n = EmailNotifier()
    # Mock _get_settings to return our test settings
    n._get_settings = MagicMock(return_value=settings_mock)  # type: ignore[method-assign]
    return n


def test_is_enabled(notifier: EmailNotifier, settings_mock: Settings) -> None:
    assert notifier.is_enabled(settings_mock) is True

    settings_disabled = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        SMTP_USER=None,
        SMTP_PASSWORD=None,
        DIGEST_TO_EMAIL=None,
    )
    assert notifier.is_enabled(settings_disabled) is False


@pytest.mark.asyncio
async def test_send_success(notifier: EmailNotifier, settings_mock: Settings) -> None:
    with patch("aiosmtplib.SMTP") as MockSMTP:
        mock_smtp_instance = MockSMTP.return_value
        mock_smtp_instance.__aenter__.return_value = mock_smtp_instance
        mock_smtp_instance.starttls = AsyncMock()
        mock_smtp_instance.login = AsyncMock()
        mock_smtp_instance.send_message = AsyncMock()

        msg = NotificationMessage(
            channel="email",
            subject="Test Subject",
            body_text="Hello Text",
            body_html="<h1>Hello HTML</h1>",
        )
        result = await notifier.send(msg)

        assert result.success is True
        assert mock_smtp_instance.login.called
        assert mock_smtp_instance.send_message.called

        # Verify call arguments for send_message
        args, _ = mock_smtp_instance.send_message.call_args
        mime_msg = args[0]
        assert mime_msg["Subject"] == "Test Subject"
        assert mime_msg["From"] == "user@example.com"
        assert mime_msg["To"] == "recipient@example.com"

        # Verify it is multipart/alternative
        assert mime_msg.is_multipart()
        payload = mime_msg.get_payload()
        assert len(payload) == 2
        assert payload[0].get_content_type() == "text/plain"
        assert payload[1].get_content_type() == "text/html"


@pytest.mark.asyncio
async def test_send_auth_error(notifier: EmailNotifier, settings_mock: Settings) -> None:
    with patch("aiosmtplib.SMTP") as MockSMTP:
        mock_smtp_instance = MockSMTP.return_value
        mock_smtp_instance.__aenter__.return_value = mock_smtp_instance
        mock_smtp_instance.starttls = AsyncMock()
        mock_smtp_instance.login = AsyncMock(
            side_effect=aiosmtplib.SMTPAuthenticationError(535, "Auth failed")
        )

        msg = NotificationMessage(channel="email", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is False
        assert "Authentication error" in (result.error or "")


@pytest.mark.asyncio
async def test_send_smtp_error(notifier: EmailNotifier, settings_mock: Settings) -> None:
    with patch("aiosmtplib.SMTP") as MockSMTP:
        mock_smtp_instance = MockSMTP.return_value
        mock_smtp_instance.__aenter__.return_value = mock_smtp_instance
        mock_smtp_instance.starttls = AsyncMock()
        mock_smtp_instance.login = AsyncMock()
        mock_smtp_instance.send_message = AsyncMock(
            side_effect=aiosmtplib.SMTPException("Connection lost")
        )

        msg = NotificationMessage(channel="email", body_text="Hello")
        result = await notifier.send(msg)

        assert result.success is False
        assert "SMTP error" in (result.error or "")


@pytest.mark.asyncio
async def test_send_no_html(notifier: EmailNotifier, settings_mock: Settings) -> None:
    with patch("aiosmtplib.SMTP") as MockSMTP:
        mock_smtp_instance = MockSMTP.return_value
        mock_smtp_instance.__aenter__.return_value = mock_smtp_instance
        mock_smtp_instance.starttls = AsyncMock()
        mock_smtp_instance.login = AsyncMock()
        mock_smtp_instance.send_message = AsyncMock()

        msg = NotificationMessage(channel="email", body_text="Plain text only")
        result = await notifier.send(msg)

        assert result.success is True
        args, _ = mock_smtp_instance.send_message.call_args
        mime_msg = args[0]

        # Even if only text is provided, we use MIMEMultipart("alternative") in current impl
        # but it will only have 1 part if body_html is None
        payload = mime_msg.get_payload()
        assert len(payload) == 1
        assert payload[0].get_content_type() == "text/plain"
