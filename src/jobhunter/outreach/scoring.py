"""
Heuristic and AI-based scoring for outreach contacts.
"""

import re
from typing import Any, Optional

import structlog
from sqlalchemy.orm import Session

from jobhunter.db.enums import LLMPurpose, OutreachMarket
from jobhunter.db.models import OutreachContact
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.outreach.dach_companies import AI_FRIENDLY_DACH_COMPANIES

logger = structlog.get_logger(__name__)


def infer_market(company_name: Optional[str], position: Optional[str]) -> OutreachMarket:
    """
    Infers the market based on company name or position keywords.
    Best effort: "GmbH" -> Germany, "Ltd" -> UK, etc.
    """
    if not company_name:
        return OutreachMarket.OTHER

    name_lower = company_name.lower()

    if "gmbh" in name_lower or " kgaa" in name_lower or " ag" in name_lower:
        return OutreachMarket.GERMANY

    if " ltd" in name_lower or " plc" in name_lower:
        return OutreachMarket.UK

    if " b.v." in name_lower or " n.v." in name_lower:
        return OutreachMarket.NETHERLANDS

    # Simple keyword check in position as fallback
    if position:
        pos_lower = position.lower()
        if "germany" in pos_lower or "berlin" in pos_lower or "munich" in pos_lower:
            return OutreachMarket.GERMANY
        if "uk " in pos_lower or "london" in pos_lower:
            return OutreachMarket.UK
        if "netherlands" in pos_lower or "amsterdam" in pos_lower:
            return OutreachMarket.NETHERLANDS

    return (
        OutreachMarket.EU_WIDE
    )  # Default to EU_WIDE if it looks European but country not specific


def infer_specialty_stack(position: Optional[str]) -> Optional[str]:
    """
    Infers the specialty stack from position keywords.
    """
    if not position:
        return None

    pos_lower = position.lower()
    stacks = []

    if any(kw in pos_lower for kw in ["python", "django", "fastapi"]):
        stacks.append("Python")
    if any(kw in pos_lower for kw in ["ai", "ml", "machine learning", "llm", "rag"]):
        stacks.append("AI/ML")
    if any(kw in pos_lower for kw in ["flutter", "dart"]):
        stacks.append("Flutter")
    if any(kw in pos_lower for kw in ["fullstack", "full stack"]):
        stacks.append("Fullstack")
    if any(kw in pos_lower for kw in ["backend", "back-end"]):
        stacks.append("Backend")

    return ", ".join(stacks) if stacks else None


def calculate_heuristic_score(contact: OutreachContact, candidate_profile: dict[str, Any]) -> int:
    """
    Calculates a heuristic quality score (1-5) for a contact.

    Rules:
    - +2 if position contains "Tech Recruiter", "Talent Acquisition", "Engineering Recruiter".
    - +2 if position contains "CTO", "VP Engineering", "Head of Engineering".
    - +1 if company is in AI-friendly DACH list.
    - +1 if specialty_stack matches candidate's primary stack.
    - Cap at 5.
    """
    score = 1  # Base score
    role = (contact.role or "").lower()

    # Recruiter rules
    recruiter_keywords = ["tech recruiter", "talent acquisition", "engineering recruiter"]
    if any(kw in role for kw in recruiter_keywords):
        score += 2

    # Senior leadership rules
    leadership_keywords = ["cto", "vp engineering", "head of engineering"]
    if any(kw in role for kw in leadership_keywords):
        score += 2

    # Company rules
    if contact.company and contact.company in AI_FRIENDLY_DACH_COMPANIES:
        score += 1

    # Stack match
    primary_stack = [s.lower() for s in candidate_profile.get("primary_stack", [])]
    contact_stack = (contact.specialty_stack or "").lower()
    if any(s in contact_stack for s in primary_stack):
        score += 1

    return min(score, 5)


async def enrich_contact_with_ai(
    contact: OutreachContact,
    llm_client: AnthropicLLMClient,
    session: Session,
) -> int:
    """
    Uses an LLM (Haiku) to evaluate the contact's relevance.
    Updates the quality_score based on AI feedback.
    """
    system_prompt = (
        "You are a talent acquisition expert helping a senior Python/AI engineer "
        "identify high-value contacts for outreach. "
        "Evaluate the relevance of the following contact on a scale of 1 to 5, "
        "where 5 is highly relevant (Tech Recruiter in target company, CTO in AI startup, etc.) "
        "and 1 is not relevant. "
        "Return ONLY the integer score."
    )

    user_prompt = f"Name: {contact.name}\nPosition: {contact.role}\nCompany: {contact.company}"

    try:
        response = await llm_client.complete(
            system=system_prompt,
            user=user_prompt,
            model="claude-3-haiku-20240307",
            purpose=LLMPurpose.OUTREACH,
            session=session,
            max_tokens=10,
        )

        match = re.search(r"([1-5])", response.text.strip())
        if match:
            return int(match.group(1))
    except Exception as e:
        logger.error("ai_enrichment_failed", contact_id=str(contact.id), error=str(e))

    return contact.quality_score or 1
