import asyncio
import time
from datetime import timedelta

import structlog
from telegram import Bot
from telegram.error import BadRequest, NetworkError, RetryAfter

from jobhunter.config import Settings
from jobhunter.notify.base import (
    BaseNotifier,
    NotificationMessage,
    NotificationResult,
    register_notifier,
)
from jobhunter.notify.templates import escape_telegram_markdown

logger = structlog.get_logger()


def escape_telegram_markdown_v2(text: str) -> str:
    """
    Helper to escape characters for Telegram MarkdownV2.
    Delegates to the central template filter for consistency.
    """
    return escape_telegram_markdown(text)


@register_notifier("telegram")
class TelegramNotifier(BaseNotifier):
    """
    Notifier implementation for Telegram.
    """

    @property
    def name(self) -> str:
        return "telegram"

    def is_enabled(self, settings: Settings) -> bool:
        """
        Checks if Telegram notifications are enabled.
        """
        return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """
        Sends a notification via Telegram.

        Args:
            message: The NotificationMessage to send.

        Returns:
            NotificationResult: Result of the attempt.
        """
        # Call a helper to get settings to make it easier to mock
        settings = self._get_settings()

        if not self.is_enabled(settings):
            return NotificationResult(
                success=False,
                error="Telegram notifier is not enabled (missing token or chat_id)",
                duration_ms=0,
            )

        token = settings.TELEGRAM_BOT_TOKEN.get_secret_value() if settings.TELEGRAM_BOT_TOKEN else ""
        chat_id = settings.TELEGRAM_CHAT_ID or ""

        bot = Bot(token=token)

        # Telegram message limit is 4096 characters.
        # We escape first, then truncate.
        text = escape_telegram_markdown_v2(message.body_text)

        if len(text) > 4096:
            text = text[:4095]
            # Ensure we don't end with a trailing backslash that would break escaping
            if text.endswith("\\"):
                text = text[:-1]
            text += "…"

        start_time = time.perf_counter()

        try:
            return await self._send_with_retry(bot, chat_id, text, start_time)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Unexpected error sending Telegram message", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                duration_ms=duration_ms,
            )

    def _get_settings(self) -> Settings:
        """Helper to get application settings."""
        return Settings()  # type: ignore[call-arg]

    async def _send_with_retry(
        self, bot: Bot, chat_id: str, text: str, start_time: float, retry_count: int = 0
    ) -> NotificationResult:
        """
        Internal helper to send message with one retry for RetryAfter.
        """
        try:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return NotificationResult(
                success=True,
                provider_message_id=str(sent_message.message_id),
                duration_ms=duration_ms,
            )
        except RetryAfter as e:
            if retry_count < 1:
                logger.warning("Telegram rate limited, retrying", retry_after=e.retry_after)
                # Handle both int and timedelta for sleep
                delay = (
                    e.retry_after.total_seconds()
                    if isinstance(e.retry_after, timedelta)
                    else float(e.retry_after)
                )
                await asyncio.sleep(delay)
                return await self._send_with_retry(bot, chat_id, text, start_time, retry_count + 1)
            else:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                logger.error("Telegram rate limited, no more retries", retry_after=e.retry_after)
                return NotificationResult(
                    success=False,
                    error=f"Rate limited: {str(e)}",
                    duration_ms=duration_ms,
                )
        except BadRequest as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Telegram BadRequest (possibly malformed MarkdownV2)", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Bad request: {str(e)}",
                duration_ms=duration_ms,
            )
        except NetworkError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Telegram NetworkError", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Network error: {str(e)}",
                duration_ms=duration_ms,
            )
