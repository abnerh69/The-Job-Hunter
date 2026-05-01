"""
Core logic for generating outreach messages using LLMs.
"""

import re
from pathlib import Path
from typing import Optional

import structlog
from pydantic import BaseModel
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.db.enums import LLMPurpose, OutreachTemplateType
from jobhunter.db.models import OutreachContact, OutreachMessage
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.outreach.templates import load_outreach_template, render_outreach_template
from jobhunter.analytics.ab_testing import select_variant

logger = structlog.get_logger(__name__)


class MessageGenerationResult(BaseModel):
    """
    Result of an outreach message generation.
    """

    body: str
    subject: Optional[str] = None
    template_version: str
    model: str
    cost_usd: float
    word_count: int


class OutreachGenerationError(Exception):
    """
    Raised when outreach message generation fails after retries.
    """

    pass


async def generate_message(
    contact: OutreachContact,
    template_type: OutreachTemplateType,
    research_notes: str,
    llm_client: AnthropicLLMClient,
    session: Session,
    settings: Optional[Settings] = None,
    template_version: str = "latest",
    parent_message: Optional[OutreachMessage] = None,
    target_language: str = "en",
) -> OutreachMessage:
    """
    Generates an outreach message for a contact using an LLM.

    Args:
        contact: The contact to reach out to.
        template_type: The type of outreach template to use.
        research_notes: Research notes about the contact or company.
        llm_client: The LLM client to use.
        session: Database session.
        settings: Application settings.
        template_version: The version of the template to use.
        parent_message: The parent message if this is a follow-up.
        target_language: The target language for the message (e.g., 'en', 'es').

    Returns:
        The created OutreachMessage object.

    Raises:
        ValueError: If research_notes is too short.
        OutreachGenerationError: If generation fails after retries.
    """
    # 1. Pre-validation
    if not research_notes or len(research_notes) < 20:
        raise ValueError("research_notes must be at least 20 characters long.")

    if settings is None:
        settings = Settings()  # type: ignore[call-arg]

    # 2. A/B test logic: select template version
    # If template_version is 'latest' (default), we check for an active A/B test
    actual_version = template_version
    if template_version == "latest":
        variant = select_variant(session, "outreach_template", contact.id)
        if variant != "default":
            actual_version = variant

    # 3. Load Template
    template = load_outreach_template(template_type, version=actual_version)

    # 3. Load Candidate Profile
    profile_path = Path("prompts/candidate_profile.yaml")
    if not profile_path.exists():
        raise FileNotFoundError(f"Candidate profile not found at {profile_path}")
    candidate_profile_yaml = profile_path.read_text(encoding="utf-8")

    # 4. Prepare Context
    context = {
        "contact_name": contact.name,
        "contact_role": contact.role or "N/A",
        "contact_company": contact.company or "N/A",
        "research_notes": research_notes,
        "candidate_profile_yaml": candidate_profile_yaml,
        "target_language": target_language,
    }

    if template_type == OutreachTemplateType.D_FOLLOWUP and parent_message:
        context["parent_message_body"] = parent_message.body

    # 5. Render prompts
    system_prompt = template.system_prompt
    user_prompt_base = render_outreach_template(template.user_template, context)
    requirements_rendered = render_outreach_template(template.requirements, context)

    # Combine user prompt with requirements
    user_prompt = f"{user_prompt_base}\n\n## REQUIREMENTS\n{requirements_rendered}"

    forbidden_phrases_path = Path("prompts/outreach/forbidden_phrases.txt")
    forbidden_phrases = (
        forbidden_phrases_path.read_text().splitlines() if forbidden_phrases_path.exists() else []
    )
    forbidden_phrases = [p.strip() for p in forbidden_phrases if p.strip()]

    async def call_llm(extra_instruction: str = "") -> MessageGenerationResult:
        final_system = system_prompt
        if extra_instruction:
            final_system += f"\n\nIMPORTANT: {extra_instruction}"

        response = await llm_client.complete(
            system=final_system,
            user=user_prompt,
            model=settings.OUTREACH_MODEL,
            purpose=LLMPurpose.OUTREACH_MESSAGE,
            prompt_version=template.version,
            session=session,
            max_tokens=1000,
        )

        return MessageGenerationResult(
            body=response.text.strip(),
            subject=None,  # Most outreach messages don't have separate subjects in LinkedIn
            template_version=template.version,
            model=settings.OUTREACH_MODEL,
            cost_usd=response.cost_usd,
            word_count=len(response.text.split()),
        )

    def validate(text: str) -> list[str]:
        errors = []
        words = text.split()
        word_count = len(words)
        if word_count < 80 or word_count > 150:
            errors.append(f"Word count {word_count} is outside the allowed range [80, 150].")

        for phrase in forbidden_phrases:
            if phrase.lower() in text.lower():
                errors.append(f"Found forbidden phrase: '{phrase}'")

        # Heuristic check for research notes reference
        # Extract meaningful terms from research_notes (simple approach: split by space and filter short words)
        notes_terms = [t.lower() for t in re.split(r"\W+", research_notes) if len(t) > 3]
        found_ref = False
        for term in notes_terms:
            if term in text.lower():
                found_ref = True
                break

        if not found_ref:
            errors.append("Message does not seem to include any reference to research_notes.")

        return errors

    # Attempt 1
    result = await call_llm()
    errors = validate(result.body)

    if errors:
        logger.warning(
            "outreach_message_validation_failed",
            contact_id=str(contact.id),
            errors=errors,
            attempt=1,
        )
        # Attempt 2: Retry with reinforced instruction
        reinforced_instruction = (
            "Your previous attempt failed validation for the following reasons:\n"
            + "\n".join(f"- {e}" for e in errors)
            + "\n\nPlease rewrite the message strictly following all rules, "
            "especially addressing the issues above and ensuring the reference to research_notes is clear."
        )
        result = await call_llm(extra_instruction=reinforced_instruction)
        final_errors = validate(result.body)

        if final_errors:
            logger.error(
                "outreach_message_validation_failed_final",
                contact_id=str(contact.id),
                errors=final_errors,
                attempt=2,
            )
            raise OutreachGenerationError(
                f"Failed to generate valid outreach message after 2 attempts: {final_errors}"
            )

    # 6. Persistence
    repo = OutreachMessageRepo(session)
    message = repo.create_draft(
        contact_id=contact.id,
        template_type=template_type,
        body=result.body,
        subject=result.subject,
        template_version=result.template_version,
        research_notes=research_notes,
        model_used=result.model,
        cost_usd=result.cost_usd,
        parent_message_id=parent_message.id if parent_message else None,
    )
    session.commit()

    logger.info(
        "outreach_message_generated_and_persisted",
        contact_id=str(contact.id),
        message_id=str(message.id),
        template_type=template_type,
        model=result.model,
        cost_usd=result.cost_usd,
    )

    return message
