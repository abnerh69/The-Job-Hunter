import uuid
from datetime import date, timedelta

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from jobhunter.analytics import pipeline_metrics, quality_metrics
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
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    start_date = week_ending - timedelta(days=6)

    # Use analytics package
    tier_dist = quality_metrics.get_tier_distribution(session, start_date, week_ending)
    new_jobs_by_tier = {item.tier: item.count for item in tier_dist.distribution}

    funnel = pipeline_metrics.get_funnel_metrics(session, start_date, week_ending)
    apps_sent_this_week = 0
    for stage in funnel.stages:
        if stage.stage == "4. Applied":
            apps_sent_this_week = stage.count
            break

    # Pending follow-ups
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

    # Tier A jobs in QUEUED status
    queued_tier_a_stmt = (
        select(Job)
        .where(Job.tier == JobTier.A, Job.status == JobStatus.QUEUED)
        .order_by(Job.fit_score.desc())
        .limit(5)
    )
    queued_tier_a = session.scalars(queued_tier_a_stmt).all()

    from sqlalchemy import func

    queued_tier_a_count = (
        session.scalar(
            select(func.count(Job.id)).where(Job.tier == JobTier.A, Job.status == JobStatus.QUEUED)
        )
        or 0
    )

    manual_review_tier_c_count = (
        session.scalar(
            select(func.count(Job.id)).where(
                Job.tier == JobTier.C, Job.status == JobStatus.MANUAL_REVIEW
            )
        )
        or 0
    )

    # Trends and response rate using analytics
    weekly_trends = pipeline_metrics.get_weekly_trends(session, weeks=4)
    monthly_trends = [
        MonthlyMetric(
            week_start=trend.week,
            apps_sent=trend.apps_sent,
            interviews=trend.interviews,
            conversion_rate=trend.response_rate,
        )
        for trend in reversed(weekly_trends)
    ]

    response_rate = 0.0
    if weekly_trends:
        total_apps = sum(t.apps_sent for t in weekly_trends)
        total_resp = sum(t.apps_with_response for t in weekly_trends)
        if total_apps > 0:
            response_rate = (total_resp / total_apps) * 100

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


def prepare_weekly_digest(
    session: Session, week_ending: date | None = None
) -> tuple[NotificationMessage, str]:
    """
    Computes metrics and renders templates for the weekly digest.

    Args:
        session: SQLAlchemy session.
        week_ending: The end date of the week. Defaults to today.

    Returns:
        tuple[NotificationMessage, str]: The rendered notification message and its dedup key.
    """
    if week_ending is None:
        week_ending = date.today()

    iso_year, iso_week, _ = week_ending.isocalendar()
    dedup_key = f"digest:{iso_year}:{iso_week}"

    # Compute context
    context = compute_digest_context(session, week_ending)
    context_dict = context.model_dump()

    # Render templates
    body_html = render("notifications/weekly_digest_email.html", context_dict)
    body_text = render("notifications/weekly_digest_email.txt", context_dict)

    message = NotificationMessage(
        channel="email",
        subject=f"Weekly Job Hunt Summary - {week_ending.strftime('%b %d, %Y')}",
        body_text=body_text,
        body_html=body_html,
    )

    return message, dedup_key


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
    message, dedup_key = prepare_weekly_digest(session, week_ending)
    channel = "email"

    repo = NotificationsRepo(session)
    if repo.was_sent(channel, dedup_key):
        return None

    notifier = EmailNotifier()
    result = await notifier.send(message)

    # Record attempt
    repo.record_sent(channel, dedup_key, None, result)
    session.commit()

    return result
