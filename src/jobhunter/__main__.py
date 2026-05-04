import asyncio
import subprocess
import sys
import yaml
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any, Optional

import structlog
import typer
from sqlalchemy import select, asc
from rich.console import Console
from rich.table import Table
from rich.markdown import Markdown

from jobhunter import __version__
from jobhunter.log_config import configure_logging
import uuid

from jobhunter.config import Settings
from jobhunter.db.enums import (
    JobStatus,
    JobTier,
    ApplicationStatus,
    OutreachMarket,
    OutreachStatus,
    OutreachTemplateType,
    OutreachMessageStatus,
)
from jobhunter.db.maintenance import refresh_weekly_metrics
from jobhunter.db.repos.job import JobRepo
from jobhunter.db.repos.llm_calls import LLMCallRepo
from jobhunter.db.repos.outreach import OutreachRepo
from jobhunter.db.repos.outreach_messages import OutreachMessageRepo
from jobhunter.db.repos.source_health import SourceHealthRepo
from jobhunter.db.seed import seed_database
from jobhunter.db.session import get_session
from jobhunter.llm.anthropic_client import AnthropicLLMClient
from jobhunter.scoring.pipeline import rescore_jobs, score_pending_jobs
from jobhunter.scoring.schema import ScoringResult, Tier
from jobhunter.scoring.scorer import JobScorer
from jobhunter.sources.orchestrator import run_ingestion
from jobhunter.sources.registry import get_all_sources
from jobhunter.notify import get_all_notifiers, get_notifier_cls, NotificationMessage
from jobhunter.notify.digest import prepare_weekly_digest, send_weekly_digest
from jobhunter.notify.dispatcher import dispatch_tier_a_notifications
from jobhunter.notify.health_check import dispatch_health_alerts
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.pipeline import RunCycleStatus, run_cycle, run_followup_checks
from jobhunter.application.assistant import assist_application
from jobhunter.application.cover_letter import generate_cover_letter
from jobhunter.application.cv import load_cv
from jobhunter.db.models import Application, Job, OutreachContact, OutreachMessage
from jobhunter.analytics.regression_detector import check_metrics

logger = structlog.get_logger()
app = typer.Typer(help="Job Hunter EU CLI")

sources_app = typer.Typer(help="Manage job sources")
app.add_typer(sources_app, name="sources")

scoring_app = typer.Typer(help="LLM scoring statistics and management")
app.add_typer(scoring_app, name="scoring")

notify_app = typer.Typer(help="Manage and test notifications")
app.add_typer(notify_app, name="notify")

pipeline_app = typer.Typer(help="Orchestrate full pipeline cycles")
app.add_typer(pipeline_app, name="pipeline")

logs_app = typer.Typer(help="Inspect and download system logs")
app.add_typer(logs_app, name="logs")

email_app = typer.Typer(help="Manage Gmail OAuth2 authentication")
app.add_typer(email_app, name="email")

outreach_app = typer.Typer(help="Manage proactive outreach contacts")
app.add_typer(outreach_app, name="outreach")

telegram_app = typer.Typer(help="Manage Telegram bot interactions")
app.add_typer(telegram_app, name="telegram")

analytics_app = typer.Typer(help="Analytics and performance metrics")
app.add_typer(analytics_app, name="analytics")

backup_app = typer.Typer(help="Manage database backups and restores")
app.add_typer(backup_app, name="backup")

ab_test_app = typer.Typer(help="Manage A/B tests for prompts and templates")
analytics_app.add_typer(ab_test_app, name="ab-test")

api_app = typer.Typer(help="Manage API sidecar")
app.add_typer(api_app, name="api")


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


@notify_app.command("dispatch")
def notify_dispatch() -> None:
    """Dispatch pending Tier-A notifications."""
    logger.info("Starting manual notification dispatch")
    try:
        with get_session() as session:
            report = asyncio.run(dispatch_tier_a_notifications(session))

        console = Console()
        table = Table(title="Notification Dispatch Report", header_style="bold magenta")
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        table.add_row("Total Pending", str(report.total_pending))
        table.add_row("Sent Successfully", f"[green]{report.success_count}[/green]")
        table.add_row("Failed", f"[red]{report.failure_count}[/red]")
        table.add_row("Duration", f"{report.duration_ms}ms")

        console.print(table)

        if report.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for err in report.errors:
                console.print(f"- {err}")

    except Exception as e:
        logger.error("Dispatch failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@notify_app.command("digest")
def notify_digest(
    week_ending: Annotated[
        str | None, typer.Option(help="End date of the week (YYYY-MM-DD), defaults to today")
    ] = None,
    send: Annotated[
        bool, typer.Option(help="Actually send the email instead of just previewing")
    ] = False,
) -> None:
    """Preview or send the weekly digest email summary."""
    logger.info("Triggering weekly digest command", week_ending=week_ending, send=send)

    ending_date: date | None = None
    if week_ending:
        try:
            ending_date = datetime.strptime(week_ending, "%Y-%m-%d").date()
        except ValueError:
            typer.echo(f"Error: Invalid date format: {week_ending}. Use YYYY-MM-DD.", err=True)
            raise typer.Exit(code=1)

    try:
        with get_session() as session:
            if send:
                result = asyncio.run(send_weekly_digest(session, ending_date))
                if result is None:
                    typer.echo("Digest was already sent for this week. Skipping.")
                elif result.success:
                    typer.echo(
                        f"Successfully sent weekly digest. (Duration: {result.duration_ms}ms)"
                    )
                else:
                    typer.echo(f"Failed to send weekly digest: {result.error}", err=True)
                    raise typer.Exit(code=1)
            else:
                message, _ = prepare_weekly_digest(session, ending_date)
                typer.echo(f"Subject: {message.subject}")
                typer.echo("-" * 40)
                typer.echo(message.body_text)
                typer.echo("-" * 40)
                typer.echo("NOTE: Use --send to actually deliver the email.")

    except Exception as e:
        logger.error("Weekly digest command failed", error=str(e))
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
    subject: Annotated[str | None, typer.Option(help="Subject of the message (for email)")] = None,
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
        subject=subject,
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


@notify_app.command("status")
def notify_status() -> None:
    """Display the status of notification channels and recent attempts."""
    console = Console()
    settings = Settings()  # type: ignore[call-arg]

    # 1. Channel Status
    table_channels = Table(title="Notification Channels Status", header_style="bold blue")
    table_channels.add_column("Channel")
    table_channels.add_column("Status")
    table_channels.add_column("Reason")

    for notifier_cls in get_all_notifiers():
        notifier = notifier_cls()
        enabled = notifier.is_enabled(settings)
        status_str = "[green]ENABLED[/green]" if enabled else "[red]DISABLED[/red]"

        reason = "-"
        if not enabled:
            if notifier.name == "telegram":
                reason = "Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID"
            elif notifier.name == "email":
                reason = "Missing SMTP credentials or DIGEST_TO_EMAIL"

        table_channels.add_row(notifier.name, status_str, reason)

    console.print(table_channels)

    try:
        with get_session() as session:
            repo = NotificationsRepo(session)

            # 2. Recent Notifications
            recent = repo.get_recent(limit=10)
            table_recent = Table(title="Recent Notification Attempts", header_style="bold magenta")
            table_recent.add_column("Sent At")
            table_recent.add_column("Channel")
            table_recent.add_column("Dedup Key")
            table_recent.add_column("Status")

            for n in recent:
                status_style = "green" if n.success else "red"
                table_recent.add_row(
                    n.sent_at.strftime("%Y-%m-%d %H:%M:%S"),
                    n.channel,
                    n.dedup_key,
                    f"[{status_style}]{'SUCCESS' if n.success else 'FAILED'}[/{status_style}]",
                )
            console.print(table_recent)

            # 3. Failures in last 24h
            failures = repo.get_failure_breakdown(hours=24)
            if failures:
                table_failures = Table(title="Failures in Last 24h", header_style="bold red")
                table_failures.add_column("Channel")
                table_failures.add_column("Count", justify="right")
                for chan, count in failures.items():
                    table_failures.add_row(chan, str(count))
                console.print(table_failures)
            else:
                console.print("\n[green]No notification failures in the last 24 hours.[/green]")

    except Exception as e:
        logger.error("Failed to retrieve notification status", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def assist(
    job_id: Annotated[str, typer.Argument(help="UUID of the job to assist")],
    output_dir: Annotated[
        Path | None, typer.Option(help="Directory to write files (default: stdout)")
    ] = None,
    no_letter: Annotated[bool, typer.Option(help="Skip cover letter generation")] = False,
    cv_variant: Annotated[str | None, typer.Option(help="Override CV variant selector")] = None,
) -> None:
    """Generate application package: CV variant, tweaks, keywords, and letter."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {job_id}", err=True)
        raise typer.Exit(code=1)

    settings = Settings()  # type: ignore[call-arg]
    llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    try:
        with get_session() as session:
            package = asyncio.run(
                assist_application(
                    session=session,
                    job_id=job_uuid,
                    llm_client=llm_client,
                    settings=settings,
                    no_letter=no_letter,
                    cv_variant_override=cv_variant,
                )
            )

        console = Console()
        console.print(f"\n[bold blue]Application Package for Job {job_id}[/bold blue]\n")

        # Summary table
        table = Table(title="Summary")
        table.add_column("Component")
        table.add_column("Result")
        table.add_row("CV Variant", package.cv_variant.variant_name)
        table.add_row("Variant Reasoning", package.cv_variant.reasoning)
        table.add_row("Estimated Apply Time", f"{package.estimated_apply_time_min} min")
        table.add_row("Total Cost", f"${package.total_cost_usd:.4f}")
        table.add_row("Duration", f"{package.total_duration_ms}ms")
        console.print(table)

        # ATS Keywords
        console.print("\n[bold magenta]ATS Keywords:[/bold magenta]")
        kw_table = Table()
        kw_table.add_column("Term")
        kw_table.add_column("Weight", justify="right")
        kw_table.add_column("In CV?", justify="center")

        for kw in package.ats_keywords.must_have + package.ats_keywords.nice_to_have:
            in_cv = "[green]✓[/green]" if kw.present_in_cv else "[red]✗[/red]"
            kw_table.add_row(kw.term, str(kw.weight), in_cv)
        console.print(kw_table)

        # CV Tweaks
        console.print("\n[bold magenta]CV Tweaks:[/bold magenta]")
        for i, tweak in enumerate(package.cv_tweaks.tweaks, 1):
            console.print(f"{i}. [bold]{tweak.type}: {tweak.target}[/bold]")
            console.print(f"   [italic]{tweak.suggested}[/italic]")
            console.print(f"   Rationale: {tweak.rationale}\n")

        # Cover Letter
        if package.cover_letter:
            console.print("\n[bold magenta]Cover Letter:[/bold magenta]")
            console.print("-" * 40)
            console.print(Markdown(package.cover_letter.text))
            console.print("-" * 40)

        # Output to files if requested
        if output_dir:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "cv_variant.txt").write_text(package.cv_variant.variant_name)
            (output_dir / "cv_tweaks.md").write_text(
                "\n".join(
                    f"- {t.type} ({t.target}): {t.suggested}\n  Rationale: {t.rationale}"
                    for t in package.cv_tweaks.tweaks
                )
            )
            (output_dir / "keywords.txt").write_text(
                "\n".join(
                    f"{kw.term} ({kw.weight}) - {'Present' if kw.present_in_cv else 'Missing'}"
                    for kw in package.ats_keywords.must_have + package.ats_keywords.nice_to_have
                )
            )
            if package.cover_letter:
                (output_dir / "cover_letter.md").write_text(package.cover_letter.text)
            typer.echo(f"\nFiles written to {output_dir}")

    except Exception as e:
        logger.error("Assist failed", job_id=job_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def letter(
    job_id: Annotated[str, typer.Argument(help="UUID of the job to generate letter for")],
    output: Annotated[
        Path | None, typer.Option(help="File to write letter (default: stdout)")
    ] = None,
    cv_variant: Annotated[str | None, typer.Option(help="CV variant to use")] = None,
) -> None:
    """Generate only the cover letter for a job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {job_id}", err=True)
        raise typer.Exit(code=1)

    settings = Settings()  # type: ignore[call-arg]
    llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    try:
        with get_session() as session:
            job = session.get(Job, job_uuid)
            if not job:
                typer.echo(f"Error: Job {job_id} not found.", err=True)
                raise typer.Exit(code=1)

            if not cv_variant:
                from jobhunter.application.variant_selector import recommend_cv_variant

                rec = recommend_cv_variant(job)
                cv_variant = rec.variant_name
                typer.echo(f"Auto-selected CV variant: {cv_variant} ({rec.reasoning})")

            cv = load_cv(cv_variant, settings=settings)
            result = asyncio.run(
                generate_cover_letter(
                    job=job,
                    cv_variant=cv,
                    llm_client=llm_client,
                    model=settings.COVER_LETTER_MODEL,
                    session=session,
                )
            )

            if output:
                output.write_text(result.text)
                typer.echo(f"Cover letter written to {output}")
            else:
                console = Console()
                console.print("-" * 40)
                console.print(Markdown(result.text))
                console.print("-" * 40)

    except Exception as e:
        logger.error("Letter generation failed", job_id=job_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def apply(
    job_id: Annotated[str, typer.Argument(help="UUID of the job applied to")],
    method: Annotated[
        str,
        typer.Option(help="Application method (web/email/linkedin/referral)", show_default=False),
    ],
    cv_variant: Annotated[str, typer.Option(help="CV variant used", show_default=False)],
    contact_name: Annotated[str | None, typer.Option(help="Name of contact person")] = None,
    contact_email: Annotated[str | None, typer.Option(help="Email of contact person")] = None,
    notes: Annotated[str | None, typer.Option(help="Additional notes")] = None,
) -> None:
    """Register a manual application for a job."""
    try:
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {job_id}", err=True)
        raise typer.Exit(code=1)

    try:
        with get_session() as session:
            job = session.get(Job, job_uuid)
            if not job:
                typer.echo(f"Error: Job {job_id} not found.", err=True)
                raise typer.Exit(code=1)

            # Create Application
            app_record = Application(
                job_id=job_uuid,
                application_method=method,
                cv_variant=cv_variant,
                contact_name=contact_name,
                contact_email=contact_email,
                notes=notes,
                status=ApplicationStatus.APPLIED,
            )

            # Check for cached assistant data in job.score_data
            if job.score_data and "assistant_cache" in job.score_data:
                cache = job.score_data["assistant_cache"]
                if "cover_letter_text" in cache:
                    app_record.cover_letter_text = cache["cover_letter_text"]
                    app_record.cover_letter_model = cache.get("cover_letter_model")
                    typer.echo(
                        "Persisting cover letter from database cache (from previous assist)."
                    )

            session.add(app_record)

            # Transition Job status
            job.status = JobStatus.APPLIED

            session.commit()
            typer.echo(f"Successfully registered application for {job.company} - {job.title}")

    except Exception as e:
        logger.error("Apply registration failed", job_id=job_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@pipeline_app.command("check-followups")
def pipeline_check_followups() -> None:
    """Run daily follow-up and ghosting checks."""
    logger.info("Starting follow-up and ghosting checks")

    try:
        with get_session() as session:
            report = asyncio.run(run_followup_checks(session))

        console = Console()
        table = Table(title="Follow-up Checks Report", header_style="bold magenta")
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        table.add_row("App Follow-ups Due", str(report.pending_followups_count))
        table.add_row("Apps Ghosted", str(report.ghosted_marked_count))
        table.add_row("Outreach Follow-ups Due", str(report.pending_outreach_count))
        table.add_row("Outreach Ghosted", str(report.outreach_ghosted_count))
        table.add_row(
            "Notification Sent", "[green]YES[/green]" if report.notification_sent else "NO"
        )
        table.add_row("Duration", f"{report.duration_ms}ms")

        console.print(table)

        if report.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for err in report.errors:
                console.print(f"- {err}")

    except Exception as e:
        logger.exception("Follow-up checks failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command("health-check")
def health_check() -> None:
    """Run system health checks and send alerts if needed."""
    logger.info("Starting system health checks")
    try:
        with get_session() as session:
            sent_count = asyncio.run(dispatch_health_alerts(session))

        if sent_count > 0:
            typer.echo(f"Sent {sent_count} health alerts.")
        else:
            typer.echo("System healthy. No alerts sent.")
    except Exception as e:
        logger.error("Health check command failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@pipeline_app.command("run-cycle")
def pipeline_run_cycle(
    skip_step: Annotated[
        list[str] | None, typer.Option(help="Steps to skip (ingest, score, notify)")
    ] = None,
    since: Annotated[
        str, typer.Option(help="Fetch jobs since this date (YYYY-MM-DD or 'N days ago')")
    ] = "1 day ago",
    limit: Annotated[int | None, typer.Option(help="Maximum jobs per source to ingest")] = None,
    source: Annotated[
        list[str] | None, typer.Option(help="Specific sources to run (can be repeated)")
    ] = None,
) -> None:
    """Run the full ingestion -> scoring -> notification cycle."""
    logger.info(
        "Starting pipeline run-cycle", skip_steps=skip_step, since=since, limit=limit, source=source
    )

    # Resolve 'since' parameter
    since_dt: datetime
    if "days ago" in since or "day ago" in since:
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

    try:
        with get_session() as session:
            report = asyncio.run(
                run_cycle(
                    session=session,
                    skip_steps=skip_step,
                    since=since_dt,
                    ingest_limit=limit,
                    ingest_sources=source,
                )
            )

        console = Console()
        table = Table(title="Pipeline Run Cycle Report", header_style="bold magenta")
        table.add_column("Step")
        table.add_column("Status")
        table.add_column("Details")

        # Ingestion Row
        if report.ingestion:
            ing = report.ingestion
            table.add_row(
                "Ingestion",
                "[green]SUCCESS[/green]" if ing.total_errors == 0 else "[yellow]PARTIAL[/yellow]",
                f"New: {ing.total_new}, Dups: {ing.total_duplicates}, Errs: {ing.total_errors}",
            )
        elif skip_step and "ingest" in skip_step:
            table.add_row("Ingestion", "[blue]SKIPPED[/blue]", "-")
        else:
            table.add_row(
                "Ingestion",
                "[red]FAILED[/red]",
                report.errors[0] if report.errors else "Unknown error",
            )

        # Scoring Row
        if report.scoring:
            sc = report.scoring
            table.add_row(
                "Scoring",
                "[green]SUCCESS[/green]" if sc.failed_count == 0 else "[yellow]PARTIAL[/yellow]",
                f"Processed: {sc.total_processed}, Success: {sc.success_count}, Fail: {sc.failed_count}",
            )
        elif skip_step and "score" in skip_step:
            table.add_row("Scoring", "[blue]SKIPPED[/blue]", "-")
        else:
            table.add_row("Scoring", "[red]FAILED[/red]", "Check logs for details")

        # Notification Row
        if report.dispatch:
            disp = report.dispatch
            table.add_row(
                "Notification",
                "[green]SUCCESS[/green]" if disp.failure_count == 0 else "[yellow]PARTIAL[/yellow]",
                f"Pending: {disp.total_pending}, Success: {disp.success_count}, Fail: {disp.failure_count}",
            )
        elif skip_step and "notify" in skip_step:
            table.add_row("Notification", "[blue]SKIPPED[/blue]", "-")
        else:
            table.add_row("Notification", "[red]FAILED[/red]", "Check logs for details")

        table.add_section()
        status_style = "green" if report.overall_status == RunCycleStatus.SUCCESS else "yellow"
        if report.overall_status == RunCycleStatus.TOTAL_FAILURE:
            status_style = "red"

        table.add_row(
            "OVERALL",
            f"[{status_style}]{report.overall_status.value.upper()}[/{status_style}]",
            f"Duration: {report.total_duration_ms}ms",
            style="bold",
        )

        console.print(table)

        # Machine output: JSON at the end
        import json

        # Structured log for Action Summary
        logger.info(
            "pipeline_cycle_machine_report",
            overall_status=report.overall_status.value,
            total_duration_ms=report.total_duration_ms,
            ingestion=report.ingestion.model_dump(mode="json") if report.ingestion else None,
            scoring=report.scoring.model_dump(mode="json") if report.scoring else None,
            dispatch=report.dispatch.model_dump(mode="json") if report.dispatch else None,
        )

        console.print("\n[bold]Machine Report (JSON):[/bold]")
        console.print(json.dumps(report.model_dump(mode="json"), indent=2))

        if report.overall_status == RunCycleStatus.TOTAL_FAILURE:
            raise typer.Exit(code=1)

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.exception("Pipeline run-cycle failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@logs_app.command("tail")
def logs_tail(
    since: Annotated[
        str | None, typer.Option(help="Filter logs since this date/time (YYYY-MM-DD or relative)")
    ] = "1 day ago",
    level: Annotated[str | None, typer.Option(help="Filter by log level")] = None,
    event: Annotated[str | None, typer.Option(help="Filter by event type")] = None,
    module: Annotated[str | None, typer.Option(help="Filter by module name")] = None,
    correlation_id: Annotated[str | None, typer.Option(help="Filter by correlation ID")] = None,
) -> None:
    """Download and display the latest log artifacts from GitHub Actions."""
    logger.info(
        "Starting logs tail",
        since=since,
        level=level,
        event=event,
        module=module,
        correlation_id=correlation_id,
    )

    # 1. Download latest artifacts using gh CLI
    # We assume 'gh' is installed and authenticated in the environment where this runs
    # (e.g., local dev with gh login)
    try:
        console = Console()
        with console.status("[bold green]Downloading latest log artifacts..."):
            # List runs, get latest successful or failed pipeline-cycle
            # We use gh run list --workflow pipeline-cycle.yml --limit 1 --json databaseId
            import json

            run_info_cmd = [
                "gh",
                "run",
                "list",
                "--workflow",
                "pipeline-cycle.yml",
                "--limit",
                "1",
                "--json",
                "databaseId",
            ]
            run_result = subprocess.run(run_info_cmd, capture_output=True, text=True, check=True)
            runs = json.loads(run_result.stdout)

            if not runs:
                typer.echo("No recent pipeline-cycle runs found.")
                raise typer.Exit(code=1)

            run_id = runs[0]["databaseId"]
            temp_dir = Path(".logs_cache")
            temp_dir.mkdir(exist_ok=True)

            # Download artifact
            download_cmd = ["gh", "run", "download", str(run_id), "--dir", str(temp_dir)]
            subprocess.run(download_cmd, check=True, capture_output=True)

        # 2. Find and parse .jsonl files (using rglob to find in subdirs)
        log_files = list(temp_dir.rglob("*.jsonl"))
        if not log_files:
            typer.echo(f"No log files found in artifacts for run {run_id}.")
            raise typer.Exit(code=1)

        # 3. Process and filter
        from datetime import datetime, timedelta

        since_dt = datetime.min
        if since:
            if "day ago" in since or "days ago" in since:
                days = int(since.split()[0])
                since_dt = datetime.now() - timedelta(days=days)
            else:
                try:
                    since_dt = datetime.fromisoformat(since)
                except ValueError:
                    pass

        table = Table(box=None, header_style="bold blue")
        table.add_column("Timestamp", style="dim")
        table.add_column("Level")
        table.add_column("Event")
        table.add_column("Message")

        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        # Filter by since
                        ts_str = data.get("timestamp")
                        if ts_str:
                            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            # Make ts naive for comparison if since_dt is naive
                            if ts.tzinfo is not None:
                                ts = ts.replace(tzinfo=None)
                            if ts < since_dt:
                                continue

                        # Filter by level
                        log_lvl = data.get("level", "info").upper()
                        if level and log_lvl != level.upper():
                            continue

                        # Filter by event
                        evt = data.get("event", "")
                        if event and event.lower() not in evt.lower():
                            continue

                        # Filter by module
                        log_mod = data.get("module", "")
                        if module and module.lower() not in log_mod.lower():
                            continue

                        # Filter by correlation_id
                        log_cid = data.get("correlation_id", "")
                        if correlation_id and correlation_id != log_cid:
                            continue

                        # Format level color
                        lvl_style = "green"
                        if log_lvl == "WARNING":
                            lvl_style = "yellow"
                        elif log_lvl in ("ERROR", "CRITICAL"):
                            lvl_style = "red"

                        # Extract message (some logs use 'event' as msg, others have extra info)
                        msg_parts = []
                        for k, v in data.items():
                            if k not in ("timestamp", "level", "event"):
                                msg_parts.append(f"{k}={v}")
                        msg = " ".join(msg_parts)

                        table.add_row(
                            ts_str[:19] if ts_str else "-",
                            f"[{lvl_style}]{log_lvl}[/{lvl_style}]",
                            evt,
                            msg,
                        )
                    except Exception:
                        # Skip malformed lines (e.g. non-JSON output captured in .jsonl)
                        continue

        console.print(table)

    except subprocess.CalledProcessError as e:
        typer.echo(f"Error calling GitHub CLI: {e.stderr}", err=True)
        typer.echo("Ensure 'gh' is installed and authenticated (`gh auth login`).")
        raise typer.Exit(code=1)
    except Exception as e:
        logger.exception("Logs tail failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("check-cadence")
def outreach_check_cadence() -> None:
    """Run outreach cadence and ghosting checks."""
    from jobhunter.pipeline import run_outreach_cadence_checks

    logger.info("Starting outreach cadence checks")
    try:
        with get_session() as session:
            results = asyncio.run(run_outreach_cadence_checks(session))

            console = Console()
            table = Table(title="Outreach Cadence Report", header_style="bold magenta")
            table.add_column("Metric")
            table.add_column("Value", justify="right")

            table.add_row("Follow-ups Due", str(len(results["pending_followups"])))
            table.add_row("Messages Ghosted", str(results["ghosted_count"]))

            console.print(table)

            if results["pending_followups"]:
                console.print("\n[bold]Contacts due for follow-up:[/bold]")
                for contact in results["pending_followups"]:
                    console.print(f"- {contact.name} at {contact.company or 'Unknown'}")

            session.commit()

    except Exception as e:
        logger.exception("Outreach cadence checks failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("stats")
def outreach_stats(
    since: Annotated[
        str, typer.Option(help="Calculate stats since this date (YYYY-MM-DD or 'N weeks ago')")
    ] = "4 weeks ago",
) -> None:
    """Display outreach effectiveness statistics and response rates."""
    from jobhunter.dashboard.services.metrics import get_metrics_service

    # Resolve 'since' parameter
    since_dt: datetime
    if "weeks ago" in since:
        try:
            weeks = int(since.split()[0])
            since_dt = datetime.now() - timedelta(weeks=weeks)
        except (ValueError, IndexError):
            typer.echo(f"Error: Invalid 'since' format: {since}", err=True)
            raise typer.Exit(code=1)
    else:
        try:
            since_dt = datetime.fromisoformat(since)
        except ValueError:
            typer.echo(f"Error: Invalid 'since' date format: {since}. Use YYYY-MM-DD.", err=True)
            raise typer.Exit(code=1)

    try:
        with get_session() as session:
            service = get_metrics_service(session)
            stats = service.get_outreach_stats(since_dt.date())
            warmest = service.get_warmest_contacts(limit=5)

        console = Console()
        console.print(f"\n[bold blue]Outreach Statistics (Since {since_dt.date()})[/bold blue]\n")

        # Overview Table
        overview = Table(title="Global Overview", header_style="bold magenta")
        overview.add_column("Metric")
        overview.add_column("Value", justify="right")

        overview.add_row("Total Messages Sent", str(stats["total_sent"]))
        overview.add_row("Total Replies Received", str(stats["total_replied"]))
        overview.add_row(
            "Global Response Rate", f"[bold green]{stats['response_rate'] * 100:.1f}%[/bold green]"
        )
        overview.add_row("Mean Response Time", f"{stats['mean_response_time'] / 3600:.1f} hours")
        console.print(overview)

        # Status Counts Table
        status_table = Table(title="Message Lifecycle Status", header_style="bold cyan")
        status_table.add_column("Status")
        status_table.add_column("Count", justify="right")
        for status, count in stats["status_counts"].items():
            status_name = status.value if hasattr(status, "value") else str(status)
            status_table.add_row(status_name, str(count))
        console.print(status_table)

        # Breakdown by Template
        template_table = Table(title="Effectiveness by Template Type", header_style="bold yellow")
        template_table.add_column("Template Type")
        template_table.add_column("Sent", justify="right")
        template_table.add_column("Replied", justify="right")
        template_table.add_column("Rate", justify="right")
        for s in stats["template_stats"]:
            template_table.add_row(
                s["template_type"], str(s["sent"]), str(s["replied"]), f"{s['rate'] * 100:.1f}%"
            )
        console.print(template_table)

        # Breakdown by Market
        market_table = Table(title="Effectiveness by Market", header_style="bold green")
        market_table.add_column("Market")
        market_table.add_column("Sent", justify="right")
        market_table.add_column("Replied", justify="right")
        market_table.add_column("Rate", justify="right")
        for s in stats["market_stats"]:
            market_table.add_row(
                s["market"] or "Unknown",
                str(s["sent"]),
                str(s["replied"]),
                f"{s['rate'] * 100:.1f}%",
            )
        console.print(market_table)

        # Breakdown by Quality Score
        quality_table = Table(title="Effectiveness by Quality Score", header_style="bold blue")
        quality_table.add_column("Score Bin")
        quality_table.add_column("Sent", justify="right")
        quality_table.add_column("Replied", justify="right")
        quality_table.add_column("Rate", justify="right")
        for s in stats["quality_stats"]:
            quality_table.add_row(
                s["score_bin"], str(s["sent"]), str(s["replied"]), f"{s['rate'] * 100:.1f}%"
            )
        console.print(quality_table)

        # Warmest Contacts
        if warmest:
            warm_table = Table(title="Top 5 Warmest Contacts", header_style="bold red")
            warm_table.add_column("Name")
            warm_table.add_column("Company")
            warm_table.add_column("Status")
            warm_table.add_column("Last Contact")
            for c in warmest:
                last_contact = (
                    c["last_contacted_at"].strftime("%Y-%m-%d") if c["last_contacted_at"] else "-"
                )
                warm_table.add_row(c["name"], c["company"] or "-", c["status"], last_contact)
            console.print(warm_table)

    except Exception as e:
        logger.error("Outreach stats failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ab_test_app.command("create")
def ab_test_create(
    name: Annotated[str, typer.Option(help="Unique name for the test")],
    variants: Annotated[
        str, typer.Option(help="Comma-separated variants and weights, e.g. v1=0.5,v2=0.5")
    ],
    metric: Annotated[str, typer.Option(help="Target metric, e.g. tier_a_precision")],
    description: Annotated[Optional[str], typer.Option(help="Optional description")] = None,
) -> None:
    """Create a new A/B test."""
    from jobhunter.db.enums import ABTestStatus
    from jobhunter.db.models import ABTest

    variant_dict = {}
    try:
        for v in variants.split(","):
            v_name, weight = v.split("=")
            variant_dict[v_name.strip()] = float(weight)

        if abs(sum(variant_dict.values()) - 1.0) > 0.001:
            typer.echo("Error: Weights must sum to 1.0", err=True)
            raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error parsing variants: {e}", err=True)
        raise typer.Exit(code=1)

    try:
        with get_session() as session:
            test = ABTest(
                name=name,
                variants=variant_dict,
                metric_target=metric,
                description=description,
                status=ABTestStatus.ACTIVE,
                started_at=datetime.now(timezone.utc),
            )
            session.add(test)
            session.commit()
            typer.echo(f"Successfully created A/B test: {name}")
    except Exception as e:
        logger.error("Failed to create A/B test", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ab_test_app.command("results")
def ab_test_results(
    name: Annotated[str, typer.Argument(help="Name of the A/B test")],
) -> None:
    """Show results for an A/B test."""
    from jobhunter.analytics.ab_testing import get_ab_test_results

    try:
        with get_session() as session:
            results = get_ab_test_results(session, name)

        console = Console()
        console.print(f"\n[bold blue]A/B Test Results: {name}[/bold blue]")
        console.print(f"Metric Target: {results.metric_target}\n")

        table = Table(header_style="bold magenta")
        table.add_column("Variant")
        table.add_column("Sample Size", justify="right")
        table.add_column("Conversions", justify="right")
        table.add_column("Rate", justify="right")
        table.add_column("95% Conf. Interval", justify="right")

        for v in results.variants:
            if v.sample_size < 30:
                v_name = f"{v.variant} [yellow](N<30)[/yellow]"
            else:
                v_name = v.variant

            table.add_row(
                v_name,
                str(v.sample_size),
                str(v.conversions),
                f"{v.conversion_rate:.2%}",
                f"[{v.confidence_interval[0]:.2%}, {v.confidence_interval[1]:.2%}]",
            )

        console.print(table)

        sig_style = "green" if results.statistical_significance else "yellow"
        console.print(f"\nP-value: [bold]{results.p_value:.4f}[/bold]")
        console.print(
            f"Statistically Significant: [{sig_style}]{results.statistical_significance}[/{sig_style}]"
        )

    except Exception as e:
        logger.error("Failed to retrieve A/B test results", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@ab_test_app.command("conclude")
def ab_test_conclude(
    name: Annotated[str, typer.Argument(help="Name of the A/B test")],
    winner: Annotated[str, typer.Option(help="The winning variant")],
    conclusion: Annotated[str, typer.Option(help="Conclusion notes")],
) -> None:
    """Conclude an A/B test and pick a winner."""
    from jobhunter.analytics.ab_testing import get_ab_test_results
    from jobhunter.db.enums import ABTestStatus
    from jobhunter.db.models import ABTest

    try:
        with get_session() as session:
            test = session.scalar(select(ABTest).where(ABTest.name == name))
            if not test:
                typer.echo(f"Error: A/B test '{name}' not found.", err=True)
                raise typer.Exit(code=1)

            if test.status != ABTestStatus.ACTIVE:
                typer.echo(f"Error: Test '{name}' is already {test.status}.", err=True)
                raise typer.Exit(code=1)

            # Rule: Sample size minimum 30 per variant
            results = get_ab_test_results(session, name)
            for v in results.variants:
                if v.sample_size < 30:
                    typer.echo(
                        f"Error: Sample size for variant '{v.variant}' is too small "
                        f"({v.sample_size} < 30). Cannot conclude.",
                        err=True,
                    )
                    raise typer.Exit(code=1)

            if winner not in test.variants:
                typer.echo(f"Error: Winner '{winner}' is not a valid variant.", err=True)
                raise typer.Exit(code=1)

            test.status = ABTestStatus.CONCLUDED
            test.ended_at = datetime.now(timezone.utc)
            test.conclusion = f"Winner: {winner}. {conclusion}"
            session.commit()
            typer.echo(f"Successfully concluded A/B test: {name}. Winner: {winner}")

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.error("Failed to conclude A/B test", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("check-regressions")
def analytics_check_regressions(
    notify: Annotated[
        bool, typer.Option(help="Send alerts to Telegram if regressions found")
    ] = True,
    markdown_output: Annotated[
        bool, typer.Option("--markdown", help="Output in Markdown format")
    ] = False,
) -> None:
    """Check for significant drops in key metrics (last 7 days vs 4-week baseline)."""
    logger.info("Starting regression check")
    try:
        with get_session() as session:
            report = check_metrics(session)

            if markdown_output:
                typer.echo("### 📉 Regression Analysis")
                typer.echo("| Metric | Baseline | Current | Change (%) | Status |")
                typer.echo("| :--- | :---: | :---: | :---: | :--- |")
                for m in report.metrics:
                    status = "✅ OK"
                    if m.is_regression:
                        status = "🚨 **REGRESSION**"
                    change_sign = "+" if m.change_pct > 0 else ""
                    typer.echo(
                        f"| {m.name} | {m.baseline_value:.2f}% | {m.current_value:.2f}% | {change_sign}{m.change_pct:.2f}% | {status} |"
                    )
            else:
                console = Console()
                table = Table(title="Regression Analysis", header_style="bold magenta")
                table.add_column("Metric")
                table.add_column("Baseline", justify="right")
                table.add_column("Current", justify="right")
                table.add_column("Change (%)", justify="right")
                table.add_column("Status")

                for m in report.metrics:
                    status = "[green]OK[/green]"
                    if m.is_regression:
                        status = "[bold red]REGRESSION[/bold red]"

                    change_style = "red" if m.change_pct < 0 else "green"
                    table.add_row(
                        m.name,
                        f"{m.baseline_value:.2f}%",
                        f"{m.current_value:.2f}%",
                        f"[{change_style}]{m.change_pct:+.2f}%[/{change_style}]",
                        status,
                    )

                console.print(table)

            regressions = [m for m in report.metrics if m.is_regression]

            if notify and regressions:
                from jobhunter.notify.telegram import TelegramNotifier
                from jobhunter.notify import NotificationMessage
                from jobhunter.notify.templates import render

                settings = Settings()  # type: ignore[call-arg]
                notifier = TelegramNotifier()
                if notifier.is_enabled(settings):
                    from jobhunter.db.models import NotificationSent

                    repo = NotificationsRepo(session)
                    for m in regressions:
                        # Anti-flapping: bucketed dedup_key
                        # bucketed by 20% intervals to allow re-alerting if it gets significantly worse
                        # Use absolute value of change_pct for bucketing
                        bucket = int(abs(m.change_pct) // 20)
                        dedup_key = f"regression:{m.name.lower().replace(' ', '_')}:b{bucket}"

                        # Check if already sent in last 3 days
                        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
                        stmt = select(NotificationSent).where(
                            NotificationSent.channel == "telegram",
                            NotificationSent.dedup_key == dedup_key,
                            NotificationSent.sent_at >= three_days_ago,
                            NotificationSent.success,
                        )
                        if session.scalar(stmt):
                            logger.info(
                                "Regression alert skipped (anti-flapping)",
                                metric=m.name,
                                dedup_key=dedup_key,
                            )
                            continue

                        body = render(
                            "notifications/regression_alert.md",
                            {"type": "Regresión", "metric": m, "context": report.inferred_context},
                        )
                        msg = NotificationMessage(
                            channel="telegram",
                            body_text=body,
                            metadata={"type": "regression_alert", "metric": m.name},
                        )
                        res = asyncio.run(notifier.send(msg))
                        repo.record_sent("telegram", dedup_key, None, res)
                    session.commit()

    except Exception as e:
        logger.exception("Regression check failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("false-rejects")
def analytics_false_rejects(
    limit: Annotated[int, typer.Option(help="Maximum number of false rejects to show")] = 10,
    days: Annotated[int, typer.Option(help="Number of days to look back")] = 60,
) -> None:
    """List jobs that were rejected by the system but manually promoted by the user."""
    from jobhunter.analytics.quality_metrics import get_false_rejects_detailed

    logger.info("Starting false rejects analysis", limit=limit, days=days)
    try:
        with get_session() as session:
            rejects = get_false_rejects_detailed(session, limit=limit, days=days)

        console = Console()
        if not rejects:
            console.print(
                "[yellow]No se encontraron false rejects en el periodo especificado.[/yellow]"
            )
            return

        table = Table(title=f"False Rejects (Últimos {days} días)", header_style="bold magenta")
        table.add_column("Empresa", style="bold")
        table.add_column("Título")
        table.add_column("Razón REJECT Original", style="dim")
        table.add_column("Razón Promoción Manual")

        for r in rejects:
            table.add_row(
                r.company,
                r.title,
                r.original_reject_reason or "N/A",
                r.manual_promotion_reason or "N/A",
            )

        console.print(table)
    except Exception as e:
        logger.error("False rejects analysis failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("missed-opportunities")
def analytics_missed_opportunities(
    limit: Annotated[int, typer.Option(help="Maximum number of candidates to show")] = 10,
    days: Annotated[int, typer.Option(help="Number of days to look back")] = 60,
) -> None:
    """Identify jobs that were rejected but might be candidates for re-scoring based on heuristics."""
    from jobhunter.analytics.quality_metrics import get_missed_opportunities

    logger.info("Starting missed opportunities analysis", limit=limit, days=days)
    try:
        with get_session() as session:
            candidates = get_missed_opportunities(session, limit=limit, days=days)

        console = Console()
        if not candidates:
            console.print("[yellow]No se encontraron missed opportunities potenciales.[/yellow]")
            return

        table = Table(
            title=f"Missed Opportunities Candidates (Últimos {days} días)", header_style="bold blue"
        )
        table.add_column("ID", style="dim")
        table.add_column("Empresa", style="bold")
        table.add_column("Título")
        table.add_column("Red Flags")
        table.add_column("Score", justify="right")

        for c in candidates:
            table.add_row(
                c.job_id[:8],
                c.company,
                c.title,
                ", ".join(c.red_flags),
                str(c.fit_score or "-"),
            )

        console.print(table)
        console.print("\n[italic]Usa 'rescore-suspicious' para re-evaluar estos jobs.[/italic]")
    except Exception as e:
        logger.error("Missed opportunities analysis failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("report")
def analytics_report(
    month: Annotated[
        Optional[str], typer.Option(help="Month to report on (YYYY-MM), defaults to last month")
    ] = None,
    output: Annotated[str, typer.Option(help="Output format (md, html, pdf)")] = "md",
    send_email: Annotated[bool, typer.Option("--send-email", help="Send report via email")] = False,
) -> None:
    """Generate a narrative monthly analytics report."""
    from jobhunter.analytics.report_generator import (
        get_month_range,
        collect_metrics_for_period,
        calculate_comparison,
        generate_narrative_report,
        format_report_as_html,
        convert_html_to_pdf,
    )

    logger.info("Starting monthly report generation", month=month, output=output)

    # 1. Resolve month
    now = datetime.now(timezone.utc)
    if month:
        try:
            year, month_int = map(int, month.split("-"))
            report_month_date = date(year, month_int, 1)
        except ValueError:
            typer.echo(f"Error: Invalid month format: {month}. Use YYYY-MM.", err=True)
            raise typer.Exit(code=1)
    else:
        # Default to previous month
        first_of_this_month = now.replace(day=1)
        report_month_date = (first_of_this_month - timedelta(days=1)).replace(day=1).date()
        year = report_month_date.year
        month_int = report_month_date.month

    month_label = report_month_date.strftime("%Y-%m")

    # 2. Collect metrics
    try:
        with get_session() as session:
            # Current month
            start_date, end_date = get_month_range(year, month_int)
            current_metrics = collect_metrics_for_period(session, start_date, end_date, month_label)

            # Previous month
            prev_month_date = (report_month_date - timedelta(days=1)).replace(day=1)
            p_start, p_end = get_month_range(prev_month_date.year, prev_month_date.month)
            prev_metrics = collect_metrics_for_period(session, p_start, p_end, "Prev Month")

            # Previous quarter (average)
            # For simplicity, we just take the last 3 months before report_month
            q_start = (report_month_date - timedelta(days=90)).replace(day=1)
            q_end = report_month_date - timedelta(days=1)
            prev_quarter_metrics = collect_metrics_for_period(
                session, q_start, q_end, "Prev Quarter"
            )

            # Comparisons
            prev_month_comp = calculate_comparison(current_metrics, prev_metrics)
            prev_quarter_comp = calculate_comparison(current_metrics, prev_quarter_metrics)

            # Anomalies (check_metrics uses fixed 7d vs 28d window, but it's better than nothing)
            anomalies = check_metrics(session)

            # 3. Generate narrative
            settings = Settings()  # type: ignore[call-arg]
            llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

            console = Console()
            with console.status(f"[bold green]Generating narrative report for {month_label}..."):
                report_md = asyncio.run(
                    generate_narrative_report(
                        session,
                        llm_client,
                        month_label,
                        current_metrics,
                        prev_month_comp,
                        prev_quarter_comp,
                        anomalies,
                    )
                )

            # 4. Save and Format
            reports_dir = Path("reports")
            reports_dir.mkdir(exist_ok=True)

            base_filename = f"{month_label}-monthly"
            md_path = reports_dir / f"{base_filename}.md"
            md_path.write_text(report_md)
            typer.echo(f"Markdown report saved to {md_path}")

            if output == "md":
                console.print(Markdown(report_md))
            elif output == "html":
                html_report = format_report_as_html(report_md, month_label)
                html_path = reports_dir / f"{base_filename}.html"
                html_path.write_text(html_report)
                typer.echo(f"HTML report saved to {html_path}")
            elif output == "pdf":
                html_report = format_report_as_html(report_md, month_label)
                pdf_path = reports_dir / f"{base_filename}.pdf"
                convert_html_to_pdf(html_report, str(pdf_path))
                typer.echo(f"PDF report saved to {pdf_path}")
            else:
                typer.echo(f"Warning: Unknown output format '{output}'. Only saved as .md")

            if send_email:
                from jobhunter.notify.email import EmailNotifier
                from jobhunter.notify.base import NotificationMessage

                notifier = EmailNotifier()
                settings = Settings()  # type: ignore[call-arg]

                if not notifier.is_enabled(settings):
                    typer.echo("Error: Email notifier is not enabled. Cannot send report.", err=True)
                else:
                    typer.echo(f"Sending report for {month_label} via email...")

                    pdf_path = reports_dir / f"{base_filename}.pdf"
                    if not pdf_path.exists():
                        # Generate PDF if it doesn't exist yet
                        html_report = format_report_as_html(report_md, month_label)
                        convert_html_to_pdf(html_report, str(pdf_path))

                    with open(pdf_path, "rb") as f:
                        pdf_content = f.read()

                    msg = NotificationMessage(
                        channel="email",
                        subject=f"Monthly Analytics Report: {month_label}",
                        body_text=f"Please find attached the monthly analytics report for {month_label}.",
                        body_html=format_report_as_html(report_md, month_label),
                        attachments=[{"filename": f.name, "content": pdf_content}],
                    )

                    result = asyncio.run(notifier.send(msg))
                    if result.success:
                        typer.echo("Email sent successfully.")
                    else:
                        typer.echo(f"Failed to send email: {result.error}", err=True)

    except Exception as e:
        logger.exception("Report generation failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("rescore-suspicious")
def analytics_rescore_suspicious(
    limit: Annotated[int, typer.Option(help="Maximum number of jobs to rescore")] = 5,
    confirm: Annotated[bool, typer.Option(help="If True, actually persist changes to DB")] = False,
) -> None:
    """Re-score potential missed opportunities with the latest prompt/model."""
    from jobhunter.analytics.quality_metrics import (
        get_missed_opportunities,
        rescore_suspicious_jobs,
    )
    from jobhunter.scoring.scorer import JobScorer
    from jobhunter.llm.anthropic_client import AnthropicLLMClient

    logger.info("Starting rescore-suspicious", limit=limit, confirm=confirm)
    try:
        settings = Settings()  # type: ignore[call-arg]
        llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
        scorer = JobScorer(llm_client=llm_client)

        with get_session() as session:
            candidates_meta = get_missed_opportunities(session, limit=limit)
            job_ids = [uuid.UUID(c.job_id) for c in candidates_meta]

            jobs = session.query(Job).filter(Job.id.in_(job_ids)).all()

            if not jobs:
                typer.echo("No pending suspicious jobs to rescore.")
                return

            console = Console()
            with console.status("[bold green]Re-scoring suspicious jobs..."):
                reports = asyncio.run(
                    rescore_suspicious_jobs(session, scorer, jobs, confirm=not confirm)
                )

        table = Table(title=f"Rescoring suspicious report ({'PROD' if confirm else 'DRY RUN'})")
        table.add_column("Job", style="bold")
        table.add_column("Old Tier")
        table.add_column("New Tier")
        table.add_column("Improved?")

        for r in reports:
            imp_style = "green" if r.improved else "red"
            table.add_row(
                f"{r.company} - {r.title}",
                str(r.old_tier),
                str(r.new_tier),
                f"[{imp_style}]{r.improved}[/{imp_style}]",
            )

        console.print(table)

        if not confirm:
            console.print(
                "\n[yellow]NOTE: This was a DRY RUN. Use --confirm to persist changes.[/yellow]"
            )

    except Exception as e:
        logger.error("Rescore suspicious failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("check-anomalies")
def analytics_check_anomalies(
    notify: Annotated[bool, typer.Option(help="Send alerts to Telegram if anomalies found")] = True,
    markdown_output: Annotated[
        bool, typer.Option("--markdown", help="Output in Markdown format")
    ] = False,
) -> None:
    """Check for unexpected upward spikes in key metrics."""
    logger.info("Starting anomaly check")
    try:
        with get_session() as session:
            report = check_metrics(session)

            if markdown_output:
                typer.echo("### 🚀 Anomaly Analysis")
                typer.echo("| Metric | Baseline | Current | Change (%) | Status |")
                typer.echo("| :--- | :---: | :---: | :---: | :--- |")
                for m in report.metrics:
                    status = "✅ OK"
                    if m.is_anomaly:
                        status = "⚠️ **ANOMALY**"
                    change_sign = "+" if m.change_pct > 0 else ""
                    typer.echo(
                        f"| {m.name} | {m.baseline_value:.2f}% | {m.current_value:.2f}% | {change_sign}{m.change_pct:.2f}% | {status} |"
                    )
            else:
                console = Console()
                table = Table(title="Anomaly Analysis", header_style="bold blue")
                table.add_column("Metric")
                table.add_column("Baseline", justify="right")
                table.add_column("Current", justify="right")
                table.add_column("Change (%)", justify="right")
                table.add_column("Status")

                for m in report.metrics:
                    status = "[green]OK[/green]"
                    if m.is_anomaly:
                        status = "[bold yellow]ANOMALY[/bold yellow]"

                    change_style = "green" if m.change_pct > 0 else "red"
                    table.add_row(
                        m.name,
                        f"{m.baseline_value:.2f}%",
                        f"{m.current_value:.2f}%",
                        f"[{change_style}]{m.change_pct:+.2f}%[/{change_style}]",
                        status,
                    )

                console.print(table)

            anomalies = [m for m in report.metrics if m.is_anomaly]

            if notify and anomalies:
                from jobhunter.notify.telegram import TelegramNotifier
                from jobhunter.notify import NotificationMessage
                from jobhunter.notify.templates import render
                from jobhunter.db.models import NotificationSent

                settings = Settings()  # type: ignore[call-arg]
                notifier = TelegramNotifier()
                if notifier.is_enabled(settings):
                    repo = NotificationsRepo(session)
                    for m in anomalies:
                        bucket = int(abs(m.change_pct) // 20)
                        dedup_key = f"anomaly:{m.name.lower().replace(' ', '_')}:b{bucket}"

                        three_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
                        stmt = select(NotificationSent).where(
                            NotificationSent.channel == "telegram",
                            NotificationSent.dedup_key == dedup_key,
                            NotificationSent.sent_at >= three_days_ago,
                            NotificationSent.success,
                        )
                        if session.scalar(stmt):
                            logger.info(
                                "Anomaly alert skipped (anti-flapping)",
                                metric=m.name,
                                dedup_key=dedup_key,
                            )
                            continue

                        body = render(
                            "notifications/regression_alert.md",
                            {"type": "Anomalía", "metric": m, "context": report.inferred_context},
                        )
                        msg = NotificationMessage(
                            channel="telegram",
                            body_text=body,
                            metadata={"type": "anomaly_alert", "metric": m.name},
                        )
                        res = asyncio.run(notifier.send(msg))
                        repo.record_sent("telegram", dedup_key, None, res)
                    session.commit()

    except Exception as e:
        logger.exception("Anomaly check failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@analytics_app.command("recommendations")
def analytics_recommendations(
    json_output: Annotated[bool, typer.Option("--json", help="Output in JSON format")] = False,
    markdown_output: Annotated[
        bool, typer.Option("--markdown", help="Output in Markdown format")
    ] = False,
) -> None:
    """Display actionable recommendations based on system heuristics."""
    from jobhunter.analytics.recommendations import get_recommendations
    import json

    logger.info("Starting recommendations analysis")
    try:
        with get_session() as session:
            recs = get_recommendations(session)

        if json_output:
            typer.echo(json.dumps([r.model_dump() for r in recs], indent=2))
            return

        if markdown_output:
            typer.echo("### 💡 Recommendations")
            if not recs:
                typer.echo("No recommendations at this time. System is performing well!")
                return
            typer.echo("| Priority | Action | Reason | Impact | Effort |")
            typer.echo("| :--- | :--- | :--- | :--- | :--- |")
            for r in recs:
                typer.echo(
                    f"| **{r.priority}** | {r.action} | {r.reason} | {r.impact} | {r.effort} |"
                )
            return

        console = Console()
        if not recs:
            console.print(
                "[green]No recommendations at this time. System is performing well![/green]"
            )
            return

        table = Table(title="Actionable Recommendations", header_style="bold magenta")
        table.add_column("Priority", style="bold")
        table.add_column("Action", style="bold")
        table.add_column("Reason")
        table.add_column("Impact")
        table.add_column("Effort")

        for r in recs:
            p_style = "red" if r.priority == "P1" else "yellow" if r.priority == "P2" else "blue"
            table.add_row(
                f"[{p_style}]{r.priority}[/{p_style}]",
                r.action,
                r.reason,
                r.impact,
                r.effort,
            )

        console.print(table)
    except Exception as e:
        logger.error("Recommendations analysis failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@telegram_app.command("process-callbacks")
def telegram_process_callbacks() -> None:
    """Process pending Telegram callback updates."""
    logger.info("Starting Telegram callback processing")
    try:
        from jobhunter.notify.telegram import TelegramNotifier

        notifier = TelegramNotifier()
        with get_session() as session:
            count = asyncio.run(notifier.process_callback_updates(session))

        if count > 0:
            typer.echo(f"Successfully processed {count} Telegram callbacks.")
        else:
            typer.echo("No pending Telegram callbacks found.")
    except Exception as e:
        logger.error("Failed to process Telegram callbacks", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("add")
def outreach_add(
    name: Annotated[str, typer.Option(help="Name of the contact")],
    linkedin_url: Annotated[Optional[str], typer.Option(help="LinkedIn URL of the contact")] = None,
    company: Annotated[Optional[str], typer.Option(help="Company of the contact")] = None,
    role: Annotated[Optional[str], typer.Option(help="Role of the contact")] = None,
    market: Annotated[Optional[OutreachMarket], typer.Option(help="Market of the contact")] = None,
    notes: Annotated[Optional[str], typer.Option(help="Additional notes")] = None,
) -> None:
    """Add a new outreach contact manually."""
    from jobhunter.outreach.scoring import (
        calculate_heuristic_score,
        infer_market,
        infer_specialty_stack,
    )
    from jobhunter.cli.formatters import format_contact_row

    try:
        with get_session() as session:
            repo = OutreachRepo(session)

            if linkedin_url:
                existing = repo.find_by_linkedin_url(linkedin_url)
                if existing:
                    typer.echo(
                        f"Error: Contact with LinkedIn URL {linkedin_url} already exists.", err=True
                    )
                    raise typer.Exit(code=1)

            # Heuristic market inference if not provided
            if not market:
                market = infer_market(company, role)

            specialty_stack = infer_specialty_stack(role)

            contact = OutreachContact(
                name=name,
                linkedin_url=linkedin_url,
                company=company,
                role=role,
                market=market,
                specialty_stack=specialty_stack,
                notes=notes,
                status=OutreachStatus.NEW,
            )

            # Load candidate profile for heuristic scoring
            profile_path = Path("prompts/candidate_profile.yaml")
            candidate_profile = {}
            if profile_path.exists():
                candidate_profile = yaml.safe_load(profile_path.read_text())

            contact.quality_score = calculate_heuristic_score(contact, candidate_profile)

            session.add(contact)
            session.commit()
            session.refresh(contact)

            console = Console()
            table = Table(title="Contact Created")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Company")
            table.add_column("Role")
            table.add_column("Score")
            table.add_column("Status")
            table.add_column("Last Contacted")

            table.add_row(*format_contact_row(contact))
            console.print(table)

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.error("Failed to add outreach contact", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("candidates")
def outreach_candidates(
    limit: Annotated[int, typer.Option(help="Maximum number of candidates to show")] = 10,
    market: Annotated[Optional[OutreachMarket], typer.Option(help="Filter by market")] = None,
    min_score: Annotated[Optional[int], typer.Option(help="Minimum quality score")] = None,
) -> None:
    """List prioritized outreach candidates."""
    from jobhunter.cli.formatters import format_contact_row

    try:
        with get_session() as session:
            stmt = select(OutreachContact)
            if market:
                stmt = stmt.where(OutreachContact.market == market)
            if min_score is not None:
                stmt = stmt.where(OutreachContact.quality_score >= min_score)

            # Ordenamiento literal del AC original: quality_score DESC, last_contacted_at ASC NULLS FIRST
            stmt = stmt.order_by(
                OutreachContact.quality_score.desc().nulls_last(),
                asc(OutreachContact.last_contacted_at).nulls_first(),
            ).limit(limit)

            contacts = session.scalars(stmt).all()

            console = Console()
            table = Table(title="Outreach Candidates")
            table.add_column("ID")
            table.add_column("Name")
            table.add_column("Company")
            table.add_column("Role")
            table.add_column("Score")
            table.add_column("Status")
            table.add_column("Last Contacted")

            for contact in contacts:
                table.add_row(*format_contact_row(contact))

            console.print(table)

    except Exception as e:
        logger.error("Failed to list candidates", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("draft")
def outreach_draft(
    contact_id: Annotated[str, typer.Argument(help="UUID of the contact")],
    type: Annotated[OutreachTemplateType, typer.Option(help="Template type to use")],
    note: Annotated[str, typer.Option(help="Research notes (min 20 chars)")],
    language: Annotated[str, typer.Option(help="Target language (en/es)")] = "en",
    copy: Annotated[bool, typer.Option(help="Copy to clipboard")] = False,
) -> None:
    """Generate an outreach message draft for a contact."""
    from jobhunter.outreach.generator import generate_message

    try:
        contact_uuid = uuid.UUID(contact_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {contact_id}", err=True)
        raise typer.Exit(code=1)

    if len(note) < 20:
        typer.echo("Error: research notes must be at least 20 characters long.", err=True)
        raise typer.Exit(code=1)

    try:
        settings = Settings()  # type: ignore[call-arg]
        llm_client = AnthropicLLMClient(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

        with get_session() as session:
            contact = session.get(OutreachContact, contact_uuid)
            if not contact:
                typer.echo(f"Error: Contact {contact_id} not found.", err=True)
                raise typer.Exit(code=1)

            message = asyncio.run(
                generate_message(
                    contact=contact,
                    template_type=type,
                    research_notes=note,
                    llm_client=llm_client,
                    session=session,
                    settings=settings,
                    target_language=language,
                )
            )

            console = Console()
            console.print(f"\n[bold blue]Generated Message for {contact.name}[/bold blue]\n")
            console.print(Markdown(message.body))
            console.print(f"\n[dim]Message ID: {message.id}[/dim]")
            console.print(f"[dim]To mark as sent: jobhunter outreach sent {message.id}[/dim]\n")

            if copy:
                try:
                    import pyperclip  # type: ignore[import-untyped]

                    pyperclip.copy(message.body)
                    typer.echo("Message body copied to clipboard.")
                except ImportError:
                    typer.echo(
                        "Error: pyperclip not installed. Install it with 'pip install pyperclip' to use --copy.",
                        err=True,
                    )
                except Exception as e:
                    typer.echo(f"Warning: Could not copy to clipboard: {e}")

    except ValueError as e:
        # Probablemente política de 2 toques
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error("Failed to generate outreach draft", contact_id=contact_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("sent")
def outreach_sent(
    message_id: Annotated[str, typer.Argument(help="UUID of the message")],
    at: Annotated[
        Optional[datetime], typer.Option(help="ISO 8601 timestamp (default: now)")
    ] = None,
) -> None:
    """Mark an outreach message as sent."""
    try:
        msg_uuid = uuid.UUID(message_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {message_id}", err=True)
        raise typer.Exit(code=1)

    try:
        with get_session() as session:
            repo = OutreachMessageRepo(session)
            msg = repo.get(msg_uuid)
            if not msg:
                typer.echo(f"Error: Message {message_id} not found.", err=True)
                raise typer.Exit(code=1)

            repo.mark_sent(msg_uuid, sent_at=at)
            session.commit()
            typer.echo(f"Message {message_id} marked as SENT.")

    except Exception as e:
        logger.error("Failed to mark message as sent", message_id=message_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("replied")
def outreach_replied(
    message_id: Annotated[str, typer.Argument(help="UUID of the message")],
    at: Annotated[
        Optional[datetime], typer.Option(help="ISO 8601 timestamp (default: now)")
    ] = None,
) -> None:
    """Mark an outreach message as replied."""
    try:
        msg_uuid = uuid.UUID(message_id)
    except ValueError:
        typer.echo(f"Error: Invalid UUID format: {message_id}", err=True)
        raise typer.Exit(code=1)

    try:
        with get_session() as session:
            repo = OutreachMessageRepo(session)
            msg = repo.get(msg_uuid)
            if not msg:
                typer.echo(f"Error: Message {message_id} not found.", err=True)
                raise typer.Exit(code=1)

            repo.mark_replied(msg_uuid, replied_at=at)
            session.commit()
            typer.echo(f"Message {message_id} marked as REPLIED.")

    except Exception as e:
        logger.error("Failed to mark message as replied", message_id=message_id, error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("list")
def outreach_list_cmd(
    status: Annotated[
        Optional[list[OutreachMessageStatus]],
        typer.Option(help="Filter by status (can be repeated)"),
    ] = None,
    contact_id: Annotated[Optional[str], typer.Option(help="Filter by contact UUID")] = None,
    last: Annotated[int, typer.Option(help="Show messages from the last N days")] = 14,
) -> None:
    """List outreach messages with filters."""
    from jobhunter.cli.formatters import format_message_row
    from sqlalchemy.orm import selectinload

    try:
        with get_session() as session:
            stmt = select(OutreachMessage).options(selectinload(OutreachMessage.contact))

            if status:
                stmt = stmt.where(OutreachMessage.status.in_(status))

            if contact_id:
                try:
                    stmt = stmt.where(OutreachMessage.contact_id == uuid.UUID(contact_id))
                except ValueError:
                    typer.echo(f"Error: Invalid contact UUID format: {contact_id}", err=True)
                    raise typer.Exit(code=1)

            if last:
                since = datetime.now(timezone.utc) - timedelta(days=last)
                stmt = stmt.where(OutreachMessage.created_at >= since)

            stmt = stmt.order_by(OutreachMessage.created_at.desc())
            messages = session.scalars(stmt).all()

            console = Console()
            table = Table(title="Outreach Messages")
            table.add_column("ID")
            table.add_column("Contact")
            table.add_column("Type")
            table.add_column("Status")
            table.add_column("Created At")
            table.add_column("Sent At")
            table.add_column("Replied At")

            for msg in messages:
                table.add_row(*format_message_row(msg))

            console.print(table)

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.error("Failed to list outreach messages", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@outreach_app.command("import")
def outreach_import(
    from_path: Annotated[Path, typer.Option("--from", help="Path to the CSV file to import")],
    mapping_file: Annotated[
        Optional[Path], typer.Option("--mapping", help="Path to a JSON file with column mapping")
    ] = None,
    enrich_with_ai: Annotated[
        bool, typer.Option("--enrich-with-ai", help="Enrich contacts with AI scoring")
    ] = False,
) -> None:
    """Import outreach contacts from a CSV file (LinkedIn or generic)."""
    import json
    import yaml
    from jobhunter.outreach.linkedin_csv import LinkedInCSVParser
    from jobhunter.outreach.scoring import (
        infer_market,
        infer_specialty_stack,
        calculate_heuristic_score,
        enrich_contact_with_ai,
    )
    from jobhunter.db.repos.outreach import OutreachRepo

    if not from_path.exists():
        typer.echo(f"Error: File not found: {from_path}", err=True)
        raise typer.Exit(code=1)

    mapping = None
    if mapping_file:
        if not mapping_file.exists():
            typer.echo(f"Error: Mapping file not found: {mapping_file}", err=True)
            raise typer.Exit(code=1)
        with open(mapping_file, "r") as f:
            mapping = json.load(f)

    logger.info("Starting outreach import", from_path=str(from_path), enrich_with_ai=enrich_with_ai)

    try:
        content = from_path.read_text(encoding="utf-8")
        parsed_contacts = LinkedInCSVParser.parse(content, mapping=mapping)

        if not parsed_contacts:
            typer.echo("No valid contacts found in the CSV.")
            return

        # Load candidate profile for heuristic scoring
        profile_path = Path("prompts/candidate_profile.yaml")
        candidate_profile = {}
        if profile_path.exists():
            candidate_profile = yaml.safe_load(profile_path.read_text())

        # Enrich with heuristics
        for c_data in parsed_contacts:
            c_data["market"] = infer_market(c_data.get("company"), c_data.get("role"))
            c_data["specialty_stack"] = infer_specialty_stack(c_data.get("role"))

            # Temporary contact for scoring
            temp_contact = OutreachContact(
                name=c_data["name"],
                company=c_data.get("company"),
                role=c_data.get("role"),
                specialty_stack=c_data.get("specialty_stack"),
            )
            c_data["quality_score"] = calculate_heuristic_score(temp_contact, candidate_profile)

        with get_session() as session:
            repo = OutreachRepo(session)

            if enrich_with_ai:
                settings = Settings()  # type: ignore[call-arg]
                llm_client = AnthropicLLMClient(
                    api_key=settings.ANTHROPIC_API_KEY.get_secret_value()
                )

                console = Console()
                with console.status("[bold green]Enriching contacts with AI..."):
                    for c_data in parsed_contacts:
                        # Only enrich if it hasn't been skipped/failed (handled by repo later, but let's be efficient)
                        existing = repo.find_by_linkedin_url(c_data["linkedin_url"])
                        if existing:
                            continue

                        temp_contact = OutreachContact(
                            name=c_data["name"],
                            company=c_data.get("company"),
                            role=c_data.get("role"),
                            quality_score=c_data["quality_score"],
                        )
                        # We don't save temp_contact to DB yet, we just pass it to AI
                        c_data["quality_score"] = asyncio.run(
                            enrich_contact_with_ai(temp_contact, llm_client, session)
                        )

            imported, skipped, failed = repo.process_import_batch(parsed_contacts)
            session.commit()

        # Output results
        console = Console()
        table = Table(title="Outreach Import Results")
        table.add_column("Status", style="bold")
        table.add_column("Count", justify="right")

        table.add_row("Imported", f"[green]{imported}[/green]")
        table.add_row("Skipped (Duplicate)", f"[yellow]{skipped}[/yellow]")
        table.add_row("Failed (Validation)", f"[red]{failed}[/red]")

        console.print(table)

    except Exception as e:
        logger.error("Outreach import failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@email_app.command("auth")
def email_auth(
    revoke: Annotated[bool, typer.Option(help="Revoke existing tokens")] = False,
) -> None:
    """Authenticate with Gmail via OAuth2."""
    from jobhunter.auth.google import GoogleOAuthHandler

    settings = Settings()  # type: ignore[call-arg]
    try:
        with get_session() as session:
            handler = GoogleOAuthHandler(session, settings)

            if revoke:
                emails = handler.list_authenticated_emails()
                if not emails:
                    typer.echo("No authenticated Gmail accounts found.")
                    return

                for email in emails:
                    if typer.confirm(f"Revoke tokens for {email}?"):
                        if handler.revoke_tokens(email):
                            typer.echo(f"Successfully revoked tokens for {email}.")
                        else:
                            typer.echo(f"Failed to revoke tokens for {email}.", err=True)
                return

            typer.echo("Starting Gmail OAuth2 authentication flow...")
            typer.echo("A browser window will open to complete the process.")

            result = handler.run_local_server_flow()

            typer.echo("-" * 40)
            typer.echo(f"Authentication successful for: {result['email']}")
            typer.echo(f"Granted scopes: {', '.join(result['scopes'])}")
            typer.echo("-" * 40)

    except Exception as e:
        logger.error("Gmail auth failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@email_app.command("stats")
def email_stats(
    since: Annotated[
        str, typer.Option(help="Calculate stats since this date (YYYY-MM-DD or 'N weeks ago')")
    ] = "4 weeks ago",
    strict: Annotated[
        bool, typer.Option("--strict", help="Exit with code 1 if precision < 85%")
    ] = False,
) -> None:
    """Display email matching performance and AI cost."""
    from jobhunter.analytics.email_metrics import get_matcher_metrics

    # Resolve 'since' parameter
    since_dt: datetime
    if "weeks ago" in since or "week ago" in since:
        try:
            weeks = int(since.split()[0])
            since_dt = datetime.now(timezone.utc) - timedelta(weeks=weeks)
        except (ValueError, IndexError):
            typer.echo(f"Error: Invalid 'since' format: {since}", err=True)
            raise typer.Exit(code=1)
    elif "days ago" in since or "day ago" in since:
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

    try:
        with get_session() as session:
            metrics = get_matcher_metrics(session, since_dt.date(), date.today())

        console = Console()
        console.print(
            f"\n[bold blue]Email Matcher Statistics (Since {since_dt.date()})[/bold blue]\n"
        )

        # Overview Table
        overview = Table(title="Global Overview", header_style="bold magenta")
        overview.add_column("Metric")
        overview.add_column("Value", justify="right")

        overview.add_row("Total Emails Processed", str(metrics.total_processed))
        overview.add_row(
            "Overall Match Rate", f"[bold green]{metrics.match_rate * 100:.1f}%[/bold green]"
        )
        precision_color = "green" if metrics.precision >= 0.85 else "red"
        overview.add_row(
            "Precision (User Validated)",
            f"[{precision_color}]{metrics.precision * 100:.1f}%[/{precision_color}]",
        )
        overview.add_row("Accumulated AI Cost", f"${metrics.ai_cost_usd:.4f}")
        console.print(overview)

        # Breakdown Table
        breakdown = Table(title="Match Status Breakdown", header_style="bold cyan")
        breakdown.add_column("Status")
        breakdown.add_column("Count", justify="right")
        breakdown.add_column("Percentage", justify="right")

        total = metrics.total_processed or 1
        breakdown.add_row(
            "Auto Matched",
            str(metrics.auto_matched),
            f"{metrics.auto_matched / total * 100:.1f}%",
        )
        breakdown.add_row(
            "AI Matched",
            str(metrics.ai_matched),
            f"{metrics.ai_matched / total * 100:.1f}%",
        )
        breakdown.add_row(
            "Unmatched",
            str(metrics.unmatched),
            f"{metrics.unmatched / total * 100:.1f}%",
        )
        breakdown.add_row(
            "Ignored (Marketing)",
            str(metrics.ignored_marketing),
            f"{metrics.ignored_marketing / total * 100:.1f}%",
        )
        breakdown.add_row(
            "User Confirmed",
            str(metrics.user_confirmed),
            f"{metrics.user_confirmed / total * 100:.1f}%",
        )
        breakdown.add_row(
            "User Rejected",
            str(metrics.user_rejected),
            f"{metrics.user_rejected / total * 100:.1f}%",
        )
        console.print(breakdown)

        # Top Domains Table
        if metrics.top_domains:
            domains_table = Table(title="Top Domains", header_style="bold yellow")
            domains_table.add_column("Domain")
            domains_table.add_column("Count", justify="right")
            for d in metrics.top_domains:
                domains_table.add_row(d["domain"] or "unknown", str(d["count"]))
            console.print(domains_table)

        if strict and metrics.precision < 0.85:
            typer.echo(f"\n[red]Error: Precision {metrics.precision:.1%} is below target 85%[/red]")
            raise typer.Exit(code=1)

    except Exception as e:
        if isinstance(e, typer.Exit):
            raise
        logger.error("Email stats failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@email_app.command("poll-and-suggest")
def email_poll_and_suggest() -> None:
    """Poll Gmail for new messages, match them, and suggest state changes."""
    from jobhunter.email.orchestrator import run_email_poll_and_suggest

    logger.info("Starting email poll and suggest")
    try:
        with get_session() as session:
            report = asyncio.run(run_email_poll_and_suggest(session))

        console = Console()
        table = Table(title="Email Poll and Suggest Report", header_style="bold magenta")
        table.add_column("Metric")
        table.add_column("Value", justify="right")

        table.add_row("Processed Accounts", str(report["processed_accounts"]))
        table.add_row("New Emails Recorded", str(report["new_emails"]))
        table.add_row("Suggestions Generated", str(report["suggestions"]))
        table.add_row("Callbacks Processed", str(report.get("callbacks_processed", 0)))

        console.print(table)
        session.commit()
    except Exception as e:
        logger.exception("Email poll and suggest failed")
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@app.command()
def dashboard() -> None:
    """Run the Streamlit dashboard."""
    logger.info("Starting dashboard")
    try:
        app_path = Path(__file__).parent / "dashboard" / "streamlit_app.py"
        if not app_path.exists():
            typer.echo(f"Error: Dashboard entry point not found at {app_path}", err=True)
            raise typer.Exit(code=1)

        cmd = ["streamlit", "run", str(app_path)]

        # We use subprocess.run and let it handle the execution
        # In a real environment, this would block until the dashboard is stopped.
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        logger.error("Dashboard failed to run", error=str(e))
        raise typer.Exit(code=1)
    except Exception as e:
        logger.error("Failed to start dashboard", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@api_app.command("run")
def api_run(
    host: Annotated[str, typer.Option(help="Host to bind")] = "0.0.0.0",  # nosec B104
    port: Annotated[int, typer.Option(help="Port to bind")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable auto-reload")] = False,
) -> None:
    """Run the FastAPI health sidecar."""
    import uvicorn

    logger.info("Starting API sidecar", host=host, port=port, reload=reload)
    try:
        uvicorn.run("jobhunter.api.main:app", host=host, port=port, reload=reload)
    except Exception as e:
        logger.error("API sidecar failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@backup_app.command("create")
def backup_create(
    output: Annotated[Optional[Path], typer.Option(help="Local path to save the backup")] = None,
    upload: Annotated[bool, typer.Option(help="Upload to configured storage")] = False,
    cleanup: Annotated[bool, typer.Option(help="Run automated cleanup of old backups")] = False,
) -> None:
    """Create a compressed backup of the database."""
    from jobhunter.db.backup import create_compressed_backup, BackupStorage, run_backup_cleanup

    settings = Settings()  # type: ignore[call-arg]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.sql.gz"

    local_path = output if output else Path(filename)

    try:
        create_compressed_backup(settings.DATABASE_URL, local_path)
        typer.echo(f"Successfully created backup: {local_path}")

        if upload:
            storage = BackupStorage(settings)
            remote_url = storage.upload(local_path)
            typer.echo(f"Successfully uploaded backup to: {remote_url}")

            # If it wasn't a custom output path, we can delete the local temp file after upload
            if not output:
                local_path.unlink()
                typer.echo("Cleaned up local temporary backup file.")

        if cleanup:
            storage = BackupStorage(settings)
            deleted = run_backup_cleanup(storage, settings.BACKUP_RETENTION_WEEKS)
            typer.echo(f"Cleanup: deleted {deleted} old backups.")

    except Exception as e:
        logger.error("Backup creation failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@backup_app.command("list")
def backup_list(
    json_output: Annotated[bool, typer.Option("--json", help="Output in JSON format")] = False,
) -> None:
    """List available backups in the configured storage."""
    from jobhunter.db.backup import BackupStorage
    import json

    settings = Settings()  # type: ignore[call-arg]
    try:
        storage = BackupStorage(settings)
        backups = storage.list_backups()

        if json_output:
            # Format dates for JSON
            json_backups = []
            for b in backups:
                b_copy = b.copy()
                b_copy["created_at"] = b["created_at"].isoformat()
                json_backups.append(b_copy)
            typer.echo(json.dumps(json_backups))
            return

        if not backups:
            typer.echo("No backups found.")
            return

        console = Console()
        table = Table(title=f"Backups ({settings.BACKUP_STORAGE_PROVIDER})")
        table.add_column("Backup ID")
        table.add_column("Size (MB)", justify="right")
        table.add_column("Created At")

        for b in backups:
            size_mb = b["size"] / (1024 * 1024)
            table.add_row(
                b["id"], f"{size_mb:.2f}", b["created_at"].strftime("%Y-%m-%d %H:%M:%S %Z")
            )

        console.print(table)
    except Exception as e:
        logger.error("Failed to list backups", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


@backup_app.command("restore")
def backup_restore(
    backup_id: Annotated[str, typer.Argument(help="ID of the backup to restore")],
    force: Annotated[bool, typer.Option(help="Skip interactive confirmation")] = False,
    expected_version: Annotated[
        Optional[str], typer.Option(help="Expected migration version for integrity check")
    ] = None,
) -> None:
    """Restore the database from a backup (DESTRUCTIVE)."""
    from jobhunter.db.backup import (
        restore_from_compressed_backup,
        BackupStorage,
        validate_db_integrity,
    )

    if not force:
        confirm = typer.confirm(
            f"WARNING: This will OVERWRITE your current database with backup '{backup_id}'. "
            "This operation is destructive and cannot be undone. Are you sure?",
            default=False,
        )
        if not confirm:
            typer.echo("Restore cancelled.")
            return

    settings = Settings()  # type: ignore[call-arg]
    temp_dir = Path(".temp_restore")
    temp_dir.mkdir(exist_ok=True)

    try:
        storage = BackupStorage(settings)
        typer.echo(f"Downloading backup {backup_id}...")
        local_path = storage.download(backup_id, temp_dir)

        typer.echo("Starting restore process...")
        restore_from_compressed_backup(local_path, settings.DATABASE_URL)
        typer.echo("Successfully restored database.")

        # Validate integrity
        with get_session() as session:
            results = validate_db_integrity(session, expected_migration_version=expected_version)
            all_passed = all(results.values())

            console = Console()
            table = Table(title="Post-Restore Integrity Check")
            table.add_column("Check")
            table.add_column("Status")

            for check, passed in results.items():
                status = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                table.add_row(check, status)

            console.print(table)

            if not all_passed:
                typer.echo("Warning: Integrity check failed for some tables!", err=True)
                raise typer.Exit(code=1)

    except Exception as e:
        logger.error("Restore failed", error=str(e))
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    finally:
        if temp_dir.exists():
            import shutil

            shutil.rmtree(temp_dir)


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
    configure_logging()
    app()


if __name__ == "__main__":
    main()
