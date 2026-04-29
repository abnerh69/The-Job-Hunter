import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any

import structlog
import typer
from rich.console import Console
from rich.table import Table

from jobhunter import __version__
import uuid

from jobhunter.config import Settings
from jobhunter.db.enums import JobStatus, JobTier
from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.db.repos.source_health import SourceHealthRepo
from jobhunter.db.seed import seed_database
from jobhunter.db.session import get_session
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.scoring.pipeline import rescore_jobs, score_pending_jobs
from jobhunter.scoring.schema import ScoringResult, Tier
from jobhunter.scoring.scorer import JobScorer
from jobhunter.sources.orchestrator import run_ingestion
from jobhunter.sources.registry import get_all_sources
from jobhunter.notify import get_notifier_cls, NotificationMessage
from jobhunter.notify.digest import send_weekly_digest

logger = structlog.get_logger()
app = typer.Typer(help="Job Hunter EU CLI")

sources_app = typer.Typer(help="Manage job sources")
app.add_typer(sources_app, name="sources")

scoring_app = typer.Typer(help="LLM scoring statistics and management")
app.add_typer(scoring_app, name="scoring")

notify_app = typer.Typer(help="Manage and test notifications")
app.add_typer(notify_app, name="notify")


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


@notify_app.command("digest")
def notify_digest(
    week_ending: Annotated[
        str | None, typer.Option(help="End date of the week (YYYY-MM-DD), defaults to today")
    ] = None,
) -> None:
    """Send the weekly digest email summary."""
    logger.info("Triggering weekly digest notification", week_ending=week_ending)

    ending_date: date | None = None
    if week_ending:
        try:
            ending_date = datetime.strptime(week_ending, "%Y-%m-%d").date()
        except ValueError:
            typer.echo(f"Error: Invalid date format: {week_ending}. Use YYYY-MM-DD.", err=True)
            raise typer.Exit(code=1)

    try:
        with get_session() as session:
            result = asyncio.run(send_weekly_digest(session, ending_date))

            if result is None:
                typer.echo("Digest was already sent for this week. Skipping.")
            elif result.success:
                typer.echo(f"Successfully sent weekly digest. (Duration: {result.duration_ms}ms)")
            else:
                typer.echo(f"Failed to send weekly digest: {result.error}", err=True)
                raise typer.Exit(code=1)
    except Exception as e:
        logger.error("Failed to send weekly digest", error=str(e))
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
                success_rate = (
                    (s["success_count"] / s["total_calls"]) * 100 if s["total_calls"] > 0 else 0
                )
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
def score(
    limit: Annotated[int, typer.Option(help="Maximum number of jobs to score")] = 100,
    concurrency: Annotated[int, typer.Option(help="Maximum concurrent LLM calls")] = 5,
    model: Annotated[str | None, typer.Option(help="LLM model to use")] = None,
    prompt_version: Annotated[str, typer.Option(help="Prompt version to use")] = "latest",
    dry_run: Annotated[bool, typer.Option(help="Do not persist results to database")] = False,
) -> None:
    """Score pending jobs using LLM."""
    logger.info(
        "Starting job scoring",
        limit=limit,
        concurrency=concurrency,
        model=model,
        prompt_version=prompt_version,
        dry_run=dry_run,
    )

    settings = Settings()  # type: ignore[call-arg]
    llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    scorer_kwargs = {"llm_client": llm_client, "prompt_version": prompt_version}
    if model:
        scorer_kwargs["model"] = model

    scorer = JobScorer(**scorer_kwargs)  # type: ignore[arg-type]

    try:
        with get_session() as session:
            # We use a simple spinner for now as the pipeline doesn't report incremental progress
            from rich.progress import Progress, SpinnerColumn, TextColumn

            console = Console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description="Scoring jobs...", total=None)
                report = asyncio.run(
                    score_pending_jobs(
                        session=session,
                        scorer=scorer,
                        limit=limit,
                        concurrency=concurrency,
                        dry_run=dry_run,
                    )
                )

            # Output results table
            table = Table(
                title=f"Scoring Report {'(DRY RUN)' if dry_run else ''}",
                show_footer=True,
                header_style="bold magenta",
            )
            table.add_column("Metric", footer="Total")
            table.add_column("Value", justify="right")

            table.add_row("Processed", str(report.total_processed))
            table.add_row("Success", f"[green]{report.success_count}[/green]")
            table.add_row("Failed", f"[red]{report.failed_count}[/red]")
            table.add_row("Total Cost", f"${report.total_cost_usd:.4f}", style="bold")
            table.add_row("Duration", f"{report.duration_seconds:.2f}s")

            console.print(table)

            if report.tier_distribution:
                tier_table = Table(title="Tier Distribution", header_style="bold blue")
                tier_table.add_column("Tier")
                tier_table.add_column("Count", justify="right")
                for tier, count in sorted(report.tier_distribution.items()):
                    tier_table.add_row(tier, str(count))
                console.print(tier_table)

            # Exit code 1 if success rate < 90%
            if report.total_processed > 0:
                success_rate = (report.success_count / report.total_processed) * 100
                if success_rate < 90:
                    typer.echo(f"Low success rate: {success_rate:.1f}%", err=True)
                    raise typer.Exit(code=1)

            if report.total_processed == 0:
                typer.echo("No pending jobs to score.")

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.error("Scoring failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def score_job(
    job_id: Annotated[str, typer.Argument(help="UUID of the job to score")],
    persist: Annotated[bool, typer.Option(help="Persist result to database")] = False,
) -> None:
    """Score a specific job and show raw response."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {job_id}", err=True)
        raise typer.Exit(code=1)

    logger.info("Scoring specific job", job_id=job_id, persist=persist)

    settings = Settings()  # type: ignore[call-arg]
    llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
    scorer = JobScorer(llm_client=llm_client)

    try:
        with get_session() as session:
            repo = JobRepo(session)
            job = repo.get(job_uuid)
            if not job:
                typer.echo(f"Error: Job {job_id} not found.", err=True)
                raise typer.Exit(code=1)

            outcome = asyncio.run(scorer.score(job, session=session))

            typer.echo("--- RAW RESPONSE ---")
            typer.echo(outcome.raw_response)
            typer.echo("--- END RAW RESPONSE ---")

            console = Console()
            table = Table(title="Scoring Result")
            table.add_column("Field")
            table.add_column("Value")

            table.add_row("Model", outcome.model)
            table.add_row("Cost", f"${outcome.cost_usd:.4f}")
            table.add_row("Tokens", f"I:{outcome.input_tokens} / O:{outcome.output_tokens}")

            if hasattr(outcome.result, "tier"):
                table.add_row("Tier", str(outcome.result.tier))
            if hasattr(outcome.result, "fit_score"):
                table.add_row("Fit Score", str(outcome.result.fit_score))

            console.print(table)

            if persist:
                job.scored_at = datetime.now(timezone.utc)
                job.score_model = outcome.model
                job.score_version = outcome.prompt_version
                job.score_data = outcome.result.model_dump()

                if isinstance(outcome.result, ScoringResult):
                    job.fit_score = outcome.result.fit_score
                    job.tier = JobTier(outcome.result.tier.value)

                    if outcome.result.tier in (Tier.A, Tier.B):
                        job.status = JobStatus.QUEUED
                    elif outcome.result.tier == Tier.C:
                        job.status = JobStatus.MANUAL_REVIEW
                    elif outcome.result.tier == Tier.REJECT:
                        job.status = JobStatus.REJECTED
                else:
                    job.status = JobStatus.ARCHIVED

                session.commit()
                typer.echo("Result persisted to database.")
            else:
                session.rollback()
                typer.echo("Result NOT persisted (use --persist to save).")

    except Exception as e:
        logger.error("Job scoring failed", job_id=job_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def rescore(
    tier: Annotated[JobTier, typer.Option(help="Tier of jobs to rescore")] = JobTier.A,
    with_model: Annotated[str | None, typer.Option(help="LLM model to use for rescoring")] = None,
    limit: Annotated[int, typer.Option(help="Maximum number of jobs to rescore")] = 100,
) -> None:
    """Re-score jobs already scored."""
    logger.info("Starting job rescoring", tier=tier, model=with_model, limit=limit)

    settings = Settings()  # type: ignore[call-arg]
    client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    scorer_kwargs: dict[str, Any] = {"llm_client": client}
    if with_model:
        scorer_kwargs["model"] = with_model

    scorer = JobScorer(**scorer_kwargs)

    try:
        with get_session() as session:
            from rich.progress import Progress, SpinnerColumn, TextColumn

            console = Console()
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                progress.add_task(description=f"Rescoring Tier {tier} jobs...", total=None)
                report = asyncio.run(
                    rescore_jobs(
                        session=session,
                        scorer=scorer,
                        filters={"tier": tier},
                        limit=limit,
                    )
                )

            table = Table(title=f"Rescoring Report (Tier {tier})")
            table.add_column("Metric")
            table.add_column("Value", justify="right")

            table.add_row("Processed", str(report.total_processed))
            table.add_row("Success", str(report.success_count))
            table.add_row("Failed", str(report.failed_count))
            table.add_row("Total Cost", f"${report.total_cost_usd:.4f}")

            console.print(table)

    except Exception as e:
        logger.error("Rescoring failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@notify_app.command("test")
def notify_test(
    channel: Annotated[str, typer.Option(help="Channel to test (e.g., 'telegram')")],
    message: Annotated[str, typer.Option(help="Message to send")],
) -> None:
    """Send a test notification to a specific channel."""
    logger.info("Sending test notification", channel=channel)

    settings = Settings()  # type: ignore[call-arg]
    notifier_cls = get_notifier_cls(channel)

    if not notifier_cls:
        typer.echo(f"Error: Notifier '{channel}' not found.", err=True)
        raise typer.Exit(code=1)

    notifier = notifier_cls()
    if not notifier.is_enabled(settings):
        typer.echo(f"Error: Notifier '{channel}' is not enabled in settings.", err=True)
        raise typer.Exit(code=1)

    msg = NotificationMessage(
        channel=channel,
        body_text=message,
        metadata={"test": True},
    )

    try:
        result = asyncio.run(notifier.send(msg))
        if result.success:
            typer.echo(f"Successfully sent message to {channel}.")
        else:
            typer.echo(f"Failed to send message: {result.error}", err=True)
            raise typer.Exit(code=1)
    except Exception as e:
        logger.error("Failed to send test notification", channel=channel, error=str(e))
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
