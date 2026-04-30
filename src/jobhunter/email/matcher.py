import uuid
import structlog
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from jobhunter.db.enums import (
    ApplicationStatus,
    EmailMatchStatus,
    LLMPurpose,
    OutreachMessageStatus,
)
from jobhunter.db.models import Application, Job, OutreachContact, OutreachMessage
from jobhunter.email.schemas import GmailMessageDetail, MatchResult
from jobhunter.llm.anthropic_client import AnthropicLLMClient

logger = structlog.get_logger(__name__)

MARKETING_MARKERS = ["noreply", "no-reply", "newsletter"]
UNSUBSCRIBE_MARKER = "unsubscribe"
SUBJECT_KEYWORDS = ["re:", "application", "interview", "next steps", "your application"]


async def match_email(
    email: GmailMessageDetail, session: Session, llm_client: AnthropicLLMClient
) -> MatchResult:
    """
    Matches an email to an application or outreach message using heuristics and AI.

    Args:
        email: The Gmail message detail.
        session: SQLAlchemy session.
        llm_client: Anthropic LLM client.

    Returns:
        MatchResult: The result of the matching process.
    """
    # Heuristic 3: Marketing Detector
    from_email = email.from_email.lower()
    body_text = (email.body_text or "").lower()
    body_html = (email.body_html or "").lower()

    is_marketing = any(marker in from_email for marker in MARKETING_MARKERS) or (
        UNSUBSCRIBE_MARKER in body_text or UNSUBSCRIBE_MARKER in body_html
    )

    if is_marketing:
        logger.info("marketing_email_detected", gmail_id=email.id, from_email=from_email)
        return MatchResult(
            match_status=EmailMatchStatus.IGNORED_MARKETING,
            confidence=1.0,
            reasoning="Marketing markers detected in sender address or body.",
        )

    # Heuristic 1: Domain Match
    domain = from_email.split("@")[-1] if "@" in from_email else ""

    match_status = EmailMatchStatus.UNMATCHED
    application_id = None
    outreach_message_id = None
    confidence = 0.0
    reasoning = ""

    if domain:
        # Search for applications via Job.company similarity or Application.contact_email
        # Note: simplistic company match for now
        app_stmt = (
            select(Application)
            .join(Job)
            .where(
                or_(
                    Application.contact_email.ilike(f"%@{domain}"),
                    Job.company.ilike(f"{domain.split('.')[0]}%"),
                    Job.company.ilike(f"% {domain.split('.')[0]}%"),
                )
            )
        )
        apps = session.scalars(app_stmt).all()

        # Search for outreach contacts
        contact_stmt = select(OutreachContact).where(
            or_(
                OutreachContact.email.ilike(f"%@{domain}"),
                OutreachContact.company.ilike(f"%{domain.split('.')[0]}%"),
            )
        )
        contacts = session.scalars(contact_stmt).all()

        if len(apps) == 1 and not contacts:
            application_id = apps[0].id
            confidence = 0.9
            match_status = EmailMatchStatus.AUTO_MATCHED
            reasoning = f"Unique application match found for domain: {domain}"
        elif len(contacts) == 1 and not apps:
            # For outreach, we need to find the latest sent message to this contact
            msg_stmt = (
                select(OutreachMessage)
                .where(
                    OutreachMessage.contact_id == contacts[0].id,
                    OutreachMessage.status == OutreachMessageStatus.SENT,
                )
                .order_by(OutreachMessage.sent_at.desc())
                .limit(1)
            )
            latest_msg = session.scalar(msg_stmt)
            if latest_msg:
                outreach_message_id = latest_msg.id
                confidence = 0.9
                match_status = EmailMatchStatus.AUTO_MATCHED
                reasoning = f"Unique outreach match found for domain: {domain}"

    # Heuristic 2: Subject keyword match
    if (application_id or outreach_message_id) and confidence >= 0.9:
        subject = (email.subject or "").lower()
        if any(keyword in subject for keyword in SUBJECT_KEYWORDS):
            confidence = 0.95
            reasoning += " + Subject keywords matched."

    # AI Escalation (if confidence < 0.8)
    if confidence < 0.8:
        import json

        # Get candidate data for context
        # In a real scenario, we'd limit this to recent ones
        candidate_apps = session.scalars(
            select(Application).join(Job).order_by(Application.applied_at.desc()).limit(5)
        ).all()
        candidate_outreach = session.scalars(
            select(OutreachContact).order_by(OutreachContact.last_contacted_at.desc()).limit(5)
        ).all()

        candidates_info = []
        for app in candidate_apps:
            candidates_info.append(
                {
                    "type": "application",
                    "id": str(app.id),
                    "company": app.job.company,
                    "title": app.job.title,
                    "domain": (app.contact_email.split("@")[-1] if app.contact_email else ""),
                }
            )
        for contact in candidate_outreach:
            candidates_info.append(
                {
                    "type": "outreach",
                    "id": str(contact.id),
                    "name": contact.name,
                    "company": (contact.company or ""),
                    "domain": (contact.email.split("@")[-1] if contact.email else ""),
                }
            )

        system_prompt = """You are an email matching assistant for a job search tracker.
Your task is to match an incoming email to either a job application or an outreach contact.
Respond ONLY with a JSON object containing:
- match_status: "ai_matched" if found, "unmatched" otherwise.
- application_id: UUID if matched to an application, null otherwise.
- outreach_contact_id: UUID if matched to an outreach contact, null otherwise.
- confidence: float between 0 and 1.
- reasoning: short string explaining the match.
"""
        user_prompt = f"""Incoming Email:
Subject: {email.subject}
Snippet: {email.snippet}
Sender: {email.from_email}

Candidates:
{json.dumps(candidates_info, indent=2)}
"""
        try:
            llm_response = await llm_client.complete(
                system=system_prompt,
                user=user_prompt,
                model="claude-3-haiku-20240307",
                purpose=LLMPurpose.OUTREACH,  # Using OUTREACH as a generic purpose for now
                session=session,
            )

            result_data = json.loads(llm_response.text)

            if result_data.get("match_status") == "ai_matched":
                match_status = EmailMatchStatus.AI_MATCHED
                confidence = result_data.get("confidence", 0.0)
                reasoning = result_data.get("reasoning", "AI Matched.")

                if result_data.get("application_id"):
                    application_id = uuid.UUID(str(result_data["application_id"]))
                elif result_data.get("outreach_contact_id"):
                    contact_id = uuid.UUID(str(result_data["outreach_contact_id"]))
                    # Find latest sent message for this contact
                    msg_stmt = (
                        select(OutreachMessage)
                        .where(
                            OutreachMessage.contact_id == contact_id,
                            OutreachMessage.status == OutreachMessageStatus.SENT,
                        )
                        .order_by(OutreachMessage.sent_at.desc())
                        .limit(1)
                    )
                    latest_msg = session.scalar(msg_stmt)
                    if latest_msg:
                        outreach_message_id = latest_msg.id

        except Exception as e:
            logger.error("ai_escalation_failed", error=str(e))

    # Status Change Inference
    suggested_change = None
    if match_status != EmailMatchStatus.UNMATCHED:
        full_text = (
            f"{(email.subject or '')} {(email.snippet or '')} {(email.body_text or '')}".lower()
        )

        if application_id:
            logger.debug(
                "inferring_status_change", app_id=application_id, full_text=full_text[:100]
            )
            if any(
                kw in full_text
                for kw in ["interview", "schedule a call", "speak with you", "availability"]
            ):
                suggested_change = {
                    "status": ApplicationStatus.SCREENING,
                    "note": "Possible interview request detected.",
                }
            elif any(
                kw in full_text
                for kw in [
                    "rejected",
                    "move forward with",
                    "moved forward with",
                    "regret to inform",
                    "not to move forward",
                ]
            ):
                suggested_change = {
                    "status": ApplicationStatus.REJECTED,
                    "note": "Rejection email detected.",
                }
            elif any(
                kw in full_text
                for kw in ["offer", "compensation package", "contract", "congratulations"]
            ):
                suggested_change = {
                    "status": ApplicationStatus.OFFER,
                    "note": "Offer email detected.",
                }

        elif outreach_message_id:
            # For outreach, if it's not marketing and we matched it, it's likely a reply
            suggested_change = {
                "status": OutreachMessageStatus.REPLIED,
                "note": "Direct reply to outreach message.",
            }

    return MatchResult(
        match_status=match_status,
        application_id=application_id,
        outreach_message_id=outreach_message_id,
        confidence=confidence,
        reasoning=reasoning or "No match found.",
        suggested_change=suggested_change,
    )
