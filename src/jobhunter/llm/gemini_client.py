"""Gemini API and Antigravity CLI (`agy -p`) LLM clients."""

from __future__ import annotations

import asyncio
import re
import time
from uuid import UUID

import httpx
import structlog
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.llm.anthropic_client import LLMResponse

logger = structlog.get_logger(__name__)

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _strip_markdown_fences(text: str) -> str:
    """Remove surrounding markdown code fences if the model included them."""
    stripped = text.strip()
    match = re.match(r"^```(?:json)?\s*\n(.*?)\n```$", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()
    return stripped


def _record_llm_call(
    session: Session | None,
    *,
    job_id: UUID | None,
    purpose: LLMPurpose,
    model: str,
    prompt_version: str | None,
    input_tokens: int,
    output_tokens: int,
    cost_usd: float,
    duration_ms: int,
    status: str,
) -> None:
    if session is None:
        return
    repo = LLMCallRepo(session)
    repo.record_call(
        model=model,
        purpose=purpose,
        success=(status == "success"),
        job_id=job_id,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )


class GeminiLLMClient:
    """LLM client calling Google's Gemini REST API via httpx."""

    def __init__(
        self,
        api_key: str,
        default_model: str = "gemini-2.5-flash",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.default_model = default_model
        self.timeout = timeout

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
    ) -> LLMResponse:
        """Send a completion request to Gemini REST API."""
        target_model = self.default_model if model.startswith("claude-") else model
        start_time = time.perf_counter()

        url = f"{_GEMINI_API_BASE}/{target_model}:generateContent"
        payload: dict[str, object] = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    params={"key": self.api_key},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            _record_llm_call(
                session,
                job_id=job_id,
                purpose=purpose,
                model=target_model,
                prompt_version=prompt_version,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                duration_ms=duration_ms,
                status="error",
            )
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        candidates = data.get("candidates", [])
        text = ""
        stop_reason = None
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            stop_reason = candidates[0].get("finishReason")

        text = _strip_markdown_fences(text)
        usage = data.get("usageMetadata", {})
        input_tokens = int(usage.get("promptTokenCount", 0))
        output_tokens = int(usage.get("candidatesTokenCount", 0))

        _record_llm_call(
            session,
            job_id=job_id,
            purpose=purpose,
            model=target_model,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            duration_ms=duration_ms,
            status="success",
        )

        return LLMResponse(
            text=text,
            model=target_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=0.0,
            duration_ms=duration_ms,
            stop_reason=stop_reason,
        )


class AgyCLILLMClient:
    """LLM client invoking Antigravity CLI (`agy -p`) in headless mode on remote server."""

    def __init__(
        self,
        cli_bin: str = "agy",
        default_model: str = "gemini-4-hydrogen-medium",
        timeout: float = 120.0,
    ) -> None:
        self.cli_bin = cli_bin
        self.default_model = default_model
        self.timeout = timeout

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
    ) -> LLMResponse:
        """Run `agy -p` with combined system/user instructions and return its stdout."""
        del max_tokens  # `agy -p` manages generation limits internally
        target_model = self.default_model if model.startswith("claude-") else model
        combined_prompt = (
            f"Follow these instructions strictly and output ONLY the requested response.\n\n"
            f"### SYSTEM\n{system}\n\n### USER\n{user}"
        )

        start_time = time.perf_counter()
        try:
            proc = await asyncio.create_subprocess_exec(
                self.cli_bin,
                "-p",
                combined_prompt,
                "--model",
                target_model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            if proc.returncode != 0:
                stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
                raise RuntimeError(f"agy CLI exited with {proc.returncode}: {stderr_text}")
        except Exception:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            _record_llm_call(
                session,
                job_id=job_id,
                purpose=purpose,
                model=target_model,
                prompt_version=prompt_version,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                duration_ms=duration_ms,
                status="error",
            )
            raise

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        text = _strip_markdown_fences(stdout_bytes.decode("utf-8", errors="replace"))

        _record_llm_call(
            session,
            job_id=job_id,
            purpose=purpose,
            model=target_model,
            prompt_version=prompt_version,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            duration_ms=duration_ms,
            status="success",
        )

        return LLMResponse(
            text=text,
            model=target_model,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0,
            duration_ms=duration_ms,
            stop_reason="end_turn",
        )
