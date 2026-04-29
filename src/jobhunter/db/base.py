from typing import Any

from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Base class for all SQLAlchemy models.
    Uses SQLAlchemy 2.0 style DeclarativeBase.
    """

    type_annotation_map = {
        dict[str, Any]: JSONB().with_variant(JSON(), "sqlite"),
    }
