import re
from pathlib import Path

from pydantic import BaseModel

from jobhunter.config import Settings


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
    Represents a parsed CV variant.

    Attributes:
        name: The name of the variant (e.g., 'ai_python').
        path: The filesystem path to the CV file.
        summary: A professional summary.
        stack_primary: List of primary technologies.
        stack_secondary: List of secondary technologies.
        experience: List of work experiences.
        skills: List of additional skills.
        raw_markdown: The full raw content of the markdown file.
    """

    name: str
    path: Path
    summary: str
    stack_primary: list[str]
    stack_secondary: list[str]
    experience: list[Experience]
    skills: list[str]
    raw_markdown: str


def list_available_variants(settings: Settings | None = None) -> list[str]:
    """
    Lists the names of available CV variants.

    It looks into the configured CV_VARIANTS_DIR and the fallback cv_variants/ directory.
    Variants are identified by .md or .template.md extensions.

    Args:
        settings: Application settings.

    Returns:
        A list of variant names.
    """
    if settings is None:
        settings = Settings()  # type: ignore[call-arg]

    search_dirs = [settings.CV_VARIANTS_DIR, Path("cv_variants")]
    variants = set()

    for directory in search_dirs:
        if directory.exists() and directory.is_dir():
            for file in directory.glob("*.md"):
                # Remove .template.md or .md extension
                name = file.name
                if name.endswith(".template.md"):
                    name = name[: -len(".template.md")]
                elif name.endswith(".md"):
                    name = name[: -len(".md")]
                variants.add(name)

    return sorted(list(variants))


def load_cv(variant_name: str, settings: Settings | None = None) -> CVVariant:
    """
    Loads and parses a CV variant by name.

    It first tries to find variant_name.md in CV_VARIANTS_DIR,
    then variant_name.template.md in CV_VARIANTS_DIR,
    then falls back to cv_variants/ directory with the same logic.

    Args:
        variant_name: The name of the variant to load.
        settings: Application settings.

    Returns:
        A CVVariant object.

    Raises:
        FileNotFoundError: If the CV variant file is not found.
        ValueError: If the CV file is malformed.
    """
    if settings is None:
        settings = Settings()  # type: ignore[call-arg]

    search_dirs = [settings.CV_VARIANTS_DIR, Path("cv_variants")]
    cv_path: Path | None = None

    for directory in search_dirs:
        # Try exact .md first
        p = directory / f"{variant_name}.md"
        if p.exists():
            cv_path = p
            break
        # Try .template.md
        p = directory / f"{variant_name}.template.md"
        if p.exists():
            cv_path = p
            break

    if cv_path is None:
        raise FileNotFoundError(f"CV variant '{variant_name}' not found.")

    with open(cv_path, "r", encoding="utf-8") as f:
        content = f.read()

    return _parse_cv_markdown(variant_name, cv_path, content)


def _parse_cv_markdown(name: str, path: Path, content: str) -> CVVariant:
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
        path=path,
        summary=summary,
        stack_primary=stack_primary,
        stack_secondary=stack_secondary,
        experience=experience,
        skills=skills,
        raw_markdown=content,
    )
