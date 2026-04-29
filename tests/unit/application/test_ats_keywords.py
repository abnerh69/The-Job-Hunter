import pytest
from unittest.mock import MagicMock, AsyncMock
from pathlib import Path
from jobhunter.application.ats_keywords import (
    extract_ats_keywords,
    _check_presence_in_cv,
    ATSKeywordsResult
)
from jobhunter.db.models import Job
from jobhunter.application.cv import CVVariant
from jobhunter.llm.anthropic_client import LLMResponse
from jobhunter.db.enums import LLMPurpose

@pytest.fixture
def mock_job():
    return Job(
        id="00000000-0000-0000-0000-000000000001",
        title="Senior Python Engineer",
        company="Tech Corp",
        description="We are looking for a Python expert with AWS experience. K8s is a plus.",
        source="linkedin",
        url="http://example.com"
    )

@pytest.fixture
def mock_cv():
    return CVVariant(
        name="test_cv",
        path=Path("test.md"),
        summary="Senior Developer",
        stack_primary=["Python", "AWS"],
        stack_secondary=[],
        experience=[],
        skills=[],
        raw_markdown="Experience with Python 3 and Amazon Web Services. I also know Docker."
    )

@pytest.mark.asyncio
async def test_extract_ats_keywords_success(mock_job, mock_cv):
    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock(return_value=LLMResponse(
        text='{"must_have": [{"term": "Python", "category": "technical", "weight": 10}, {"term": "AWS", "category": "technical", "weight": 9}], "nice_to_have": [{"term": "Kubernetes", "category": "tool", "weight": 5}]}',
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=500,
        stop_reason="end_turn"
    ))

    result = await extract_ats_keywords(mock_job, mock_llm_client, cv_variant=mock_cv)

    assert isinstance(result, ATSKeywordsResult)
    assert len(result.must_have) == 2
    assert len(result.nice_to_have) == 1

    # Check weights and sorting (if we added more they should be sorted)
    assert result.must_have[0].term == "Python"
    assert result.must_have[1].term == "AWS"

    # Check presence in CV
    assert result.must_have[0].present_in_cv is True  # Python matches Python 3
    assert result.must_have[1].present_in_cv is True  # AWS matches Amazon Web Services
    assert result.nice_to_have[0].present_in_cv is False # Kubernetes not in CV

    # Verify LLM call
    mock_llm_client.complete.assert_called_once()
    args, kwargs = mock_llm_client.complete.call_args
    assert kwargs["purpose"] == LLMPurpose.ATS_KEYWORDS
    assert kwargs["model"] == "claude-haiku-4-5-20251001"

def test_check_presence_in_cv():
    cv_text = "I am a Python developer using Py3 and Django. I also use k8s."

    # Case insensitive
    assert _check_presence_in_cv("Python", cv_text) is True
    assert _check_presence_in_cv("python", cv_text) is True

    # Literal match
    assert _check_presence_in_cv("Django", cv_text) is True

    # Synonym match
    assert _check_presence_in_cv("Python", cv_text) is True # via "Py3"
    assert _check_presence_in_cv("Kubernetes", cv_text) is True # via "k8s"

    # No match
    assert _check_presence_in_cv("React", cv_text) is False

def test_check_presence_in_cv_word_boundaries():
    cv_text = "Experience with Java and Javascript."

    # Should match Java
    assert _check_presence_in_cv("Java", cv_text) is True

    # Should not match 'Script' if looking for 'Script' as whole word
    # (Actually my implementation uses \b so it should behave)
    assert _check_presence_in_cv("Script", cv_text) is False
    assert _check_presence_in_cv("Javascript", cv_text) is True

@pytest.mark.asyncio
async def test_extract_ats_keywords_sorting(mock_job):
    mock_llm_client = MagicMock()
    mock_llm_client.complete = AsyncMock(return_value=LLMResponse(
        text='{"must_have": [{"term": "LowWeight", "category": "technical", "weight": 1}, {"term": "HighWeight", "category": "technical", "weight": 10}], "nice_to_have": []}',
        model="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.001,
        duration_ms=500,
        stop_reason="end_turn"
    ))

    result = await extract_ats_keywords(mock_job, mock_llm_client)

    assert result.must_have[0].term == "HighWeight"
    assert result.must_have[1].term == "LowWeight"
