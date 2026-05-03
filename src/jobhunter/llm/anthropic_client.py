import time
from uuid import UUID
from typing import Any

import anthropic
import structlog
from anthropic import APIConnectionError, InternalServerError, RateLimitError
from pydantic import BaseModel
from sqlalchemy.orm import Session
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from jobhunter.db.enums import LLMPurpose
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.llm.pricing import calculate_cost_usd

logger = structlog.get_logger(__name__)


class LLMResponse(BaseModel):
    """
    Standard response from an LLM call.
    """

    text: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    stop_reason: str | None


class AnthropicLLMClient:
    """
    Centralized wrapper for the Anthropic API client.
    """

    def __init__(self, api_key: str, timeout: float = 60.0):
        """
        Initialize the client.

        Args:
            api_key: The Anthropic API key.
            timeout: The timeout for API calls in seconds.
        """
        if api_key == "dummy":
            # For testing purposes when ANTHROPIC_API_KEY is dummy
            self._mock_mode = True
            self.client: Any = None
        else:
            self._mock_mode = False
            self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

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
        """
        Send a completion request to Anthropic.

        Args:
            system: The system prompt.
            user: The user prompt.
            model: The model to use.
            purpose: The purpose of the call.
            session: The SQLAlchemy session to use for recording the call.
            job_id: The ID of the job associated with the call.
            prompt_version: The version of the prompt used.
            max_tokens: The maximum number of tokens to generate.

        Returns:
            An LLMResponse object.
        """
        start_time = time.perf_counter()
        attempt = 0

        async for attempt_retry in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential_jitter(initial=1, max=4),
            retry=retry_if_exception_type(
                (RateLimitError, APIConnectionError, InternalServerError)
            ),
            reraise=True,
        ):
            with attempt_retry:
                attempt += 1
                try:
                    if self._mock_mode:
                        # Mock behavior for E2E tests when dummy key is used
                        duration_ms = 100
                        input_tokens = 500
                        output_tokens = 300
                        cost_usd = 0.01

                        import json

                        if purpose == LLMPurpose.ATS_KEYWORDS:
                            text = json.dumps(
                                {
                                    "must_have": [
                                        {"term": "Python", "category": "technical", "weight": 10}
                                    ],
                                    "nice_to_have": [
                                        {"term": "AI", "category": "technical", "weight": 5}
                                    ],
                                }
                            )
                        elif purpose == LLMPurpose.CV_TWEAKS:
                            text = json.dumps(
                                {
                                    "tweaks": [
                                        {
                                            "type": "add_keyword",
                                            "target": "Python",
                                            "rationale": "High weight",
                                        }
                                    ]
                                }
                            )
                        elif purpose == LLMPurpose.OUTREACH_MESSAGE:
                            # Mock outreach message that passes validation (80-150 words)
                            # and includes a term from research notes (e.g. "company")
                            text = "Hello, I am interested in your company. " + " ".join(
                                ["word"] * 100
                            )
                        elif purpose == LLMPurpose.RESUME_PARSING:
                            text = json.dumps(
                                {
                                    "name": "Jane Doe",
                                    "email": "jane@example.com",
                                    "phone": "123456789",
                                    "location_raw": "Berlin, Germany",
                                    "summary": "Experienced Python Developer",
                                    "experiences": [
                                        {
                                            "role": "Senior Engineer",
                                            "company": "Tech Corp",
                                            "dates": "2020 - Present",
                                            "bullets": ["Developed Python apps", "Managed team"],
                                        }
                                    ],
                                    "educations": [
                                        {
                                            "degree": "BSc Computer Science",
                                            "institution": "Tech University",
                                            "dates": "2015-2019",
                                            "description": "GPA 3.8",
                                        }
                                    ],
                                    "skills": ["Python", "SQL"],
                                    "languages": ["English", "German"],
                                    "detected_seniority": "senior",
                                    "detected_years_experience": 8,
                                    "detected_primary_stack": ["Python", "FastAPI"],
                                }
                            )
                        elif purpose == LLMPurpose.SALARY_PROPOSAL:
                            text = json.dumps(
                                {
                                    "currency": "USD",
                                    "period": "year",
                                    "floor": 90000,
                                    "target": 110000,
                                    "stretch": 130000,
                                    "rationale": "Strong background in Python and AI.",
                                    "data_sources": ["llm_baseline_2026"],
                                    "confidence": 0.9,
                                }
                            )
                        else:
                            # Mock cover letter that passes validation (250-450 words)
                            text = " ".join(["word"] * 300)

                        llm_response = LLMResponse(
                            text=text,
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost_usd=cost_usd,
                            duration_ms=duration_ms,
                            stop_reason="end_turn",
                        )
                    else:
                        response = await self.client.messages.create(
                            model=model,
                            max_tokens=max_tokens,
                            system=system,
                            messages=[{"role": "user", "content": user}],
                        )

                        duration_ms = int((time.perf_counter() - start_time) * 1000)
                        input_tokens = response.usage.input_tokens
                        output_tokens = response.usage.output_tokens
                        cost_usd = calculate_cost_usd(model, input_tokens, output_tokens)

                        text = ""
                        if response.content and hasattr(response.content[0], "text"):
                            text = response.content[0].text

                        llm_response = LLMResponse(
                            text=text,
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            cost_usd=cost_usd,
                            duration_ms=duration_ms,
                            stop_reason=response.stop_reason,
                        )

                    logger.info(
                        "llm_call_success",
                        model=llm_response.model,
                        input_tokens=llm_response.input_tokens,
                        output_tokens=llm_response.output_tokens,
                        cost_usd=llm_response.cost_usd,
                        duration_ms=llm_response.duration_ms,
                        attempt=attempt,
                    )

                    if session:
                        repo = LLMCallRepo(session)
                        repo.record_call(
                            model=llm_response.model,
                            purpose=purpose,
                            success=True,
                            job_id=job_id,
                            prompt_version=prompt_version,
                            input_tokens=llm_response.input_tokens,
                            output_tokens=llm_response.output_tokens,
                            cost_usd=llm_response.cost_usd,
                            duration_ms=llm_response.duration_ms,
                        )

                    return llm_response

                except (RateLimitError, APIConnectionError, InternalServerError) as e:
                    logger.warning(
                        "llm_call_retry",
                        model=model,
                        error=str(e),
                        attempt=attempt,
                    )
                    if session:
                        duration_ms = int((time.perf_counter() - start_time) * 1000)
                        repo = LLMCallRepo(session)
                        repo.record_call(
                            model=model,
                            purpose=purpose,
                            success=False,
                            job_id=job_id,
                            prompt_version=prompt_version,
                            duration_ms=duration_ms,
                        )
                    raise
                except Exception as e:
                    logger.error(
                        "llm_call_failed",
                        model=model,
                        error=str(e),
                        attempt=attempt,
                    )
                    if session:
                        duration_ms = int((time.perf_counter() - start_time) * 1000)
                        repo = LLMCallRepo(session)
                        repo.record_call(
                            model=model,
                            purpose=purpose,
                            success=False,
                            job_id=job_id,
                            prompt_version=prompt_version,
                            duration_ms=duration_ms,
                        )
                    raise
        # This line should technically not be reached because of reraise=True
        raise RuntimeError("LLM completion failed unexpectedly")
