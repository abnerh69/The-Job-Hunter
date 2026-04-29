import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

import structlog
import typer
from rich.console import Console
from rich.table import Table

from jobhunter import __version__
from jobhunter.config import Settings
from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.db.repos.source_health import SourceHealthRepo
from jobhunter.db.seed import seed_database
from jobhunter.db.session import get_session
from jobhunter.sources.orchestrator import run_ingestion
from jobhunter.sources.registry import get_all_sources

logger = structlog.get_logger()
app = typer.Typer(help="Job Hunter EU CLI")

sources_app = typer.Typer(help="Manage job sources")
app.add_typer(sources_app, name="sources")

scoring_app = typer.Typer(help="LLM scoring statistics and management")
app.add_typer(scoring_app, name="scoring")


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
def ingest(
    source: Annotated[
        list[str] | None, typer.Option(help="Specific sources to run (can be repeated)")
    ] = None,
    since: Annotated[
        str, typer.Option(help="Fetch jobs since this date (YYYY-MM-DD or 'N days ago')")
    ] = "7 days ago",
    limit: Annotated[int | None, typer.Option(help="Maximum jobs per source")] = None,
    dry_run: Annotated[bool, typer.Option(help="Fetch and parse but do not persist to DB")] = False,
) -> None:
    """Run job ingestion from configured sources."""
    logger.info("Starting job ingestion", sources=source, since=since, dry_run=dry_run)

    # Resolve 'since' parameter
    since_dt: datetime
    if "days ago" in since:
        try:
            days = int(since.split()[0])
            since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        except (ValueError, IndexError):
            typer.echo(f"Error: Invalid 'since' format: {since}", err=True)
            raise typer.Exit(code=1)
    else:
        try:
            since_dt = datetime.fromisoformat(since).replace(tzinfo=timezone.utc)
        except ValueError:
            typer.echo(f"Error: Invalid 'since' date format: {since}. Use YYYY-MM-DD.", err=True)
            raise typer.Exit(code=1)

    # Resolve sources
    all_source_classes = get_all_sources()
    selected_sources = []
    if source:
        source_map = {cls.__name__.lower(): cls for cls in all_source_classes}
        for s in source:
            cls = source_map.get(s.lower())
            if cls:
                selected_sources.append(cls())
            else:
                typer.echo(f"Error: Source '{s}' not found.", err=True)
                raise typer.Exit(code=1)
    else:
        selected_sources = [cls() for cls in all_source_classes]

    if not selected_sources:
        typer.echo("No sources to ingest.")
        return

    try:
        with get_session() as session:
            report = asyncio.run(
                run_ingestion(selected_sources, since_dt, session, dry_run=dry_run, limit=limit)
            )

        # Output results table
        console = Console()
        table = Table(
            title=f"Ingestion Report {'(DRY RUN)' if dry_run else ''}",
            show_footer=True,
            header_style="bold magenta",
        )
        table.add_column("Source", footer="Total")
        table.add_column("Status")
        table.add_column("New", justify="right", footer=str(report.total_new))
        table.add_column("Duplicates", justify="right", footer=str(report.total_duplicates))
        table.add_column("Errors", justify="right", footer=str(report.total_errors))
        table.add_column("Duration", justify="right")

        for res in report.source_results:
            duration_str = f"{res.duration_ms}ms" if res.duration_ms > 0 else "-"
            status_style = "green" if res.status == "success" else "red"
            if res.status == "skipped_breaker":
                status_style = "yellow"

            table.add_row(
                res.source_name,
                f"[{status_style}]{res.status}[/{status_style}]",
                str(res.new_jobs),
                str(res.duplicates),
                "1" if res.status == "failed" else "0",
                duration_str,
            )

        console.print(table)

        if report.total_errors > 0:
            raise typer.Exit(code=1)

    except Exception as e:
        logger.error("Ingestion failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@sources_app.command("list")
def sources_list() -> None:
    """List all registered job sources and their current health status."""
    all_source_classes = get_all_sources()
    console = Console()
    table = Table(title="Job Sources Health", header_style="bold blue")
    table.add_column("Source Name")
    table.add_column("Circuit Breaker State")
    table.add_column("Last Failure At")
    table.add_column("Opened Until")

    try:
        with get_session() as session:
            repo = SourceHealthRepo(session)
            for cls in all_source_classes:
                name = cls.__name__
                health = repo.get_by_source(name)

                state = health.state if health else "CLOSED"
                last_failure = (
                    health.last_failure_at.isoformat() if health and health.last_failure_at else "-"
                )
                opened_until = (
                    health.opened_until.isoformat() if health and health.opened_until else "-"
                )

                state_style = "green" if state == "CLOSED" else "red"
                if state == "HALF_OPEN":
                    state_style = "yellow"

                table.add_row(
                    name,
                    f"[{state_style}]{state}[/{state_style}]",
                    last_failure,
                    opened_until,
                )

        console.print(table)
    except Exception as e:
        logger.error("Failed to list sources", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@scoring_app.command("stats")
def scoring_stats() -> None:
    """Display LLM scoring statistics and cost breakdown."""
    console = Console()
    now = datetime.now(timezone.utc)

    try:
        with get_session() as session:
            repo = LLMCallRepo(session)
            settings = Settings()  # type: ignore[call-arg]

            monthly_total = repo.monthly_total_usd(now.year, now.month)
            weekly_total = repo.weekly_total_usd(now)
            budget = settings.LLM_MONTHLY_BUDGET_USD

            # Header info
            console.print(f"[bold blue]LLM Cost Tracking - {now.strftime('%B %Y')}[/bold blue]")
            console.print(f"Monthly Spend: [bold]${monthly_total:.4f}[/] / ${budget:.2f}")
            console.print(f"Weekly Spend: [bold]${weekly_total:.4f}[/]")

            # Breakdown by model
            # Let's take stats for the current month
            start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = (start_of_month + timedelta(days=32)).replace(day=1)

            stats = repo.get_stats_by_model(start_of_month, next_month)

            table = Table(title="Cost Breakdown by Model", header_style="bold magenta")
            table.add_column("Model")
            table.add_column("Total Calls", justify="right")
            table.add_column("Success Rate", justify="right")
            table.add_column("Cost (USD)", justify="right")

            total_calls = 0
            total_success = 0

            for s in stats:
                success_rate = (s["success_count"] / s["total_calls"]) * 100 if s["total_calls"] > 0 else 0
                table.add_row(
                    s["model"],
                    str(s["total_calls"]),
                    f"{success_rate:.1f}%",
                    f"${s['total_cost']:.4f}",
                )
                total_calls += s["total_calls"]
                total_success += s["success_count"]

            avg_success = (total_success / total_calls) * 100 if total_calls > 0 else 0
            table.add_section()
            table.add_row(
                "Total",
                str(total_calls),
                f"{avg_success:.1f}%",
                f"${monthly_total:.4f}",
                style="bold",
            )

            console.print(table)

    except Exception as e:
        logger.error("Failed to retrieve scoring stats", error=str(e))
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
