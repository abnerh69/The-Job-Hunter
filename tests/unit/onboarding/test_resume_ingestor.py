from unittest.mock import patch

import pytest

from jobhunter.onboarding.resume_ingestor import ResumeIngestionError, ingest_resume


@pytest.mark.asyncio
async def test_ingest_resume_markdown() -> None:
    with open("tests/fixtures/resumes/resume.md", "rb") as f:
        file_bytes = f.read()

    with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"

        resume_data = await ingest_resume(file_bytes, "text/markdown")

        assert resume_data.name == "Jane Doe"  # Mock response from AnthropicLLMClient
        assert resume_data.email == "jane@example.com"
        assert len(resume_data.experiences) > 0
        assert "John Doe" in resume_data.raw_text


@pytest.mark.asyncio
async def test_ingest_resume_pdf() -> None:
    with open("tests/fixtures/resumes/resume.pdf", "rb") as f:
        file_bytes = f.read()

    with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"

        resume_data = await ingest_resume(file_bytes, "application/pdf")

        assert resume_data.name == "Jane Doe"
        assert "John Doe" in resume_data.raw_text


@pytest.mark.asyncio
async def test_ingest_resume_docx() -> None:
    with open("tests/fixtures/resumes/resume.docx", "rb") as f:
        file_bytes = f.read()

    with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
        mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"

        resume_data = await ingest_resume(
            file_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

        assert resume_data.name == "Jane Doe"
        assert "John Doe" in resume_data.raw_text


@pytest.mark.asyncio
async def test_ingest_resume_unsupported_mime() -> None:
    with pytest.raises(ResumeIngestionError, match="Unsupported MIME type"):
        await ingest_resume(b"dummy content", "application/zip")


@pytest.mark.asyncio
async def test_ingest_resume_empty_text() -> None:
    # Empty PDF or similar could result in empty text
    with patch("jobhunter.onboarding.resume_ingestor._extract_text", return_value="  "):
        with pytest.raises(ResumeIngestionError, match="Extracted text is empty"):
            await ingest_resume(b"dummy", "text/plain")


@pytest.mark.asyncio
async def test_ingest_resume_llm_failure() -> None:
    with patch(
        "jobhunter.onboarding.resume_ingestor.AnthropicLLMClient.complete",
        side_effect=Exception("LLM error"),
    ):
        with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"
            with pytest.raises(ResumeIngestionError, match="LLM parsing failed"):
                await ingest_resume(b"John Doe resume", "text/plain")


@pytest.mark.asyncio
async def test_ingest_resume_invalid_json_response() -> None:
    with patch("jobhunter.onboarding.resume_ingestor.AnthropicLLMClient.complete") as mock_complete:
        mock_complete.return_value.text = "Not a JSON"
        with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"
            with pytest.raises(ResumeIngestionError, match="Failed to parse LLM response"):
                await ingest_resume(b"John Doe resume", "text/plain")


@pytest.mark.asyncio
async def test_ingest_resume_missing_mandatory_fields() -> None:
    with patch("jobhunter.onboarding.resume_ingestor.AnthropicLLMClient.complete") as mock_complete:
        # Missing experiences
        mock_complete.return_value.text = '{"name": "Jane Doe", "experiences": []}'
        with patch("jobhunter.onboarding.resume_ingestor.Settings") as mock_settings:
            mock_settings.return_value.ANTHROPIC_API_KEY.get_secret_value.return_value = "dummy"
            with pytest.raises(
                ResumeIngestionError, match="Parsed resume is missing 'experiences'"
            ):
                await ingest_resume(b"John Doe resume", "text/plain")
