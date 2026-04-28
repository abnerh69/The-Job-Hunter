import sys

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
    scenario: Annotated[str, typer.Option(help="Scenario to seed: 'rich' or 'minimal'")] = "rich"
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
