import re
import uuid

from pydantic import BaseModel

from jobhunter.db.repos.cv_variant import CVVariantRepo
from sqlalchemy.orm import Session


class Experience(BaseModel):
    """
    Represents a work experience entry in a CV.

    Attributes:
        role: The job title or role.
        company: The name of the company.
        dates: The duration of the employment.
        bullets: A list of accomplishments or responsibilities.
    """

    role: str
    company: str
    dates: str
    bullets: list[str]


class CVVariant(BaseModel):
    """
    Represents a CV variant.

    Attributes:
        name: The name of the variant (e.g., 'ai_python').
        summary: A professional summary.
        stack_primary: List of primary technologies.
        stack_secondary: List of secondary technologies.
        experience: List of work experiences.
        skills: List of additional skills.
        raw_markdown: The full raw content of the markdown file.
    """

    name: str
    summary: str
    stack_primary: list[str]
    stack_secondary: list[str]
    experience: list[Experience]
    skills: list[str]
    raw_markdown: str


def list_available_variants(session: Session, profile_id: uuid.UUID) -> list[str]:
    """
    Lists the names of available CV variants from the database for a given profile.

    Args:
        session: Database session.
        profile_id: ID of the candidate profile.

    Returns:
        A list of variant names.
    """
    repo = CVVariantRepo(session)
    variants = repo.list_by_profile(profile_id)
    return sorted([v.name for v in variants])


def load_cv(session: Session, profile_id: uuid.UUID, variant_name: str) -> CVVariant:
    """
    Loads a CV variant from the database.

    Args:
        session: Database session.
        profile_id: ID of the candidate profile.
        variant_name: The name of the variant to load.

    Returns:
        A CVVariant object.

    Raises:
        FileNotFoundError: If the CV variant is not found in the database.
    """
    repo = CVVariantRepo(session)
    variant_model = repo.get_by_name(profile_id, variant_name)

    if not variant_model:
        raise FileNotFoundError(f"CV variant '{variant_name}' not found for profile {profile_id}.")

    experience = [
        Experience(
            role=exp.role or "N/A",
            company=exp.company or "N/A",
            dates=f"{exp.start_date} - {exp.end_date if exp.end_date else 'Present'}",
            bullets=exp.bullets or [],
        )
        for exp in variant_model.experiences
    ]

    return CVVariant(
        name=variant_model.name,
        summary=variant_model.summary or "",
        stack_primary=variant_model.target_stack or [],
        stack_secondary=[],  # DB schema currently only has target_stack
        experience=experience,
        skills=variant_model.skills or [],
        raw_markdown=variant_model.raw_markdown or "",
    )


def _parse_cv_markdown(name: str, content: str) -> CVVariant:
    """
    Parses the markdown content of a CV.

    The expected structure is:
    ## SUMMARY
    ...
    ## STACK
    - primary: ...
    - secondary: ...
    ## EXPERIENCE
    ### [Role] | [Company] | [Dates]
    - [bullet]
    ## SKILLS
    - ...

    Args:
        name: Variant name.
        path: File path.
        content: Raw markdown content.

    Returns:
        A CVVariant object.

    Raises:
        ValueError: If mandatory sections are missing or malformed.
    """
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)

    summary = ""
    stack_primary: list[str] = []
    stack_secondary: list[str] = []
    experience: list[Experience] = []
    skills: list[str] = []

    for section in sections:
        lines = section.strip().split("\n")
        if not lines:
            continue
        header = lines[0].strip().upper()
        body = "\n".join(lines[1:]).strip()

        if header == "SUMMARY":
            summary = body
        elif header == "STACK":
            for line in body.split("\n"):
                if "primary:" in line.lower():
                    stack_primary = [item.strip() for item in line.split("primary:")[1].split(",")]
                elif "secondary:" in line.lower():
                    stack_secondary = [
                        item.strip() for item in line.split("secondary:")[1].split(",")
                    ]
        elif header == "EXPERIENCE":
            # Split by ### headers
            exp_blocks = re.split(r"^###\s+", body, flags=re.MULTILINE)
            for block in exp_blocks:
                block = block.strip()
                if not block:
                    continue
                block_lines = block.split("\n")
                # First line: [Role] | [Company] | [Dates]
                header_line = block_lines[0].strip()
                parts = [p.strip() for p in header_line.split("|")]
                if len(parts) != 3:
                    continue
                role, company, dates = parts
                bullets = [
                    re.sub(r"^[-*]\s+", "", line).strip()
                    for line in block_lines[1:]
                    if line.strip().startswith(("- ", "* "))
                ]
                experience.append(
                    Experience(role=role, company=company, dates=dates, bullets=bullets)
                )
        elif header == "SKILLS":
            skills = [
                re.sub(r"^[-*]\s+", "", line).strip()
                for line in body.split("\n")
                if line.strip().startswith(("- ", "* "))
            ]

    # Validate mandatory fields
    if not summary:
        raise ValueError(f"CV variant '{name}' is missing a SUMMARY section.")
    if not experience:
        raise ValueError(f"CV variant '{name}' is missing an EXPERIENCE section.")

    return CVVariant(
        name=name,
        summary=summary,
        stack_primary=stack_primary,
        stack_secondary=stack_secondary,
        experience=experience,
        skills=skills,
        raw_markdown=content,
    )
