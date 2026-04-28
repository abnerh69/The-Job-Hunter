import os
import subprocess
import sys
from pathlib import Path

import structlog
import typer

from jobhunter import __version__
from jobhunter.config import Settings
from typing import Annotated
from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.seed import seed_database
from jobhunter.db.session import get_session

logger = structlog.get_logger()
app = typer.Typer(help="Job Hunter EU CLI")


@app.command()
def version() -> None:
    """Print the version of Job Hunter EU."""
    print(f"Job Hunter EU v{__version__}")


@app.command()
def db_refresh_metrics() -> None:
    """Refresh the weekly_metrics materialized view."""
    logger.info("Starting manual refresh of weekly metrics")
    try:
        with get_session() as session:
            refresh_weekly_metrics(session)
        typer.echo("Successfully refreshed weekly metrics.")
    except Exception as e:
        logger.error("Failed to refresh weekly metrics", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def db_seed(
    scenario: Annotated[str, typer.Option(help="Scenario to seed: 'rich' or 'minimal'")] = "rich",
) -> None:
    """Seed the database with sample data."""
    if scenario not in ["rich", "minimal"]:
        typer.echo(f"Error: Invalid scenario '{scenario}'. Must be 'rich' or 'minimal'.", err=True)
        raise typer.Exit(code=1)

    logger.info("Starting database seeding", scenario=scenario)
    try:
        with get_session() as session:
            seed_database(session, scenario=scenario)  # type: ignore[arg-type]
        typer.echo(f"Successfully seeded database with scenario: {scenario}")
    except Exception as e:
        logger.error("Failed to seed database", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def db_backup(
    output: Annotated[
        Path | None, typer.Option(help="Path to the backup file (defaults to timestamped file)")
    ] = None,
) -> None:
    """Create a compressed backup of the database."""
    logger.info("Starting database backup")
    try:
        # Resolve path to the backup script
        script_path = Path(__file__).parent.parent.parent / "scripts" / "backup_db.sh"
        if not script_path.exists():
            typer.echo(f"Error: Backup script not found at {script_path}", err=True)
            raise typer.Exit(code=1)

        cmd = ["bash", str(script_path)]
        if output:
            cmd.append(str(output))

        # Pass environment variables to the script
        env = os.environ.copy()
        settings = Settings()  # type: ignore[call-arg]
        env["DATABASE_URL"] = settings.DATABASE_URL

        result = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True)
        typer.echo(result.stdout)
        logger.info("Database backup completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error("Database backup failed", error=str(e), stderr=e.stderr)
        typer.echo(f"Error during backup: {e.stderr}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error("Failed to initiate database backup", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.callback()
def callback() -> None:
    """Initialize the application and validate configuration."""
    try:
        # Validate settings on every command
        Settings()  # type: ignore[call-arg]
    except Exception as e:
        logger.error("Failed to load configuration", error=str(e))
        sys.exit(1)


def main() -> None:
    """Main entry point for the application."""
    app()


if __name__ == "__main__":
    main()
