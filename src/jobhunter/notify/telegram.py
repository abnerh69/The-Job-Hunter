import asyncio
import time
from datetime import timedelta
from typing import Sequence
from uuid import UUID

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.error import BadRequest, NetworkError, RetryAfter

from jobhunter.config import Settings
from jobhunter.db.enums import EmailMatchStatus
from jobhunter.db.models import Application, EmailMessage, OutreachMessage
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


class Button(BaseModel):
    """
    Model representing an inline button for Telegram.
    """

    text: str
    callback_data: str


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
        """
        return await self.send_with_buttons(message, [])

    async def send_with_buttons(
        self, message: NotificationMessage, buttons: Sequence[Button]
    ) -> NotificationResult:
        """
        Sends a notification via Telegram with optional inline buttons.

        Args:
            message: The NotificationMessage to send.
            buttons: List of Button objects.

        Returns:
            NotificationResult: Result of the attempt.
        """
        settings = self._get_settings()

        if not self.is_enabled(settings):
            return NotificationResult(
                success=False,
                error="Telegram notifier is not enabled (missing token or chat_id)",
                duration_ms=0,
            )

        token = (
            settings.TELEGRAM_BOT_TOKEN.get_secret_value() if settings.TELEGRAM_BOT_TOKEN else ""
        )
        chat_id = settings.TELEGRAM_CHAT_ID or ""

        bot = Bot(token=token)

        text = escape_telegram_markdown_v2(message.body_text)

        if len(text) > 4096:
            text = text[:4095]
            if text.endswith("\\"):
                text = text[:-1]
            text += "…"

        reply_markup = None
        if buttons:
            keyboard = [
                [InlineKeyboardButton(btn.text, callback_data=btn.callback_data) for btn in buttons]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

        start_time = time.perf_counter()

        try:
            return await self._send_with_retry(bot, chat_id, text, start_time, reply_markup)
        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            logger.error("Unexpected error sending Telegram message", error=str(e))
            return NotificationResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                duration_ms=duration_ms,
            )

    async def process_callback_updates(self, session: Session) -> int:
        """
        Fetches updates from Telegram and processes callback queries.

        Args:
            session: SQLAlchemy session.

        Returns:
            int: Number of handled updates.
        """
        settings = self._get_settings()
        if not self.is_enabled(settings):
            return 0

        token = (
            settings.TELEGRAM_BOT_TOKEN.get_secret_value() if settings.TELEGRAM_BOT_TOKEN else ""
        )
        bot = Bot(token=token)

        try:
            updates = await bot.get_updates(allowed_updates=["callback_query"])
            handled_count = 0
            for update in updates:
                if update.callback_query:
                    await self._handle_callback(bot, update, session)
                    try:
                        await bot.answer_callback_query(callback_query_id=update.callback_query.id)
                    except Exception as e:
                        logger.warning("failed_to_answer_callback", error=str(e))
                    handled_count += 1

            if updates:
                last_id = updates[-1].update_id
                await bot.get_updates(offset=last_id + 1)

            return handled_count
        except Exception as e:
            logger.error("error_processing_telegram_callbacks", error=str(e))
            return 0

    async def _handle_callback(self, bot: Bot, update: Update, session: Session) -> None:
        """
        Routes and executes actions based on callback data.
        """
        query = update.callback_query
        if not query or not query.data or ":" not in query.data:
            return

        action, suggestion_id_str = query.data.split(":", 1)
        try:
            suggestion_id = UUID(suggestion_id_str)
        except ValueError:
            logger.warning("invalid_suggestion_id_in_callback", id=suggestion_id_str)
            return

        email_msg = session.get(EmailMessage, suggestion_id)
        if not email_msg:
            logger.warning("suggestion_not_found_in_callback", id=suggestion_id)
            return

        # Idempotency check
        if email_msg.match_status in [
            EmailMatchStatus.USER_CONFIRMED,
            EmailMatchStatus.USER_REJECTED,
        ]:
            if query.message and isinstance(query.message, Message):
                try:
                    await bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        text=f"{query.message.text_markdown_v2}\n\n*\\(Already processed\\)*",
                        parse_mode="MarkdownV2",
                    )
                except Exception:
                    # Might fail if already edited or other reasons
                    pass
            return

        if action == "approve":
            await self._handle_approve(bot, update, email_msg, session)
        elif action == "reject":
            await self._handle_reject(bot, update, email_msg, session)
        elif action == "context":
            await self._handle_context(bot, update, email_msg)

        session.commit()

    async def _handle_approve(
        self, bot: Bot, update: Update, email_msg: EmailMessage, session: Session
    ) -> None:
        query = update.callback_query
        if not query or not isinstance(query.message, Message):
            return

        meta = email_msg.suggested_status_change or {}
        new_status = meta.get("status")
        if not new_status:
            return

        old_status = "unknown"
        if email_msg.matched_application_id:
            app = session.get(Application, email_msg.matched_application_id)
            if app:
                old_status = app.status
                app.status = new_status
                setattr(
                    app,
                    "_transition_note",
                    f"Confirmed via Telegram from email: {email_msg.gmail_message_id}",
                )
        elif email_msg.matched_outreach_message_id:
            msg = session.get(OutreachMessage, email_msg.matched_outreach_message_id)
            if msg:
                old_status = msg.status
                msg.status = new_status

        email_msg.match_status = EmailMatchStatus.USER_CONFIRMED

        new_text = escape_telegram_markdown_v2(f"✅ Aplicado: {old_status} → {new_status}")
        await bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text=new_text,
            parse_mode="MarkdownV2",
        )

    async def _handle_reject(
        self, bot: Bot, update: Update, email_msg: EmailMessage, session: Session
    ) -> None:
        query = update.callback_query
        if not query or not isinstance(query.message, Message):
            return

        email_msg.match_status = EmailMatchStatus.USER_REJECTED
        await bot.edit_message_text(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            text="❌ Rechazado",
            parse_mode="MarkdownV2",
        )

    async def _handle_context(self, bot: Bot, update: Update, email_msg: EmailMessage) -> None:
        query = update.callback_query
        if not query or not isinstance(query.message, Message):
            return

        # We construct the message parts and escape them individually where needed
        # or escape the whole thing and hope the simple Markdown tags survive if they are not in the escape list.
        # escape_telegram_markdown (from templates.py) usually escapes everything including *.

        reasoning = escape_telegram_markdown_v2(email_msg.match_reasoning or "No reasoning")
        snippet = escape_telegram_markdown_v2(email_msg.snippet or "No snippet available")

        context_text = f"*Reasoning:* {reasoning}\n\n*Snippet:* {snippet}"

        await bot.send_message(
            chat_id=query.message.chat_id,
            text=context_text,
            parse_mode="MarkdownV2",
        )

    def _get_settings(self) -> Settings:
        """Helper to get application settings."""
        return Settings()  # type: ignore[call-arg]

    async def _send_with_retry(
        self,
        bot: Bot,
        chat_id: str,
        text: str,
        start_time: float,
        reply_markup: InlineKeyboardMarkup | None = None,
        retry_count: int = 0,
    ) -> NotificationResult:
        """
        Internal helper to send message with one retry for RetryAfter.
        """
        try:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="MarkdownV2",
                reply_markup=reply_markup,
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
                return await self._send_with_retry(
                    bot, chat_id, text, start_time, reply_markup, retry_count + 1
                )
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
