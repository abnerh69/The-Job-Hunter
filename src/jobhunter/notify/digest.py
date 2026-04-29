import uuid
from datetime import date, datetime, time, timedelta, timezone


from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, joinedload

from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier
from jobhunter.db.models import Application, Job
from jobhunter.db.repos.notifications import NotificationsRepo
from jobhunter.notify.base import NotificationMessage, NotificationResult
from jobhunter.notify.email import EmailNotifier
from jobhunter.notify.templates import render


class JobSummary(BaseModel):
    """
    Minimal job information for digest display.
    """

    id: uuid.UUID
    title: str
    company: str
    fit_score: int | None = None
    url: str


class ApplicationSummary(BaseModel):
    """
    Minimal application information for digest display.
    """

    job_company: str
    next_action: str | None = None
    next_action_due: date | None = None


class DigestMetrics(BaseModel):
    """
    Aggregated metrics for the weekly digest.
    """

    new_jobs_total: int = 0
    new_jobs_tier_a: int = 0
    new_jobs_tier_b: int = 0
    new_jobs_tier_c: int = 0
    apps_sent_this_week: int = 0
    response_rate_last_4_weeks: float = 0.0
    pending_followups_count: int = 0
    queued_tier_a_count: int = 0
    manual_review_tier_c_count: int = 0


class MonthlyMetric(BaseModel):
    """
    Metric for a specific week, used for monthly trends.
    """

    week_start: date
    apps_sent: int
    interviews: int
    conversion_rate: float


class WeeklyDigestContext(BaseModel):
    """
    Context data for rendering the weekly digest templates.
    """

    end_date: date
    metrics: DigestMetrics
    top_tier_a_queued: list[JobSummary] = Field(default_factory=list)
    followups_due: list[ApplicationSummary] = Field(default_factory=list)
    monthly_trends: list[MonthlyMetric] = Field(default_factory=list)
    is_empty_pipeline: bool = False


def compute_digest_context(session: Session, week_ending: date) -> WeeklyDigestContext:
    """
    Computes all metrics and data required for the weekly digest.

    Args:
        session: SQLAlchemy session.
        week_ending: The last day of the week to include in the digest.

    Returns:
        WeeklyDigestContext: Aggregated data for the digest.
    """
    start_date = week_ending - timedelta(days=6)
    start_dt = datetime.combine(start_date, time.min).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(week_ending, time.max).replace(tzinfo=timezone.utc)

    # 1. New jobs ingested this week
    new_jobs_stmt = (
        select(Job.tier, func.count(Job.id))
        .where(Job.scraped_at >= start_dt, Job.scraped_at <= end_dt)
        .group_by(Job.tier)
    )
    new_jobs_by_tier = dict(session.execute(new_jobs_stmt).all())

    # 2. Applications sent this week
    apps_sent_stmt = select(func.count(Application.id)).where(
        Application.applied_at >= start_dt, Application.applied_at <= end_dt
    )
    apps_sent_this_week = session.scalar(apps_sent_stmt) or 0

    # 3. Pending follow-ups (overdue based on next_action_due)
    terminal_statuses = [
        ApplicationStatus.REJECTED,
        ApplicationStatus.GHOSTED,
        ApplicationStatus.WITHDRAWN,
        ApplicationStatus.OFFER,
    ]
    followups_stmt = (
        select(Application)
        .options(joinedload(Application.job))
        .where(
            Application.next_action_due <= date.today(),
            ~Application.status.in_(terminal_statuses),
            Application.next_action_due.is_not(None),
        )
        .order_by(Application.next_action_due.asc())
    )
    followups = session.scalars(followups_stmt).all()

    # 4. Tier A jobs in QUEUED status (top 5 by fit_score)
    queued_tier_a_stmt = (
        select(Job)
        .where(Job.tier == JobTier.A, Job.status == JobStatus.QUEUED)
        .order_by(Job.fit_score.desc())
        .limit(5)
    )
    queued_tier_a = session.scalars(queued_tier_a_stmt).all()

    queued_tier_a_total_stmt = select(func.count(Job.id)).where(
        Job.tier == JobTier.A, Job.status == JobStatus.QUEUED
    )
    queued_tier_a_count = session.scalar(queued_tier_a_total_stmt) or 0

    # 5. Tier C jobs in MANUAL_REVIEW
    manual_review_tier_c_stmt = select(func.count(Job.id)).where(
        Job.tier == JobTier.C, Job.status == JobStatus.MANUAL_REVIEW
    )
    manual_review_tier_c_count = session.scalar(manual_review_tier_c_stmt) or 0

    # 6. Response rate and monthly trends
    response_rate = 0.0
    monthly_trends: list[MonthlyMetric] = []

    if session.bind.dialect.name == "postgresql":
        try:
            # Monthly trends from weekly_metrics view
            trends_stmt = text("""
                SELECT week, apps_sent, interviews
                FROM weekly_metrics
                ORDER BY week DESC
                LIMIT 4
            """)
            trends_rows = session.execute(trends_stmt).fetchall()

            for row in reversed(trends_rows):
                conv_rate = (row.interviews / row.apps_sent * 100) if row.apps_sent > 0 else 0.0
                monthly_trends.append(
                    MonthlyMetric(
                        week_start=row.week,
                        apps_sent=row.apps_sent,
                        interviews=row.interviews,
                        conversion_rate=conv_rate,
                    )
                )

            # Aggregate response rate for last 4 weeks from view
            resp_stmt = text("""
                SELECT
                    SUM(apps_sent) as total_apps,
                    SUM(apps_with_response) as total_responses
                FROM (
                    SELECT apps_sent, apps_with_response
                    FROM weekly_metrics
                    ORDER BY week DESC
                    LIMIT 4
                ) last_4
            """)
            resp_row = session.execute(resp_stmt).fetchone()
            if resp_row and resp_row.total_apps and resp_row.total_apps > 0:
                response_rate = (resp_row.total_responses / resp_row.total_apps) * 100
        except Exception:
            # Fallback if view doesn't exist or other error
            pass

    # If no trends found (e.g. SQLite or empty DB), attempt basic fallback for last 4 weeks
    if not monthly_trends:
        # Simple aggregation for the last 28 days
        four_weeks_ago = week_ending - timedelta(days=27)
        four_weeks_ago_dt = datetime.combine(four_weeks_ago, time.min).replace(tzinfo=timezone.utc)

        total_apps_4w_stmt = select(func.count(Application.id)).where(
            Application.applied_at >= four_weeks_ago_dt, Application.applied_at <= end_dt
        )
        total_apps_4w = session.scalar(total_apps_4w_stmt) or 0

        if total_apps_4w > 0:
            responded_apps_4w_stmt = select(func.count(Application.id)).where(
                Application.applied_at >= four_weeks_ago_dt,
                Application.applied_at <= end_dt,
                ~Application.status.in_([ApplicationStatus.APPLIED, ApplicationStatus.WITHDRAWN]),
            )
            responded_apps_4w = session.scalar(responded_apps_4w_stmt) or 0
            response_rate = (responded_apps_4w / total_apps_4w) * 100

    metrics = DigestMetrics(
        new_jobs_total=sum(new_jobs_by_tier.values()),
        new_jobs_tier_a=new_jobs_by_tier.get(JobTier.A, 0),
        new_jobs_tier_b=new_jobs_by_tier.get(JobTier.B, 0),
        new_jobs_tier_c=new_jobs_by_tier.get(JobTier.C, 0),
        apps_sent_this_week=apps_sent_this_week,
        response_rate_last_4_weeks=response_rate,
        pending_followups_count=len(followups),
        queued_tier_a_count=queued_tier_a_count,
        manual_review_tier_c_count=manual_review_tier_c_count,
    )

    return WeeklyDigestContext(
        end_date=week_ending,
        metrics=metrics,
        top_tier_a_queued=[
            JobSummary(
                id=j.id,
                title=j.title,
                company=j.company,
                fit_score=j.fit_score,
                url=j.url,
            )
            for j in queued_tier_a
        ],
        followups_due=[
            ApplicationSummary(
                job_company=a.job.company,
                next_action=a.next_action,
                next_action_due=a.next_action_due,
            )
            for a in followups
        ],
        monthly_trends=monthly_trends,
        is_empty_pipeline=(metrics.new_jobs_total == 0 and metrics.apps_sent_this_week == 0),
    )


async def send_weekly_digest(
    session: Session, week_ending: date | None = None
) -> NotificationResult | None:
    """
    Sends the weekly digest email if not already sent for this week.

    Args:
        session: SQLAlchemy session.
        week_ending: The end date of the week. Defaults to today.

    Returns:
        NotificationResult | None: The result of the notification attempt,
                                   or None if it was already sent.
    """
    if week_ending is None:
        week_ending = date.today()

    iso_year, iso_week, _ = week_ending.isocalendar()
    dedup_key = f"digest:{iso_year}:{iso_week}"
    channel = "email"

    repo = NotificationsRepo(session)
    if repo.was_sent(channel, dedup_key):
        return None

    # Compute context
    context = compute_digest_context(session, week_ending)
    context_dict = context.model_dump()

    # Render templates
    body_html = render("notifications/weekly_digest_email.html", context_dict)
    body_text = render("notifications/weekly_digest_email.txt", context_dict)

    message = NotificationMessage(
        channel=channel,
        subject=f"Weekly Job Hunt Summary - {week_ending.strftime('%b %d, %Y')}",
        body_text=body_text,
        body_html=body_html,
    )

    notifier = EmailNotifier()
    result = await notifier.send(message)

    # Record attempt
    repo.record_sent(channel, dedup_key, None, result)
    session.commit()

    return result
