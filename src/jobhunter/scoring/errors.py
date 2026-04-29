"""
Custom exceptions for the scoring module.
"""


class ScoringError(Exception):
    """Base exception for all scoring-related errors."""


class ScoringParseError(ScoringError):
    """
    Raised when the AI response cannot be parsed into a valid scoring result.

    Attributes:
        message: The error message.
        raw_response: The raw response string from the AI that failed to parse.
    """

    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


class ScoringAPIError(ScoringError):
    """Raised when there is an error communicating with the LLM API."""
