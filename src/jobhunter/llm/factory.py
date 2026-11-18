"""Factory for instantiating the configured LLM provider client."""

from jobhunter.config import Settings
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.llm.base import LLMClient
from jobhunter.llm.gemini_client import AgyCLILLMClient, GeminiLLMClient


def create_llm_client(settings: Settings) -> LLMClient:
    """Create an LLM client according to `settings.LLM_PROVIDER`."""
    provider = settings.LLM_PROVIDER
    if provider == "mock":
        return AnthropicLLMClient(api_key="dummy")
    if provider == "gemini":
        if settings.GEMINI_API_KEY is None:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER='gemini'")
        return GeminiLLMClient(
            api_key=settings.GEMINI_API_KEY.get_secret_value(),
            default_model=settings.GEMINI_MODEL,
        )
    if provider == "agy_cli":
        return AgyCLILLMClient(
            cli_bin=settings.AGY_CLI_BIN,
            default_model=settings.AGY_MODEL,
        )
    if settings.ANTHROPIC_API_KEY is None:
        raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER='anthropic'")
    return AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
