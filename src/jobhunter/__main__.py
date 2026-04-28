import sys

import structlog
import typer

from jobhunter import __version__
from jobhunter.config import Settings
from jobhunter.db.maintenance import refresh_weekly_metrics
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
