import pytest
from jobhunter.notify.base import (
    BaseNotifier,
    NotificationMessage,
    NotificationResult,
    register_notifier,
    get_all_notifiers,
)
from jobhunter.config import Settings
from pydantic import SecretStr


class DummyNotifier(BaseNotifier):
    @property
    def name(self) -> str:
        return "dummy"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.TELEGRAM_BOT_TOKEN is not None

    async def send(self, message: NotificationMessage) -> NotificationResult:
        return NotificationResult(success=True, provider_message_id="dummy-id", duration_ms=10)


def test_notifier_registration() -> None:
    # Clear registry for testing if necessary,
    # but since it's a global we might just check if DummyNotifier is in it
    register_notifier("dummy")(DummyNotifier)
    notifiers = get_all_notifiers()
    assert DummyNotifier in notifiers


def test_notifier_is_enabled() -> None:
    notifier = DummyNotifier()

    # Enabled case
    settings_enabled = Settings(
        ANTHROPIC_API_KEY=SecretStr("key"), TELEGRAM_BOT_TOKEN=SecretStr("token")
    )
    assert notifier.is_enabled(settings_enabled) is True

    # Disabled case
    settings_disabled = Settings(ANTHROPIC_API_KEY=SecretStr("key"), TELEGRAM_BOT_TOKEN=None)
    assert notifier.is_enabled(settings_disabled) is False


@pytest.mark.asyncio
async def test_notifier_send() -> None:
    notifier = DummyNotifier()
    message = NotificationMessage(channel="dummy", body_text="Hello")
    result = await notifier.send(message)
    assert result.success is True
    assert result.provider_message_id == "dummy-id"
