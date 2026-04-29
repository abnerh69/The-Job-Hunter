"""
Pricing for Anthropic models.
USD per million tokens, verified 2026-04-29.
"""

PRICING = {
    "claude-haiku-4-5-20251001": {"input": 1.0, "output": 5.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-7": {"input": 15.0, "output": 75.0},
}


def calculate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Calculate the cost of an LLM call in USD.

    Args:
        model: The model name.
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        The calculated cost in USD.
    """
    if model not in PRICING:
        return 0.0

    input_cost = (input_tokens / 1_000_000) * PRICING[model]["input"]
    output_cost = (output_tokens / 1_000_000) * PRICING[model]["output"]

    return input_cost + output_cost
