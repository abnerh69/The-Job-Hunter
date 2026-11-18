"""Common protocol for LLM clients."""

from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.llm.anthropic_client import LLMResponse


class LLMClient(Protocol):
    """Protocol implemented by all LLM provider clients."""

    async def complete(
        self,
        system: str,
        user: str,
        model: str,
        purpose: LLMPurpose,
        session: Session | None = None,
        job_id: UUID | None = None,
        prompt_version: str | None = None,
        max_tokens: int = 1500,
    ) -> LLMResponse: ...
