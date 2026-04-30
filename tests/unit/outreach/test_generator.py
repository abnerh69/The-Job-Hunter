from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from jobhunter.db.enums import OutreachTemplateType
from jobhunter.db.models import OutreachContact
from jobhunter.llm.anthropic_client import LLMResponse
from jobhunter.outreach.generator import OutreachGenerationError, generate_message


@pytest.fixture
def mock_llm_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock(spec=Session)
    session.execute = MagicMock()
    return session


@pytest.fixture
def sample_contact() -> OutreachContact:
    return OutreachContact(id=uuid4(), name="John Doe", role="Recruiter", company="Tech Corp")


@pytest.mark.asyncio
async def test_generate_message_success(
    mock_llm_client: AsyncMock, mock_session: MagicMock, sample_contact: OutreachContact
) -> None:
    # Setup
    research_notes = "I saw your company is expanding its AI team in Berlin."
    # 100 words message including research notes reference and no forbidden phrases
    body = "Hello John, " + " ".join(["word"] * 90) + " expansion in Berlin. Best regards."

    mock_llm_client.complete.return_value = LLMResponse(
        text=body,
        model="claude-sonnet-4-6",
        input_tokens=100,
        output_tokens=100,
        cost_usd=0.015,
        duration_ms=1000,
        stop_reason="end_turn",
    )

    # Execute
    result = await generate_message(
        contact=sample_contact,
        template_type=OutreachTemplateType.A_INHOUSE,
        research_notes=research_notes,
        llm_client=mock_llm_client,
        session=mock_session,
    )

    # Verify
    assert result.body == body
    word_count = len(result.body.split())
    assert word_count >= 80 and word_count <= 150
    mock_llm_client.complete.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_generate_message_retry_success(
    mock_llm_client: AsyncMock, mock_session: MagicMock, sample_contact: OutreachContact
) -> None:
    # Setup
    research_notes = "Expanding AI team in Berlin."

    # First response fails validation (too short)
    bad_body = "Too short."
    # Second response passes
    good_body = "Hello John, " + " ".join(["word"] * 90) + " expansion in Berlin."

    mock_llm_client.complete.side_effect = [
        LLMResponse(
            text=bad_body,
            model="claude-sonnet-4-6",
            input_tokens=10,
            output_tokens=10,
            cost_usd=0.001,
            duration_ms=500,
            stop_reason="end_turn",
        ),
        LLMResponse(
            text=good_body,
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.015,
            duration_ms=1000,
            stop_reason="end_turn",
        ),
    ]

    # Execute
    result = await generate_message(
        contact=sample_contact,
        template_type=OutreachTemplateType.A_INHOUSE,
        research_notes=research_notes,
        llm_client=mock_llm_client,
        session=mock_session,
    )

    # Verify
    assert result.body == good_body
    assert mock_llm_client.complete.call_count == 2
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_generate_message_retry_exhausted(
    mock_llm_client: AsyncMock, mock_session: MagicMock, sample_contact: OutreachContact
) -> None:
    # Setup
    research_notes = "Expanding AI team in Berlin."
    bad_body = "Still too short."

    mock_llm_client.complete.return_value = LLMResponse(
        text=bad_body,
        model="claude-sonnet-4-6",
        input_tokens=10,
        output_tokens=10,
        cost_usd=0.001,
        duration_ms=500,
        stop_reason="end_turn",
    )

    # Execute & Verify
    with pytest.raises(OutreachGenerationError):
        await generate_message(
            contact=sample_contact,
            template_type=OutreachTemplateType.A_INHOUSE,
            research_notes=research_notes,
            llm_client=mock_llm_client,
            session=mock_session,
        )

    assert mock_llm_client.complete.call_count == 2


@pytest.mark.asyncio
async def test_generate_message_invalid_research_notes(
    mock_llm_client: AsyncMock, mock_session: MagicMock, sample_contact: OutreachContact
) -> None:
    # Execute & Verify
    with pytest.raises(ValueError, match="research_notes must be at least 20 characters long"):
        await generate_message(
            contact=sample_contact,
            template_type=OutreachTemplateType.A_INHOUSE,
            research_notes="Too short",
            llm_client=mock_llm_client,
            session=mock_session,
        )


@pytest.mark.asyncio
async def test_generate_message_forbidden_phrase(
    mock_llm_client: AsyncMock, mock_session: MagicMock, sample_contact: OutreachContact
) -> None:
    # Setup
    research_notes = "Expanding AI team in Berlin."
    # Includes forbidden phrase "I am writing to apply for"
    bad_body = (
        "Hello, I am writing to apply for the role. " + " ".join(["word"] * 80) + " Berlin team."
    )
    good_body = "Hello John, " + " ".join(["word"] * 90) + " expansion in Berlin."

    mock_llm_client.complete.side_effect = [
        LLMResponse(
            text=bad_body,
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.015,
            duration_ms=1000,
            stop_reason="end_turn",
        ),
        LLMResponse(
            text=good_body,
            model="claude-sonnet-4-6",
            input_tokens=100,
            output_tokens=100,
            cost_usd=0.015,
            duration_ms=1000,
            stop_reason="end_turn",
        ),
    ]

    # Execute
    result = await generate_message(
        contact=sample_contact,
        template_type=OutreachTemplateType.A_INHOUSE,
        research_notes=research_notes,
        llm_client=mock_llm_client,
        session=mock_session,
    )

    # Verify
    assert result.body == good_body
    assert mock_llm_client.complete.call_count == 2
