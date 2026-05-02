from datetime import datetime, timezone
from jobhunter.db.models import OutreachContact, OutreachMessage


def humanize_date(dt: datetime | None) -> str:
    """Formats a datetime into a human-readable string like '5 days ago' or '-'."""
    if not dt:
        return "-"

    # Ensure dt is timezone-aware if it's not
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    diff = now - dt

    if diff.days == 0:
        if diff.seconds < 60:
            return "just now"
        if diff.seconds < 3600:
            return f"{diff.seconds // 60}m ago"
        return f"{diff.seconds // 3600}h ago"

    if diff.days == 1:
        return "yesterday"

    if diff.days < 30:
        return f"{diff.days} days ago"

    return dt.strftime("%Y-%m-%d")


def format_contact_row(contact: OutreachContact) -> list[str]:
    """Formats an OutreachContact into a list of strings for a Rich table row."""
    return [
        str(contact.id),
        contact.name,
        contact.company or "-",
        contact.role or "-",
        str(contact.quality_score or "-"),
        contact.status.value if hasattr(contact.status, "value") else str(contact.status),
        humanize_date(contact.last_contacted_at),
    ]


def format_message_row(msg: OutreachMessage) -> list[str]:
    """Formats an OutreachMessage into a list of strings for a Rich table row."""
    contact_name = msg.contact.name if hasattr(msg, "contact") and msg.contact else "-"
    return [
        str(msg.id)[:8],
        contact_name,
        msg.template_type.value if hasattr(msg.template_type, "value") else str(msg.template_type),
        msg.status.value if hasattr(msg.status, "value") else str(msg.status),
        msg.created_at.strftime("%Y-%m-%d %H:%M") if msg.created_at else "-",
        humanize_date(msg.sent_at),
        humanize_date(msg.replied_at),
    ]
