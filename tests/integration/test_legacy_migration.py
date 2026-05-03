import importlib.util
from pathlib import Path
from typing import Any

import yaml


def test_migration_logic(tmp_path: Path, monkeypatch: Any) -> None:
    # Setup mock filesystem
    root_dir = tmp_path
    prompts_dir = root_dir / "prompts"
    prompts_dir.mkdir()
    cv_variants_dir = root_dir / ".local" / "cv_variants"
    cv_variants_dir.mkdir(parents=True)

    yaml_content = {
        "name": "Test User",
        "years_experience": "15+",
        "location_legal": {"country": "Spain"},
        "primary_stack": ["Python", "AWS"],
    }
    yaml_file = prompts_dir / "candidate_profile.yaml"
    with open(yaml_file, "w") as f:
        yaml.dump(yaml_content, f)

    md_content = """## SUMMARY
Test CV
## STACK
- primary: Python
## EXPERIENCE
### Dev | Co | 2020-2022
- Bullet
"""
    md_file = cv_variants_dir / "test_variant.md"
    with open(md_file, "w") as f:
        f.write(md_content)

    # Point the migration to our tmp_path
    monkeypatch.chdir(root_dir)

    # Calculate path to the migration script relative to this test file
    migration_dir = Path(__file__).parent.parent.parent / "alembic" / "versions"
    migration_files = list(migration_dir.glob("8978759777f4_*.py"))
    assert len(migration_files) == 1
    migration_path = migration_files[0]

    spec = importlib.util.spec_from_file_location("migration_module", migration_path)
    assert spec is not None
    migration_module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration_module)

    # Mocking op.get_bind()
    class MockConn:
        def __init__(self) -> None:
            self.dialect = type("obj", (object,), {"name": "sqlite"})
            self.inserts: list[Any] = []

        def execute(self, statement: Any, params: Any = None) -> Any:
            self.inserts.append((statement, params))
            # Return dummy for fetchone if it's a SELECT
            if "SELECT" in str(statement):
                return type("obj", (object,), {"fetchone": lambda *args, **kwargs: None})()
            return None

    mock_conn = MockConn()

    class MockOp:
        def get_bind(self) -> Any:
            return mock_conn

    monkeypatch.setattr(migration_module, "op", MockOp())

    # Run upgrade
    migration_module.upgrade()

    # Check if archive created
    legacy_prompts = list(prompts_dir.glob("_legacy/*/candidate_profile.yaml"))
    assert len(legacy_prompts) == 1

    legacy_mds = list(cv_variants_dir.glob("_legacy/*/test_variant.md"))
    assert len(legacy_mds) == 1

    # Check mock_conn.inserts to see if we attempted to insert
    insert_statements = [str(s[0]) for s in mock_conn.inserts]
    assert any("INSERT INTO candidate_profiles" in s for s in insert_statements)
    assert any("INSERT INTO cv_variants" in s for s in insert_statements)
    assert any("INSERT INTO cv_variant_experiences" in s for s in insert_statements)
