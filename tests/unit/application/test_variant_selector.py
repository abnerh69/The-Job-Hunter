import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock
from jobhunter.db.models import Job, CVVariant
from jobhunter.application.variant_selector import recommend_cv_variant
from jobhunter.application import NoCVVariantsAvailableError
from jobhunter.llm.anthropic_client import AnthropicLLMClient


@pytest.mark.asyncio
async def test_recommend_zero_variants() -> None:
    job = Job(title="Dev", description="Desc")
    with pytest.raises(NoCVVariantsAvailableError):
        await recommend_cv_variant(job, [])


@pytest.mark.asyncio
async def test_recommend_one_variant() -> None:
    job = Job(title="Dev", description="Desc")
    v_id = uuid.uuid4()
    v = CVVariant(id=v_id, name="only_one", display_name="Only One")

    recommendation = await recommend_cv_variant(job, [v])

    assert recommendation.variant_name == "only_one"
    assert recommendation.variant_id == v_id
    assert recommendation.confidence == 1.0
    assert "Only one" in recommendation.reasoning


@pytest.mark.asyncio
async def test_recommend_heuristic_clear_match() -> None:
    job = Job(title="Python AI Engineer", description="Using PyTorch and LLMs")

    v1 = CVVariant(
        id=uuid.uuid4(),
        name="ai_python",
        target_role_keywords=["python", "ai"],
        target_stack=["pytorch", "llm"],
    )
    v2 = CVVariant(
        id=uuid.uuid4(),
        name="flutter",
        target_role_keywords=["mobile"],
        target_stack=["dart", "flutter"],
    )

    recommendation = await recommend_cv_variant(job, [v1, v2])

    assert recommendation.variant_name == "ai_python"
    assert recommendation.confidence >= 0.4
    assert "Heuristic match" in recommendation.reasoning


@pytest.mark.asyncio
async def test_recommend_llm_fallback_on_tie() -> None:
    job = Job(title="Software Engineer", description="Generic job description")

    # Both will have 0 score -> Tie
    v1 = CVVariant(
        id=uuid.uuid4(), name="v1", target_role_keywords=["flutter"], target_stack=["dart"]
    )
    v2 = CVVariant(
        id=uuid.uuid4(), name="v2", target_role_keywords=["react"], target_stack=["typescript"]
    )

    llm_client = MagicMock(spec=AnthropicLLMClient)
    llm_client.complete = AsyncMock()

    import json

    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {"variant_name": "v2", "confidence": 0.8, "reasoning": "LLM chose v2"}
    )
    llm_client.complete.return_value = mock_response

    recommendation = await recommend_cv_variant(job, [v1, v2], llm_client=llm_client)

    assert recommendation.variant_name == "v2"
    assert recommendation.confidence == 0.8
    assert "[LLM Fallback]" in recommendation.reasoning


@pytest.mark.asyncio
async def test_recommend_llm_fallback_on_low_confidence() -> None:
    # Match only 1 out of 10 keywords -> score 0.1 < 0.4
    job = Job(title="Python", description="Just python")

    v1 = CVVariant(
        id=uuid.uuid4(),
        name="v1",
        target_role_keywords=["k1", "k2", "k3", "k4", "k5", "k6", "k7", "k8", "k9", "python"],
    )

    # We need at least 2 variants to trigger fallback logic that isn't the "only one" case
    v2 = CVVariant(id=uuid.uuid4(), name="v2", target_role_keywords=["something_else"])

    llm_client = MagicMock(spec=AnthropicLLMClient)
    llm_client.complete = AsyncMock()

    import json

    mock_response = MagicMock()
    mock_response.text = json.dumps(
        {"variant_name": "v1", "confidence": 0.9, "reasoning": "LLM is sure"}
    )
    llm_client.complete.return_value = mock_response

    recommendation = await recommend_cv_variant(job, [v1, v2], llm_client=llm_client)

    assert recommendation.variant_name == "v1"
    assert recommendation.confidence == 0.9
    assert "[LLM Fallback]" in recommendation.reasoning
