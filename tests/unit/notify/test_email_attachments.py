import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from jobhunter.notify.email import EmailNotifier
from jobhunter.notify.base import NotificationMessage
from jobhunter.config import Settings
from pydantic import SecretStr


@pytest.mark.asyncio
async def test_email_attachments() -> None:
    notifier = EmailNotifier()

    # Mock settings
    mock_settings = MagicMock(spec=Settings)
    mock_settings.SMTP_USER = "user@example.com"
    mock_settings.SMTP_PASSWORD = SecretStr("password")  # pragma: allowlist secret
    mock_settings.DIGEST_TO_EMAIL = "recipient@example.com"
    mock_settings.SMTP_HOST = "localhost"
    mock_settings.SMTP_PORT = 587

    with patch.object(EmailNotifier, "_get_settings", return_value=mock_settings):
        with patch("aiosmtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=None)
            instance.starttls = AsyncMock()
            instance.login = AsyncMock()
            instance.send_message = AsyncMock()

            msg = NotificationMessage(
                channel="email",
                subject="Test Subject",
                body_text="Test Body",
                attachments=[{"filename": "test.txt", "content": b"Hello World"}],
            )

            result = await notifier.send(msg)
            assert result.success, f"Send failed: {result.error}"

            # Verify send_message was called with a message containing attachments
            args, kwargs = instance.send_message.call_args
            sent_msg = args[0]

            assert sent_msg["Subject"] == "Test Subject"
            assert sent_msg.is_multipart()

            parts = list(sent_msg.walk())
            # mixed -> alternative -> text, mixed -> application
            filenames = [p.get_filename() for p in parts if p.get_filename()]
            assert "test.txt" in filenames

            print("Email with attachments test passed!")
