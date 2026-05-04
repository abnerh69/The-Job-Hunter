"""migrate_legacy_yaml_and_markdown

Revision ID: 8978759777f4
Revises: cedd137a09ba
Create Date: 2026-05-03 09:00:28.438557

"""

import glob
import json
import os
import re
import shutil
import uuid
from datetime import date, datetime
from typing import Any, Optional, Sequence, Tuple, Union

import sqlalchemy as sa
import structlog
import yaml
from alembic import op
from dateutil import parser  # type: ignore[import-untyped]

# revision identifiers, used by Alembic.
revision: str = "8978759777f4"
down_revision: Union[str, Sequence[str], None] = "cedd137a09ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = structlog.get_logger(__name__)


def _parse_cv_dates(date_str: Optional[str]) -> Tuple[Optional[date], Optional[date]]:
    """Heuristically parses a date range string into start and end dates."""
    if not date_str:
        return None, None

    separators = [r"\s*-\s*", r"\s+to\s+", r"\s*–\s*"]
    parts = []
    for sep in separators:
        if re.search(sep, date_str, re.IGNORECASE):
            parts = re.split(sep, date_str, flags=re.IGNORECASE)
            break

    if not parts:
        try:
            dt = parser.parse(date_str, default=datetime(2000, 1, 1))
            return dt.date(), None
        except (ValueError, OverflowError):
            return None, None

    start_date = None
    end_date = None

    try:
        start_date = parser.parse(parts[0], default=datetime(2000, 1, 1)).date()
    except (ValueError, OverflowError):
        pass

    if len(parts) > 1:
        end_part = parts[1].strip().lower()
        if end_part in ["present", "current", "now", "today"]:
            end_date = None
        else:
            try:
                end_date = parser.parse(parts[1], default=datetime(2000, 1, 1)).date()
            except (ValueError, OverflowError):
                pass
    return start_date, end_date


def _parse_cv_markdown(name: str, content: str) -> dict[str, Any]:
    """Parses the markdown content of a CV."""
    sections = re.split(r"^##\s+", content, flags=re.MULTILINE)

    summary = ""
    stack_primary = []
    stack_secondary = []
    experience = []
    skills = []

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
            exp_blocks = re.split(r"^###\s+", body, flags=re.MULTILINE)
            for block in exp_blocks:
                block = block.strip()
                if not block:
                    continue
                block_lines = block.split("\n")
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
                    {"role": role, "company": company, "dates": dates, "bullets": bullets}
                )
        elif header == "SKILLS":
            skills = [
                re.sub(r"^[-*]\s+", "", line).strip()
                for line in body.split("\n")
                if line.strip().startswith(("- ", "* "))
            ]

    return {
        "name": name,
        "summary": summary,
        "stack_primary": stack_primary,
        "stack_secondary": stack_secondary,
        "experience": experience,
        "skills": skills,
        "raw_markdown": content,
    }


def _archive_file(filepath: str, legacy_dir: str) -> None:
    """Archives a file to the legacy directory."""
    if "_legacy" in filepath:
        return  # Already archived

    if not os.path.exists(legacy_dir):
        os.makedirs(legacy_dir)
    filename = os.path.basename(filepath)
    dest = os.path.join(legacy_dir, filename)
    if os.path.exists(dest):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(legacy_dir, f"{timestamp}_{filename}")
    shutil.move(filepath, dest)


def upgrade() -> None:
    """Upgrade schema."""
    conn = op.get_bind()
    is_sqlite = conn.dialect.name == "sqlite"

    yaml_paths = ["prompts/candidate_profile.yaml"] + glob.glob(
        "prompts/_legacy/*/candidate_profile.yaml"
    )
    cv_variants_globs = [".local/cv_variants/*.md", ".local/cv_variants/_legacy/*/*.md"]

    profile_id = None
    imported_profiles = 0
    imported_variants = 0

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 1. Import Profile
    data = None
    yaml_found_path = None
    for yp in yaml_paths:
        if os.path.exists(yp):
            with open(yp, "r") as f:
                try:
                    data = yaml.safe_load(f)
                    yaml_found_path = yp
                    break
                except Exception:
                    continue

    if data:
        # Check if Legacy Profile already exists (idempotency)
        existing = conn.execute(
            sa.text("SELECT id FROM candidate_profiles WHERE name = 'Legacy Profile'")
        ).fetchone()

        if not existing:
            profile_id = str(uuid.uuid4())
            logger.info("importing_legacy_profile", profile_id=profile_id)

            # Parse years_experience
            years_exp_str = str(data.get("years_experience", "0"))
            years_exp = 0
            match = re.search(r"(\d+)", years_exp_str)
            if match:
                years_exp = int(match.group(1))

            location_legal = data.get("location_legal", {})
            timezone = data.get("timezone", {})

            def prepare_json(val: Any) -> Any:
                """For JSONB columns, always encode as JSON string for sa.text()."""
                if val is None:
                    return None
                return json.dumps(val)

            def prepare_array(val: Any) -> Any:
                """For ARRAY columns, encode as JSON string for SQLite, keep as list for Postgres."""
                if val is None:
                    return None
                if is_sqlite:
                    return json.dumps(val)
                return val

            def truncate(val: Optional[str], length: int = 50) -> Optional[str]:
                if val is None:
                    return None
                return val[:length]

            conn.execute(
                sa.text("""
                    INSERT INTO candidate_profiles (
                        id, name, is_active, seniority, years_experience,
                        country, work_authorization, timezone_home,
                        overlap_max_hours_cet, preferred_overlap_cet,
                        primary_stack, secondary_stack, domains,
                        languages, compensation, contract_preferences,
                        hard_blockers, soft_negatives, positive_signals,
                        created_at, updated_at
                    ) VALUES (
                        :id, :name, :is_active, :seniority, :years_experience,
                        :country, :work_authorization, :timezone_home,
                        :overlap_max_hours_cet, :preferred_overlap_cet,
                        :primary_stack, :secondary_stack, :domains,
                        :languages, :compensation, :contract_preferences,
                        :hard_blockers, :soft_negatives, :positive_signals,
                        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                """),
                {
                    "id": profile_id,
                    "name": "Legacy Profile",
                    "is_active": True,
                    "seniority": truncate(data.get("seniority")),
                    "years_experience": years_exp,
                    "country": truncate(location_legal.get("country")),
                    "work_authorization": location_legal.get("work_authorization"),
                    "timezone_home": truncate(timezone.get("home")),
                    "overlap_max_hours_cet": timezone.get("overlap_max_acceptable_hours_with_CET"),
                    "preferred_overlap_cet": timezone.get("preferred_overlap_CET"),
                    "primary_stack": prepare_array(data.get("primary_stack")),
                    "secondary_stack": prepare_array(data.get("secondary_stack")),
                    "domains": prepare_array(data.get("domains")),
                    "languages": prepare_json(data.get("language")),
                    "compensation": prepare_json(data.get("compensation")),
                    "contract_preferences": prepare_array(data.get("contract_preferences")),
                    "hard_blockers": prepare_array(data.get("hard_blockers")),
                    "soft_negatives": prepare_array(data.get("soft_negatives")),
                    "positive_signals": prepare_array(data.get("positive_signals")),
                },
            )
            imported_profiles += 1
            # Archive profile
            if yaml_found_path:
                _archive_file(yaml_found_path, f"prompts/_legacy/{timestamp}/")
        else:
            profile_id = str(existing[0])

    # 2. Import CV Variants
    if profile_id:
        variant_files = []
        for g in cv_variants_globs:
            variant_files.extend(glob.glob(g))

        for vf in variant_files:
            filename = os.path.basename(vf)
            name = os.path.splitext(filename)[0]

            # Check if variant already exists
            existing_v = conn.execute(
                sa.text("SELECT id FROM cv_variants WHERE profile_id = :pid AND name = :name"),
                {"pid": profile_id, "name": name},
            ).fetchone()

            if not existing_v:
                logger.info("importing_legacy_variant", name=name, path=vf)
                with open(vf, "r") as f:
                    content = f.read()

                v_data = _parse_cv_markdown(name, content)
                v_id = str(uuid.uuid4())

                # Infer keywords
                keywords = name.split("_")
                if "ai" in keywords:
                    if "ml" not in keywords:
                        keywords.append("ml")

                def prepare_json_v(val: Any) -> Any:
                    if val is None:
                        return None
                    return json.dumps(val)

                def prepare_array_v(val: Any) -> Any:
                    if val is None:
                        return None
                    if is_sqlite:
                        return json.dumps(val)
                    return val

                def truncate_v(val: Optional[str], length: int = 50) -> Optional[str]:
                    if val is None:
                        return None
                    return val[:length]

                conn.execute(
                    sa.text("""
                        INSERT INTO cv_variants (
                            id, profile_id, name, display_name,
                            target_role_keywords, target_stack,
                            summary, skills, raw_markdown,
                            created_at, updated_at
                        ) VALUES (
                            :id, :profile_id, :name, :display_name,
                            :target_role_keywords, :target_stack,
                            :summary, :skills, :raw_markdown,
                            CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "id": v_id,
                        "profile_id": profile_id,
                        "name": truncate_v(name),
                        "display_name": name.replace("_", " ").title()[:100],
                        "target_role_keywords": prepare_array_v(keywords),
                        "target_stack": prepare_array_v(v_data["stack_primary"]),
                        "summary": v_data["summary"],
                        "skills": prepare_array_v(v_data["skills"]),
                        "raw_markdown": v_data["raw_markdown"],
                    },
                )

                # Experiences
                for idx, exp in enumerate(v_data["experience"]):
                    start_date, end_date = _parse_cv_dates(exp["dates"])
                    conn.execute(
                        sa.text("""
                            INSERT INTO cv_variant_experiences (
                                id, cv_variant_id, role, company,
                                start_date, end_date, bullets, sort_order
                            ) VALUES (
                                :id, :v_id, :role, :company,
                                :start_date, :end_date, :bullets, :sort_order
                            )
                        """),
                        {
                            "id": str(uuid.uuid4()),
                            "v_id": v_id,
                            "role": truncate_v(exp["role"], 200),
                            "company": truncate_v(exp["company"], 200),
                            "start_date": start_date,
                            "end_date": end_date,
                            "bullets": prepare_array_v(exp["bullets"]),
                            "sort_order": idx,
                        },
                    )

                imported_variants += 1
                # Archive variant
                _archive_file(vf, f".local/cv_variants/_legacy/{timestamp}/")

    if imported_profiles > 0 or imported_variants > 0:
        print(f"\nImported {imported_profiles} legacy profile + {imported_variants} CV variants.")
        print(
            f"Originals archived in prompts/_legacy/{timestamp}/ and .local/cv_variants/_legacy/{timestamp}/."
        )


def downgrade() -> None:
    """Downgrade schema."""
    conn = op.get_bind()
    # Delete the legacy profile. Cascade deletes should handle variants and experiences.
    # Note: This only deletes the DB records, not the files in _legacy.
    conn.execute(sa.text("DELETE FROM candidate_profiles WHERE name = 'Legacy Profile'"))
    logger.info("deleted_legacy_profile_records")
