import pytest
import json
import uuid
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from jobhunter.db.enums import LLMPurpose
from jobhunter.email.matcher import match_email
from jobhunter.email.schemas import GmailMessageDetail
from jobhunter.email.prompt import load_email_prompt


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def mock_llm_client() -> MagicMock:
    client = MagicMock()
    client.complete = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_matcher_regression_after_refactor(
    mock_session: MagicMock, mock_llm_client: MagicMock
) -> None:
    """
    Ensures the matcher produces the same MatchResult before and after refactor
    given the same LLM response.
    """
    email = GmailMessageDetail(
        id="msg_reg",
        threadId="thread_reg",
        received_at=datetime.now(),
        from_email="test@example.com",
        subject="Regression Test",
        snippet="Snippet for regression",
        body_text="Full body for regression",
    )

    # Mock no heuristic matches
    mock_session.scalars.return_value.all.return_value = []

    # Mock AI response
    target_app_id = str(uuid.uuid4())
    ai_response_json = {
        "match_status": "ai_matched",
        "application_id": target_app_id,
        "outreach_contact_id": None,
        "confidence": 0.88,
        "reasoning": "Matching because of X and Y.",
    }

    mock_llm_client.complete.return_value = MagicMock(
        text=json.dumps(ai_response_json),
        model="claude-3-haiku-20240307",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=500,
    )

    # Run matcher
    result = await match_email(email, mock_session, mock_llm_client)

    # Verify MatchResult
    assert result.match_status == "ai_matched"
    assert str(result.application_id) == target_app_id
    assert result.confidence == 0.88
    # Reason should now include version prefix
    assert result.reasoning == "[v1] Matching because of X and Y."

    # Verify LLM call parameters
    prompt_data = load_email_prompt("v1")
    expected_system = f"{prompt_data.system_prompt}\n\n{prompt_data.requirements}"

    mock_llm_client.complete.assert_called_once()
    args, kwargs = mock_llm_client.complete.call_args
    assert kwargs["system"] == expected_system
    assert kwargs["purpose"] == LLMPurpose.EMAIL_MATCH
    assert kwargs["prompt_version"] == "v1"
