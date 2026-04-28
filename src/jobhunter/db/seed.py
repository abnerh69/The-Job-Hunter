import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy.orm import Session

from jobhunter.db.enums import ApplicationStatus, JobStatus, JobTier, OutreachMarket, OutreachStatus
from jobhunter.db.models import Application, Job, OutreachContact


def seed_database(session: Session, scenario: Literal["rich", "minimal"] = "rich") -> None:
    """
    Seeds the database with sample data based on the chosen scenario.

    Args:
        session: SQLAlchemy session to use for database operations.
        scenario: The scenario to seed ('rich' or 'minimal').
    """
    fixtures_path = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures"
    jobs_fixture = fixtures_path / "sample_jobs.json"

    if not jobs_fixture.exists():
        raise FileNotFoundError(f"Jobs fixture not found at {jobs_fixture}")

    with open(jobs_fixture) as f:
        all_jobs_data = json.load(f)

    if scenario == "minimal":
        num_jobs = 5
        num_apps = 2
        num_contacts = 3
    else:
        num_jobs = 50
        num_apps = 15
        num_contacts = 20

    # 1. Seed Jobs
    jobs_data = all_jobs_data[:num_jobs]
    jobs = []
    for data in jobs_data:
        # Convert ISO strings to datetime objects
        posted_at = datetime.fromisoformat(data["posted_at"]) if data.get("posted_at") else None
        scraped_at = (
            datetime.fromisoformat(data["scraped_at"])
            if data.get("scraped_at")
            else datetime.now(timezone.utc)
        )

        job = Job(
            source=data["source"],
            url=data["url"],
            url_hash=data["url_hash"],
            title=data["title"],
            company=data["company"],
            location_raw=data.get("location_raw"),
            description=data["description"],
            posted_at=posted_at,
            scraped_at=scraped_at,
            tier=JobTier(data["tier"]) if data.get("tier") else None,
            status=JobStatus(data["status"]) if data.get("status") else JobStatus.NEW,
            fit_score=data.get("fit_score"),
        )
        session.add(job)
        jobs.append(job)

    session.flush()  # To get job IDs

    # 2. Seed Applications
    # We want a variety of statuses
    app_statuses = list(ApplicationStatus)
    # Pick a subset of jobs to apply for
    applied_jobs = random.sample(jobs, min(num_apps, len(jobs)))

    for i, job in enumerate(applied_jobs):
        # Ensure at least one of each major status if scenario is rich
        if scenario == "rich" and i < len(app_statuses):
            status = app_statuses[i]
        else:
            status = random.choice(app_statuses)

        applied_at = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 30))

        # Some realistic data for applications
        salary_max = None
        if status == ApplicationStatus.OFFER:
            salary_max = random.randint(60000, 120000)

        app = Application(
            job_id=job.id,
            status=status,
            applied_at=applied_at,
            application_method=random.choice(["LinkedIn", "Company Website", "Referral"]),
            cv_variant=random.choice(["Generic", "Backend", "Tech Lead"]),
            salary_offered_max=salary_max,
            salary_currency="EUR" if salary_max else None,
            next_action_due=date.today() + timedelta(days=random.randint(1, 7))
            if status
            not in [ApplicationStatus.REJECTED, ApplicationStatus.GHOSTED, ApplicationStatus.OFFER]
            else None,
        )
        session.add(app)
        # Update job status to match application if it was 'new'
        if job.status == JobStatus.NEW:
            job.status = JobStatus.APPLIED

    # 3. Seed Outreach Contacts
    names = [
        "John Doe",
        "Jane Smith",
        "Alice Johnson",
        "Bob Brown",
        "Charlie Davis",
        "Diana Prince",
        "Edward Norton",
        "Fiona Apple",
        "George Clooney",
        "Hannah Abbott",
        "Ian McKellen",
        "Julia Roberts",
        "Kevin Hart",
        "Laura Dern",
        "Michael Jordan",
        "Natalie Portman",
        "Oscar Isaac",
        "Penelope Cruz",
        "Quentin Tarantino",
        "Ryan Gosling",
    ]

    markets = list(OutreachMarket)
    outreach_statuses = list(OutreachStatus)
    stacks = ["Python", "Java", "Go", "React", "Node.js", "C++", "Rust", "AWS", "Azure", "GCP"]

    for i in range(num_contacts):
        name = names[i % len(names)]
        if i >= len(names):
            name += f" {i}"

        outreach_status = random.choice(outreach_statuses)
        last_contacted = None
        contact_count = 0
        if outreach_status != OutreachStatus.NEW:
            last_contacted = datetime.now(timezone.utc) - timedelta(days=random.randint(1, 20))
            contact_count = random.randint(1, 3)

        contact = OutreachContact(
            name=name,
            company=random.choice(
                ["Tech Recruiter Ltd", "Global Talent", "Startup Founders", "BigCorp HR"]
            ),
            role=random.choice(["Technical Recruiter", "HR Manager", "Engineering Manager", "CTO"]),
            linkedin_url=f"https://www.linkedin.com/in/sample-profile-{i}",
            market=random.choice(markets),
            specialty_stack=random.choice(stacks),
            quality_score=random.randint(1, 5),
            status=outreach_status,
            last_contacted_at=last_contacted,
            contact_count=contact_count,
            first_contacted_at=last_contacted - timedelta(days=5) if last_contacted else None,
        )
        session.add(contact)

    session.commit()
