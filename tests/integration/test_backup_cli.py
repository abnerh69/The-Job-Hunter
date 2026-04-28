import subprocess
import os
from pathlib import Path


def test_cli_db_backup_help() -> None:
    """Test that the db-backup command is available in the CLI help."""
    result = subprocess.run(
        ["python", "-m", "jobhunter", "db-backup", "--help"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "src", "ANTHROPIC_API_KEY": "dummy"},
    )
    assert result.returncode == 0
    assert "Create a compressed backup of the database" in result.stdout
    assert "--output" in result.stdout


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
