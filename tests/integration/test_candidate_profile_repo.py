import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from jobhunter.db.models import (
    CandidateProfile,
    CVVariant,
    CVVariantExperience,
)
from jobhunter.db.repos.candidate_profile import CandidateProfileRepo
from jobhunter.db.repos.cv_variant import CVVariantRepo


@pytest.fixture
def profile_repo(db_session: Session) -> CandidateProfileRepo:
    return CandidateProfileRepo(db_session)


@pytest.fixture
def cv_repo(db_session: Session) -> CVVariantRepo:
    return CVVariantRepo(db_session)


def test_create_candidate_profile(profile_repo: CandidateProfileRepo) -> None:
    profile = CandidateProfile(
        name="Python AI Senior",
        seniority="Senior",
        years_experience=10,
        primary_stack=["Python", "PyTorch", "SQLAlchemy"],
        languages={"english": "fluent", "spanish": "native"},
        compensation={"floor_usd_month": 6000, "target_usd_month": 8000},
    )
    created = profile_repo.create(profile)
    assert created.id is not None
    assert created.name == "Python AI Senior"
    assert created.is_active is True


def test_list_active_profiles(profile_repo: CandidateProfileRepo) -> None:
    p1 = CandidateProfile(name="P1", is_active=True)
    p2 = CandidateProfile(name="P2", is_active=True)
    p3 = CandidateProfile(name="P3", is_active=False)
    profile_repo.create(p1)
    profile_repo.create(p2)
    profile_repo.create(p3)

    active = profile_repo.list_active()
    assert len(active) == 2
    names = [p.name for p in active]
    assert "P1" in names
    assert "P2" in names
    assert "P3" not in names


def test_update_profile_trigger_history(
    profile_repo: CandidateProfileRepo, db_session: Session
) -> None:
    # Only test trigger if using postgresql as per technical specification
    # But wait, my migration added trigger ONLY for postgresql.
    # In SQLite, it won't work. We should check the dialect.
    assert db_session.bind is not None
    is_postgres = db_session.bind.dialect.name == "postgresql"

    profile = CandidateProfile(name="Initial Name", notes="Initial Notes")
    profile_repo.create(profile)
    db_session.commit()  # Ensure it's committed to DB for trigger to work on next update

    # Update
    profile_repo.update_with_history(profile.id, change_reason="Name changed", name="Updated Name")
    db_session.commit()

    if is_postgres:
        history = profile_repo.list_history(profile.id)
        assert len(history) == 1
        assert history[0].snapshot["name"] == "Initial Name"
        assert history[0].change_reason == "Name changed"
    else:
        # SQLite doesn't have the trigger, so history should be empty
        history = profile_repo.list_history(profile.id)
        assert len(history) == 0


def test_cv_variant_crud(profile_repo: CandidateProfileRepo, cv_repo: CVVariantRepo) -> None:
    profile = CandidateProfile(name="Profile for CV")
    profile_repo.create(profile)

    variant = CVVariant(
        profile_id=profile.id,
        name="ai_python",
        display_name="AI Python Engineer",
        target_stack=["Python", "TensorFlow"],
    )
    cv_repo.create(variant)

    retrieved = cv_repo.get_by_name(profile.id, "ai_python")
    assert retrieved is not None
    assert retrieved.display_name == "AI Python Engineer"


def test_create_cv_with_experiences(
    profile_repo: CandidateProfileRepo, cv_repo: CVVariantRepo
) -> None:
    profile = CandidateProfile(name="Profile for Exp")
    profile_repo.create(profile)

    variant = CVVariant(profile_id=profile.id, name="fullstack")
    exps = [
        CVVariantExperience(role="Dev", company="A", sort_order=1),
        CVVariantExperience(role="Lead", company="B", sort_order=0),
    ]

    cv_repo.create_with_experiences(variant, exps)

    retrieved = cv_repo.get(variant.id)
    assert retrieved is not None
    assert len(retrieved.experiences) == 2
    # Check ordering (models.py has order_by="CVVariantExperience.sort_order")
    assert retrieved.experiences[0].role == "Lead"
    assert retrieved.experiences[1].role == "Dev"


def test_cascade_delete(
    profile_repo: CandidateProfileRepo, cv_repo: CVVariantRepo, db_session: Session
) -> None:
    profile = CandidateProfile(name="Profile to Delete")
    profile_repo.create(profile)

    variant = CVVariant(profile_id=profile.id, name="v1")
    cv_repo.create(variant)

    exp = CVVariantExperience(cv_variant_id=variant.id, role="Role")
    db_session.add(exp)
    db_session.flush()

    # Delete profile
    profile_repo.delete(profile.id)
    db_session.commit()

    # Verify everything is gone
    assert cv_repo.get(variant.id) is None
    stmt = select(CVVariantExperience).where(CVVariantExperience.cv_variant_id == variant.id)
    assert db_session.scalar(stmt) is None
