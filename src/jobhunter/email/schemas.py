from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class Label(BaseModel):
    """Represents a Gmail label."""

    id: str
    name: str
    type: str | None = None


class GmailMessage(BaseModel):
    """Represents a summary of a Gmail message."""

    id: str
    thread_id: str = Field(alias="threadId")
    received_at: datetime
    from_email: str
    to_email: str | None = None
    subject: str | None = None
    snippet: str | None = None
    labels: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class GmailMessageDetail(GmailMessage):
    """Represents full details of a Gmail message including its body."""

    body_text: str | None = None
    body_html: str | None = None
