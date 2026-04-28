import subprocess
import os
import re
from pathlib import Path


def strip_ansi(text: str) -> str:
    """Removes ANSI escape codes from a string."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", text)


def test_cli_db_backup_help() -> None:
    """Test that the db-backup command is available in the CLI help."""
    # We use NO_COLOR=1 to try to avoid ANSI escape codes, but some may persist
    # depending on the environment/Rich configuration, so we strip them manually.
    result = subprocess.run(
        ["python", "-m", "jobhunter", "db-backup", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src", "ANTHROPIC_API_KEY": "dummy", "NO_COLOR": "1"},
    )
    assert result.returncode == 0
    stdout = strip_ansi(result.stdout)
    assert "Create a compressed backup of the database" in stdout
    assert "--output" in stdout


def test_backup_script_integrity(tmp_path: Path) -> None:
    """Test that the backup script creates a valid gzip file (smoke test)."""
    # This test assumes a database is running and accessible via DATABASE_URL
    # which is true in our sandbox environment now.
    backup_file = tmp_path / "test_backup_smoke.sql.gz"

    script_path = Path("scripts/backup_db.sh")
    assert script_path.exists()

    # Run the script directly
    result = subprocess.run(
        ["bash", str(script_path), str(backup_file)],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "DATABASE_URL": os.getenv(
                "DATABASE_URL", "postgresql://jobhunter:jobhunter_local@localhost:5432/jobhunter"
            ),
        },
    )

    assert result.returncode == 0
    assert backup_file.exists()

    # Check if it's a valid gzip file
    result_gzip = subprocess.run(["gunzip", "-t", str(backup_file)])
    assert result_gzip.returncode == 0
