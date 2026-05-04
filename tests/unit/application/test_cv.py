import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from jobhunter.application.cv import list_available_variants, load_cv
from jobhunter.db.models import CVVariant, CVVariantExperience


@pytest.fixture
def mock_session() -> MagicMock:
    return MagicMock()


@pytest.fixture
def profile_id() -> uuid.UUID:
    return uuid.uuid4()


def test_list_available_variants(mock_session: MagicMock, profile_id: uuid.UUID) -> None:
    # Setup mock return value
    variant1 = MagicMock(spec=CVVariant)
    variant1.name = "expert"
    variant2 = MagicMock(spec=CVVariant)
    variant2.name = "ai"

    mock_session.scalars.return_value.all.return_value = [variant1, variant2]

    variants = list_available_variants(mock_session, profile_id)

    assert "expert" in variants
    assert "ai" in variants
    assert len(variants) == 2


def test_load_cv_success(mock_session: MagicMock, profile_id: uuid.UUID) -> None:
    # Setup mock return value
    variant = MagicMock(spec=CVVariant)
    variant.name = "ai_python"
    variant.summary = "Experienced dev."
    variant.target_stack = ["Python", "Go"]
    variant.skills = ["Testing", "Architecture"]
    variant.raw_markdown = "## SUMMARY\n..."

    exp = MagicMock(spec=CVVariantExperience)
    exp.role = "Senior Dev"
    exp.company = "Tech Corp"
    exp.start_date = date(2020, 1, 1)
    exp.end_date = date(2024, 1, 1)
    exp.bullets = ["Led team.", "Built stuff."]

    variant.experiences = [exp]

    mock_session.scalar.return_value = variant

    cv = load_cv(mock_session, profile_id, "ai_python")

    assert cv.name == "ai_python"
    assert cv.summary == "Experienced dev."
    assert cv.stack_primary == ["Python", "Go"]
    assert len(cv.experience) == 1
    assert cv.experience[0].role == "Senior Dev"
    assert cv.experience[0].company == "Tech Corp"
    assert cv.experience[0].bullets == ["Led team.", "Built stuff."]
    assert cv.skills == ["Testing", "Architecture"]


def test_load_cv_not_found(mock_session: MagicMock, profile_id: uuid.UUID) -> None:
    mock_session.scalar.return_value = None

    with pytest.raises(FileNotFoundError):
        load_cv(mock_session, profile_id, "non_existent")
