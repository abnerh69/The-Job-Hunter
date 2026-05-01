import logging
import os
import contextvars
from typing import Any, Dict, Optional, Generator
from contextlib import contextmanager

import structlog

from jobhunter.config import Settings

# Context variable to store correlation_id
_CORRELATION_ID: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "correlation_id", default=None
)


def add_correlation_id(logger: Any, method_name: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Processor to add correlation_id to log records.
    """
    correlation_id = _CORRELATION_ID.get()
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def redact_sensitive_info(
    logger: Any, method_name: str, event_dict: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Processor to redact sensitive fields from logs.
    """
    sensitive_fields = {"password", "token", "api_key"}
    for field in sensitive_fields:
        if field in event_dict:
            event_dict[field] = "****"
    return event_dict


@contextmanager
def with_correlation_id(correlation_id: str) -> Generator[None, None, None]:
    """
    Context manager to set the correlation_id for a block of code.
    """
    token = _CORRELATION_ID.set(correlation_id)
    try:
        yield
    finally:
        _CORRELATION_ID.reset(token)


def configure_logging() -> None:
    """
    Configures structlog for the application.
    Uses JSON formatting if LOG_FORMAT=json, otherwise pretty-printing.
    """
    settings = Settings()  # type: ignore[call-arg]

    # Initialize correlation_id from environment if present
    env_correlation_id = os.getenv("JOBHUNTER_CORRELATION_ID")
    if env_correlation_id:
        _CORRELATION_ID.set(env_correlation_id)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.format_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
        add_correlation_id,
        redact_sensitive_info,
    ]

    if settings.LOG_FORMAT == "json":
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(),
        ]

    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> Any:
    """
    Returns a structlog logger with the module name bound.
    """
    return structlog.get_logger(name).bind(module=name)
