import functools
import inspect
from contextvars import ContextVar
from typing import Any, Callable, TypeVar

import structlog

from jobhunter.db.enums import AuditEventType
from jobhunter.db.session import get_session
from jobhunter.db.repos.audit_log import AuditLogRepo

logger = structlog.get_logger(__name__)

# Context variable to store the current actor (user, system, cron, etc.)
_current_actor: ContextVar[str] = ContextVar("current_actor", default="system")
_current_ip: ContextVar[str | None] = ContextVar("current_ip", default=None)

F = TypeVar("F", bound=Callable[..., Any])


def set_audit_context(actor: str, ip_address: str | None = None) -> None:
    """Sets the current actor and IP address in the context."""
    _current_actor.set(actor)
    _current_ip.set(ip_address)


def audit_logged(event_type: AuditEventType, action: str) -> Callable[[F], F]:
    """
    Decorator to automatically log critical mutations to the audit log.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)

            try:
                actor = _current_actor.get()
                ip_address = _current_ip.get()

                # Extract metadata from function arguments
                # For simplicity, we just store a summary of arguments
                # In a real system, we'd be more selective
                metadata = {}
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()

                for name, value in bound_args.arguments.items():
                    if name in ("session", "self", "db"):
                        continue
                    if (
                        "password" in name.lower()
                        or "token" in name.lower()
                        or "secret" in name.lower()
                    ):
                        metadata[name] = "[REDACTED]"
                    else:
                        metadata[name] = str(value)[:500]  # Avoid massive blobs

                with get_session() as session:
                    repo = AuditLogRepo(session)
                    repo.record(
                        event_type=event_type,
                        actor=actor,
                        action=action,
                        event_metadata=metadata,
                        ip_address=ip_address,
                    )
                    session.commit()
            except Exception as e:
                logger.error("failed_to_log_audit_event", error=str(e), event_type=event_type)

            return result

        return wrapper  # type: ignore

    return decorator


def audit_logged_async(event_type: AuditEventType, action: str) -> Callable[[F], F]:
    """
    Decorator to automatically log critical mutations to the audit log (async version).
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = await func(*args, **kwargs)

            try:
                actor = _current_actor.get()
                ip_address = _current_ip.get()

                metadata = {}
                sig = inspect.signature(func)
                bound_args = sig.bind(*args, **kwargs)
                bound_args.apply_defaults()

                for name, value in bound_args.arguments.items():
                    if name in ("session", "self", "db"):
                        continue
                    if (
                        "password" in name.lower()
                        or "token" in name.lower()
                        or "secret" in name.lower()
                    ):
                        metadata[name] = "[REDACTED]"
                    else:
                        metadata[name] = str(value)[:500]

                with get_session() as session:
                    repo = AuditLogRepo(session)
                    repo.record(
                        event_type=event_type,
                        actor=actor,
                        action=action,
                        event_metadata=metadata,
                        ip_address=ip_address,
                    )
                    session.commit()
            except Exception as e:
                logger.error("failed_to_log_audit_event_async", error=str(e), event_type=event_type)

            return result

        return wrapper  # type: ignore

    return decorator
