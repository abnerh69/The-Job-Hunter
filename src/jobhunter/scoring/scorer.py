"""
Main scoring logic for evaluating job offers using LLMs.
"""

import structlog
from pydantic import BaseModel, ConfigDict

from jobhunter.db.models import Job
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.scoring.errors import ScoringAPIError, ScoringParseError
from jobhunter.scoring.prompt import load_prompt, render_user_prompt
from jobhunter.scoring.schema import (
    InvalidScoringResponse,
    ScoringResult,
    parse_scoring_response,
)

logger = structlog.get_logger(__name__)


class ScoringOutcome(BaseModel):
    """
    Standard outcome of a job scoring operation.
    """

    model_config = ConfigDict(extra="forbid")

    result: ScoringResult | InvalidScoringResponse
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int
    raw_response: str


class JobScorer:
    """
    Orchestrates the scoring of a job using an LLM.
    """

    def __init__(
        self,
        llm_client: AnthropicLLMClient,
        prompt_version: str = "latest",
        model: str = "claude-haiku-4-5-20251001",
    ):
        """
        Initialize the JobScorer.

        Args:
            llm_client: The LLM client to use for scoring.
            prompt_version: The version of the scoring prompt to use.
            model: The LLM model to use.
        """
        self.llm_client = llm_client
        self.prompt_version = prompt_version
        self.model = model
        self.prompt = load_prompt(version=prompt_version)

    def _truncate_description(self, text: str, max_chars: int = 8000) -> str:
        """
        Truncates the description to a maximum number of characters.
        Tries to cut at a paragraph or word boundary.

        Args:
            text: The text to truncate.
            max_chars: The maximum number of characters.

        Returns:
            The truncated text.
        """
        if len(text) <= max_chars:
            return text

        # Try to find the last paragraph break before max_chars
        truncated = text[:max_chars]
        last_para = truncated.rfind("\n\n")
        if last_para > max_chars * 0.7:  # Only cut at paragraph if it's not too short
            return text[:last_para].strip()

        # Try to find the last sentence break
        last_sentence = max(truncated.rfind(". "), truncated.rfind(".\n"))
        if last_sentence > max_chars * 0.8:
            return text[: last_sentence + 1].strip()

        # Fallback to last word boundary
        last_space = truncated.rfind(" ")
        if last_space > 0:
            return text[:last_space].strip()

        return truncated.strip()

    async def score(self, job: Job) -> ScoringOutcome:
        """
        Scores a job offer.

        Args:
            job: The job to score.

        Returns:
            A ScoringOutcome object.

        Raises:
            ScoringAPIError: If there is an error calling the LLM.
            ScoringParseError: If the AI response cannot be parsed after retries.
        """
        job_data = {
            "title": job.title,
            "company": job.company,
            "description": self._truncate_description(job.description),
            "source": job.source,
            "url": job.url,
            "scraped_at": job.scraped_at,
            "location_raw": job.location_raw,
        }

        user_prompt = render_user_prompt(self.prompt.user_template, job_data)

        try:
            llm_response = await self.llm_client.complete(
                system=self.prompt.system_prompt,
                user=user_prompt,
                model=self.model,
            )
        except Exception as e:
            logger.error("llm_call_failed", error=str(e), job_id=str(job.id))
            raise ScoringAPIError(f"Failed to call LLM: {e}") from e

        try:
            result = parse_scoring_response(llm_response.text)
        except Exception as e:
            logger.warning(
                "scoring_parse_failed_first_attempt",
                error=str(e),
                job_id=str(job.id),
                raw_response=llm_response.text,
            )
            # Retry with reinforced instruction
            reinforced_user = (
                f"{user_prompt}\n\n"
                "IMPORTANT: Respond with valid JSON only, no preamble or postamble."
            )

            try:
                llm_response = await self.llm_client.complete(
                    system=self.prompt.system_prompt,
                    user=reinforced_user,
                    model=self.model,
                )
                result = parse_scoring_response(llm_response.text)
            except Exception as retry_err:
                logger.error(
                    "scoring_parse_failed_after_retry",
                    error=str(retry_err),
                    job_id=str(job.id),
                    raw_response=llm_response.text,
                )
                raise ScoringParseError(
                    f"Failed to parse AI response after retry: {retry_err}",
                    raw_response=llm_response.text,
                ) from retry_err

        return ScoringOutcome(
            result=result,
            model=llm_response.model,
            prompt_version=self.prompt.version,
            input_tokens=llm_response.input_tokens,
            output_tokens=llm_response.output_tokens,
            cost_usd=llm_response.cost_usd,
            duration_ms=llm_response.duration_ms,
            raw_response=llm_response.text,
        )
