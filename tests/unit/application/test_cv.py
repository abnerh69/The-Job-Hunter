import pytest
from pathlib import Path
from pydantic import SecretStr
from jobhunter.application.cv import load_cv, list_available_variants
from jobhunter.config import Settings


def test_list_available_variants(tmp_path: Path) -> None:
    # Setup mock directories
    local_dir = tmp_path / ".local" / "cv_variants"
    repo_dir = tmp_path / "cv_variants"
    local_dir.mkdir(parents=True)
    repo_dir.mkdir(parents=True)

    (local_dir / "expert.md").write_text("dummy")
    (repo_dir / "template.template.md").write_text("dummy")

    settings = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        CV_VARIANTS_DIR=local_dir,
    )

    # We need to mock Path("cv_variants") or just rely on the fact that we can't easily mock it without monkeypatch
    # but we can at least check if it finds the ones in CV_VARIANTS_DIR
    variants = list_available_variants(settings)
    assert "expert" in variants


def test_load_cv_success(tmp_path: Path) -> None:
    cv_content = """# My CV
## SUMMARY
Experienced dev.
## STACK
- primary: Python, Go
- secondary: AWS, Docker
## EXPERIENCE
### Senior Dev | Tech Corp | 2020-2024
- Led team.
- Built stuff.
## SKILLS
- Testing
- Architecture
"""
    cv_dir = tmp_path / "cv_variants"
    cv_dir.mkdir()
    cv_file = cv_dir / "ai_python.md"
    cv_file.write_text(cv_content)

    settings = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        CV_VARIANTS_DIR=cv_dir,
    )

    cv = load_cv("ai_python", settings=settings)

    assert cv.name == "ai_python"
    assert cv.summary == "Experienced dev."
    assert cv.stack_primary == ["Python", "Go"]
    assert cv.stack_secondary == ["AWS", "Docker"]
    assert len(cv.experience) == 1
    assert cv.experience[0].role == "Senior Dev"
    assert cv.experience[0].company == "Tech Corp"
    assert cv.experience[0].bullets == ["Led team.", "Built stuff."]
    assert cv.skills == ["Testing", "Architecture"]


def test_load_cv_malformed(tmp_path: Path) -> None:
    cv_content = """# My CV
## SUMMARY
Missing experience section.
"""
    cv_dir = tmp_path / "cv_variants"
    cv_dir.mkdir()
    cv_file = cv_dir / "bad.md"
    cv_file.write_text(cv_content)

    settings = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        CV_VARIANTS_DIR=cv_dir,
    )

    with pytest.raises(ValueError, match="missing an EXPERIENCE section"):
        load_cv("bad", settings=settings)


def test_load_cv_not_found(tmp_path: Path) -> None:
    settings = Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("pass"),
        CV_VARIANTS_DIR=tmp_path,
    )
    with pytest.raises(FileNotFoundError):
        load_cv("non_existent", settings=settings)


def test_fallback_to_repo_variants(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # This test is a bit trickier because Path("cv_variants") is hardcoded
    # We will create the directory in the current working directory (sandbox root)
    repo_dir = Path("cv_variants")
    repo_dir.mkdir(exist_ok=True)
    test_file = repo_dir / "test_fallback.template.md"
    test_file.write_text("""## SUMMARY
Fallback worked.
## EXPERIENCE
### Role | Co | Date
- Bullet
""")

    try:
        settings = Settings(
            ANTHROPIC_API_KEY=SecretStr("dummy"),
            DASHBOARD_PASSWORD=SecretStr("pass"),
            CV_VARIANTS_DIR=tmp_path / "empty",
        )
        cv = load_cv("test_fallback", settings=settings)
        assert cv.summary == "Fallback worked."
    finally:
        if test_file.exists():
            test_file.unlink()
