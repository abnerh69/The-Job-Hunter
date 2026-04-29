from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anthropic import AuthenticationError, RateLimitError

from jobhunter.llm.anthropic_client import AnthropicLLMClient, LLMResponse
from jobhunter.llm.pricing import calculate_cost_usd


def test_calculate_cost_usd() -> None:
    """Test cost calculation for supported models."""
    # Haiku: $1/$5 per M tokens
    # 100k input, 200k output -> 0.1 * 1 + 0.2 * 5 = 0.1 + 1.0 = 1.1
    assert calculate_cost_usd("claude-haiku-4-5-20251001", 100_000, 200_000) == pytest.approx(1.1)

    # Sonnet: $3/$15 per M tokens
    # 1M input, 1M output -> 1 * 3 + 1 * 15 = 18.0
    assert calculate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)

    # Opus: $15/$75 per M tokens
    # 1M input, 1M output -> 1 * 15 + 1 * 75 = 90.0
    assert calculate_cost_usd("claude-opus-4-7", 1_000_000, 1_000_000) == pytest.approx(90.0)

    # Unknown model
    assert calculate_cost_usd("unknown-model", 1000, 1000) == 0.0


@pytest.mark.asyncio
async def test_complete_success() -> None:
    """Test successful completion."""
    client = AnthropicLLMClient(api_key="test-key")

    mock_response = MagicMock()
    mock_response.model = "claude-haiku-4-5-20251001"
    mock_response.usage.input_tokens = 100
    mock_response.usage.output_tokens = 50
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(text="Hello world")]

    with patch.object(client.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_response

        response = await client.complete(
            system="system prompt",
            user="user prompt",
            model="claude-haiku-4-5-20251001",
        )

        assert isinstance(response, LLMResponse)
        assert response.text == "Hello world"
        assert response.model == "claude-haiku-4-5-20251001"
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.cost_usd == calculate_cost_usd("claude-haiku-4-5-20251001", 100, 50)
        assert response.stop_reason == "end_turn"
        assert response.duration_ms >= 0


@pytest.mark.asyncio
async def test_complete_retry_on_rate_limit() -> None:
    """Test retry behavior on RateLimitError."""
    client = AnthropicLLMClient(api_key="test-key")

    mock_response = MagicMock()
    mock_response.model = "claude-haiku-4-5-20251001"
    mock_response.usage.input_tokens = 10
    mock_response.usage.output_tokens = 10
    mock_response.stop_reason = "end_turn"
    mock_response.content = [MagicMock(text="Success after retry")]

    # Mock RateLimitError
    # The RateLimitError needs a response object which can be mocked
    mock_err_response = MagicMock()
    mock_err_response.status_code = 429
    rate_limit_error = RateLimitError(
        message="Rate limit exceeded", response=mock_err_response, body=None
    )

    with patch.object(client.client.messages, "create", new_callable=AsyncMock) as mock_create:
        # First call fails, second succeeds
        mock_create.side_effect = [rate_limit_error, mock_response]

        # Reduce wait time for tests
        with patch("tenacity.wait_exponential_jitter.__call__", return_value=0.01):
            response = await client.complete(
                system="system",
                user="user",
                model="claude-haiku-4-5-20251001",
            )

        assert response.text == "Success after retry"
        assert mock_create.call_count == 2


@pytest.mark.asyncio
async def test_complete_no_retry_on_auth_error() -> None:
    """Test that AuthenticationError does not trigger retries."""
    client = AnthropicLLMClient(api_key="test-key")

    mock_err_response = MagicMock()
    mock_err_response.status_code = 401
    auth_error = AuthenticationError(
        message="Invalid API key", response=mock_err_response, body=None
    )

    with patch.object(client.client.messages, "create", new_callable=AsyncMock) as mock_create:
        mock_create.side_effect = auth_error

        with pytest.raises(AuthenticationError):
            await client.complete(
                system="system",
                user="user",
                model="claude-haiku-4-5-20251001",
            )

        assert mock_create.call_count == 1
