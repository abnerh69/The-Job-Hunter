import io
import json
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import structlog
from docx import Document
from jinja2 import Template
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.enums import LLMPurpose
from jobhunter.llm.anthropic_client import AnthropicLLMClient

logger = structlog.get_logger(__name__)


class ResumeIngestionError(Exception):
    """Exception raised when resume ingestion fails."""

    def __init__(self, message: str, raw_text: str | None = None, raw_response: str | None = None):
        super().__init__(message)
        self.raw_text = raw_text
        self.raw_response = raw_response


class ParsedExperience(BaseModel):
    """Structured experience data from a resume."""

    role: str
    company: str
    dates: str
    bullets: list[str] = Field(default_factory=list)


class ParsedEducation(BaseModel):
    """Structured education data from a resume."""

    degree: str
    institution: str
    dates: str
    description: str | None = None


class ResumeData(BaseModel):
    """Structured data from a resume."""

    name: str
    email: str | None = None
    phone: str | None = None
    location_raw: str | None = None
    summary: str | None = None
    experiences: list[ParsedExperience] = Field(default_factory=list)
    educations: list[ParsedEducation] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    detected_seniority: str | None = None  # "junior" / "mid" / "senior" / "staff"
    detected_years_experience: int | None = None
    detected_primary_stack: list[str] = Field(default_factory=list)
    raw_text: str


async def ingest_resume(
    file_bytes: bytes, mime_type: str, session: Session | None = None
) -> ResumeData:
    """
    Ingest a resume from bytes and return structured ResumeData.

    Args:
        file_bytes: The resume file content as bytes.
        mime_type: The MIME type of the file.
        session: Optional SQLAlchemy session for LLM call tracking.

    Returns:
        A ResumeData object.

    Raises:
        ResumeIngestionError: If ingestion or parsing fails.
    """
    # 1. Extract text
    try:
        raw_text = _extract_text(file_bytes, mime_type)
    except Exception as e:
        logger.error("resume_text_extraction_failed", mime_type=mime_type, error=str(e))
        raise ResumeIngestionError(f"Failed to extract text from {mime_type}: {str(e)}")

    if not raw_text.strip():
        raise ResumeIngestionError("Extracted text is empty", raw_text=raw_text)

    # 2. LLM Parsing
    settings = Settings()  # type: ignore[call-arg]
    client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    prompt_path = Path("prompts/onboarding/resume_parser/v1.md")
    with open(prompt_path, "r") as f:
        prompt_template = Template(f.read())

    system_prompt = prompt_template.render(resume_text=raw_text)

    try:
        response = await client.complete(
            system=system_prompt,
            user="Parse the resume text provided in the system prompt.",
            model="claude-opus-4-7",
            purpose=LLMPurpose.RESUME_PARSING,
            session=session,
            prompt_version="v1",
        )
    except Exception as e:
        logger.error("resume_llm_parsing_failed", error=str(e))
        raise ResumeIngestionError(f"LLM parsing failed: {str(e)}", raw_text=raw_text)

    # 3. Parse and validate response
    try:
        data = json.loads(response.text)
        resume_data = ResumeData(**data, raw_text=raw_text)
    except Exception as e:
        logger.error("resume_data_validation_failed", error=str(e), raw_response=response.text)
        raise ResumeIngestionError(
            f"Failed to parse LLM response: {str(e)}",
            raw_text=raw_text,
            raw_response=response.text,
        )

    # Mandatory validation: name and experiences
    if not resume_data.name:
        raise ResumeIngestionError(
            "Parsed resume is missing 'name'", raw_text=raw_text, raw_response=response.text
        )
    if not resume_data.experiences:
        raise ResumeIngestionError(
            "Parsed resume is missing 'experiences'", raw_text=raw_text, raw_response=response.text
        )

    return resume_data


def _extract_text(file_bytes: bytes, mime_type: str) -> str:
    """Helper to extract text based on MIME type."""
    if mime_type == "application/pdf":
        pdf = pdfium.PdfDocument(file_bytes)
        text_parts = []
        for i in range(len(pdf)):
            page = pdf.get_page(i)
            text_page = page.get_textpage()
            text_parts.append(text_page.get_text_bounded())
        return "\n".join(text_parts)

    elif mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

    elif mime_type in ["text/markdown", "text/plain"]:
        return file_bytes.decode("utf-8")

    else:
        raise ValueError(f"Unsupported MIME type: {mime_type}")
