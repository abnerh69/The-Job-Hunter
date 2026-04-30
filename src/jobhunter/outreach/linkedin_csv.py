"""
Robust parser for LinkedIn export CSVs and generic CSVs.
"""

import csv
import io
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)


class LinkedInCSVParser:
    """
    Parses LinkedIn Connections export CSV.
    Standard columns: First Name, Last Name, URL, Email Address, Company, Position, Connected On
    """

    # Potential variations of column names
    COLUMN_MAPPING = {
        "name": ["Name", "Nombre completo", "name"],
        "first_name": ["First Name", "Nombre", "first_name"],
        "last_name": ["Last Name", "Apellidos", "last_name"],
        "linkedin_url": ["URL", "LinkedIn URL", "Perfil de LinkedIn", "linkedin_url"],
        "email": ["Email Address", "Dirección de correo electrónico", "Email", "email"],
        "company": ["Company", "Empresa", "Organización", "company"],
        "position": ["Position", "Cargo", "Puesto", "position", "role"],
        "quality_score": ["quality_score", "Score"],
    }

    @classmethod
    def parse(cls, content: str, mapping: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
        """
        Parses the CSV content and returns a list of normalized contact dictionaries.
        """
        contacts = []
        try:
            # LinkedIn CSVs often have a few header lines or notes.
            # We look for the line that has "First Name" and "Last Name".
            lines = content.splitlines()
            header_index = -1
            for i, line in enumerate(lines):
                if (
                    ("First Name" in line and "Last Name" in line)
                    or ("Name" in line and "URL" in line)
                    or ("name" in line and "linkedin_url" in line)
                    or (mapping and any(v in line for v in mapping.values()))
                ):
                    header_index = i
                    break

            if header_index == -1:
                # Try reading directly if no clear header found
                header_index = 0

            csv_content = "\n".join(lines[header_index:])
            reader = csv.DictReader(io.StringIO(csv_content))

            for row_num, row in enumerate(reader, start=header_index + 1):
                normalized = cls._normalize_row(row, mapping)

                # Validation: Name and URL are mandatory
                name = normalized.get("name")
                url = normalized.get("linkedin_url")

                if not name or not url:
                    logger.warning(
                        "skipping_invalid_csv_row",
                        row_num=row_num,
                        has_name=bool(name),
                        has_url=bool(url),
                    )
                    continue

                contacts.append(normalized)

        except Exception as e:
            logger.error("csv_parsing_failed", error=str(e))
            raise

        return contacts

    @classmethod
    def _normalize_row(
        cls, row: Dict[str, str], custom_mapping: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Maps raw CSV columns to internal contact fields.
        """
        res: Dict[str, Any] = {}

        def get_val(internal_key: str) -> Optional[str]:
            # 1. Check custom mapping
            if custom_mapping and internal_key in custom_mapping:
                val = row.get(custom_mapping[internal_key])
                if val:
                    return val.strip()

            # 2. Check standard mapping
            for raw_col in cls.COLUMN_MAPPING.get(internal_key, []):
                val = row.get(raw_col)
                if val:
                    return val.strip()
            return None

        name = get_val("name")
        if not name:
            first_name = get_val("first_name") or ""
            last_name = get_val("last_name") or ""
            name = f"{first_name} {last_name}".strip()

        res["name"] = name or "Unknown"
        res["linkedin_url"] = get_val("linkedin_url")
        res["email"] = get_val("email")
        res["company"] = get_val("company")
        res["role"] = get_val("position")

        quality_score = get_val("quality_score")
        if quality_score:
            try:
                res["quality_score"] = int(quality_score)
            except ValueError:
                pass

        return res
