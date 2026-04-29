import re
from datetime import date, datetime
from functools import lru_cache
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


def format_currency(amount: float | None, currency: str = "USD") -> str:
    """
    Formats a numeric amount as a currency string.

    Args:
        amount: The numeric amount to format.
        currency: The currency symbol or code (default: 'USD').

    Returns:
        A formatted currency string (e.g., "$5,500").
    """
    if amount is None:
        return ""
    return f"{currency} {amount:,.0f}".replace("USD ", "$")


def format_date_human(dt: date | datetime | str) -> str:
    """
    Formats a date or datetime into a human-readable string.

    Args:
        dt: The date, datetime, or ISO string to format.

    Returns:
        A human-readable date string (e.g., "Jan 15, 2024").
    """
    if not dt:
        return ""

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return str(dt)

    return dt.strftime("%b %d, %Y")


def truncate_words(text: str, n: int) -> str:
    """
    Truncates a string to at most n words.

    Args:
        text: The string to truncate.
        n: The maximum number of words to keep.

    Returns:
        The truncated string with an ellipsis if it was shortened.
    """
    if not text:
        return ""
    words = text.split()
    if len(words) <= n:
        return text
    return " ".join(words[:n]) + "..."


def escape_telegram_markdown(text: str) -> str:
    """
    Escapes special characters for Telegram MarkdownV2.

    According to Telegram API, these characters must be escaped:
    '_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!'

    Args:
        text: The string to escape.

    Returns:
        An escaped string safe for Telegram MarkdownV2.
    """
    if not text:
        return ""
    # Characters that need escaping in MarkdownV2
    escape_chars = r"_*[]()~`>#+-=|{}.!"
    return re.sub(f"([{re.escape(escape_chars)}])", r"\\\1", text)


@lru_cache(maxsize=1)
def get_jinja_env() -> Environment:
    """
    Creates and caches the Jinja2 environment.

    Returns:
        The configured Jinja2 Environment.
    """
    env = Environment(
        loader=FileSystemLoader("templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["format_currency"] = format_currency
    env.filters["format_date_human"] = format_date_human
    env.filters["truncate_words"] = truncate_words
    env.filters["escape_telegram_markdown"] = escape_telegram_markdown

    return env


def render(template_name: str, context: dict[str, Any]) -> str:
    """
    Renders a Jinja2 template with the given context.

    Args:
        template_name: The path to the template relative to the 'templates' directory.
        context: A dictionary of variables to pass to the template.

    Returns:
        The rendered template as a string.
    """
    env = get_jinja_env()
    template = env.get_template(template_name)
    return template.render(**context)
