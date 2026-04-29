import time

import anthropic
import structlog
from anthropic import APIConnectionError, InternalServerError, RateLimitError
from pydantic import BaseModel
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

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
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout)

    async def complete(
        self,
        system: str,
        user: str,
        model: str,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        """
        Send a completion request to Anthropic.

        Args:
            system: The system prompt.
            user: The user prompt.
            model: The model to use.
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
                        model=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        cost_usd=cost_usd,
                        duration_ms=duration_ms,
                        attempt=attempt,
                    )

                    return llm_response

                except (RateLimitError, APIConnectionError, InternalServerError) as e:
                    logger.warning(
                        "llm_call_retry",
                        model=model,
                        error=str(e),
                        attempt=attempt,
                    )
                    raise
                except Exception as e:
                    logger.error(
                        "llm_call_failed",
                        model=model,
                        error=str(e),
                        attempt=attempt,
                    )
                    raise
        # This line should technically not be reached because of reraise=True
        raise RuntimeError("LLM completion failed unexpectedly")
