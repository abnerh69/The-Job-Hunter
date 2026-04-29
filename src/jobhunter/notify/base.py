from abc import ABC, abstractmethod
from typing import Any, Type

from pydantic import BaseModel

from jobhunter.config import Settings


class NotificationMessage(BaseModel):
    """
    Model representing a notification message to be sent.
    """

    channel: str
    subject: str | None = None
    body_text: str
    body_html: str | None = None
    metadata: dict[str, Any] = {}


class NotificationResult(BaseModel):
    """
    Model representing the result of a notification sending attempt.
    """

    success: bool
    provider_message_id: str | None = None
    error: str | None = None
    duration_ms: int


class BaseNotifier(ABC):
    """
    Abstract Base Class for all notification providers.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for the notifier.
        """
        pass

    @abstractmethod
    def is_enabled(self, settings: Settings) -> bool:
        """
        Checks if the notifier is enabled based on the application settings.
        """
        pass

    @abstractmethod
    async def send(self, message: NotificationMessage) -> NotificationResult:
        """
        Sends a notification message using the provider.

        Args:
            message: The NotificationMessage to send.

        Returns:
            NotificationResult: The result of the sending attempt.
        """
        pass


_REGISTRY: dict[str, Type[BaseNotifier]] = {}


def register_notifier(name: str) -> Any:
    """
    Decorator to register a notifier class in the registry.

    Args:
        name: The unique identifier for the notifier.

    Returns:
        The decorator function.
    """

    def decorator(cls: Type[BaseNotifier]) -> Type[BaseNotifier]:
        _REGISTRY[name] = cls
        return cls

    return decorator


def get_all_notifiers() -> list[Type[BaseNotifier]]:
    """
    Retrieves all registered notifier classes.

    Returns:
        A list of registered BaseNotifier subclasses.
    """
    return list(_REGISTRY.values())


def get_notifier_cls(name: str) -> Type[BaseNotifier] | None:
    """
    Retrieves a registered notifier class by its name.

    Args:
        name: The unique identifier for the notifier.

    Returns:
        The notifier class if found, None otherwise.
    """
    return _REGISTRY.get(name)
