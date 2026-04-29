import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import structlog

from jobhunter.config import Settings
from jobhunter.notify.base import (
    BaseNotifier,
    NotificationMessage,
    NotificationResult,
    register_notifier,
)

logger = structlog.get_logger()


@register_notifier("email")
class EmailNotifier(BaseNotifier):
    """
    Notifier implementation for Email (SMTP).
    """

    @property
    def name(self) -> str:
        return "email"

    def is_enabled(self, settings: Settings) -> bool:
        """
        Checks if Email notifications are enabled.
        """
        return bool(settings.SMTP_USER and settings.SMTP_PASSWORD and settings.DIGEST_TO_EMAIL)

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """
        Sends a notification via Email.

        Args:
            message: The NotificationMessage to send.

        Returns:
            NotificationResult: Result of the attempt.
        """
        settings = self._get_settings()

        if not self.is_enabled(settings):
            return NotificationResult(
                success=False,
                error="Email notifier is not enabled (missing SMTP credentials or recipient email)",
                duration_ms=0,
            )

        start_time = time.perf_counter()

        try:
            # Create the root message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject or "Job Hunter Notification"
            msg["From"] = settings.SMTP_USER
            msg["To"] = settings.DIGEST_TO_EMAIL

            # Attach plain text body
            msg.attach(MIMEText(message.body_text, "plain"))

            # Attach HTML body if available
            if message.body_html:
                msg.attach(MIMEText(message.body_html, "html"))

            # Connect and send
            smtp_client = aiosmtplib.SMTP(
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                use_tls=settings.SMTP_PORT == 465,
            )

            async with smtp_client:
                if settings.SMTP_PORT == 587:
                    await smtp_client.starttls()

                password = (
                    settings.SMTP_PASSWORD.get_secret_value() if settings.SMTP_PASSWORD else ""
                )
                await smtp_client.login(settings.SMTP_USER, password)  # type: ignore[arg-type]
                await smtp_client.send_message(msg)

            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return NotificationResult(
                success=True,
                duration_ms=duration_ms,
            )

        except aiosmtplib.SMTPAuthenticationError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("SMTP authentication failed", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Authentication error: {str(e)}",
                duration_ms=duration_ms,
            )
        except aiosmtplib.SMTPException as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("SMTP error sending email", error=str(e))
            return NotificationResult(
                success=False,
                error=f"SMTP error: {str(e)}",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Unexpected error sending email", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                duration_ms=duration_ms,
            )

    def _get_settings(self) -> Settings:
        """Helper to get application settings."""
        return Settings()  # type: ignore[call-arg]
