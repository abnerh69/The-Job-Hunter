import pytest
import time
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Generator
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jobhunter.db.base import Base
from jobhunter.db.models import Job, Application, OutreachContact
from jobhunter.db.enums import JobStatus, JobTier, ApplicationStatus, OutreachStatus, OutreachMarket


@pytest.fixture(scope="module")
def test_db() -> Generator[str, None, None]:
    db_path = "test_e2e_search.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create some data to search
    job = Job(
        id=uuid.uuid4(),
        source="LinkedIn",
        url="https://example.com/search-job",
        url_hash="hash-search",
        title="Unique Job Title",
        company="Searchable Corp",
        description="Looking for someone who can search well.",
        status=JobStatus.QUEUED,
        tier=JobTier.A,
        fit_score=95,
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)

    app = Application(
        id=uuid.uuid4(),
        job_id=job.id,
        applied_at=datetime.now(timezone.utc),
        application_method="LinkedIn",
        status=ApplicationStatus.APPLIED,
        notes="Important search note here",
    )
    session.add(app)

    contact = OutreachContact(
        id=uuid.uuid4(),
        name="John Searcher",
        company="Searchable Corp",
        role="Recruiter",
        market=OutreachMarket.GERMANY,
        status=OutreachStatus.NEW,
    )
    session.add(contact)

    session.commit()
    session.close()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server(test_db: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8503) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    env["PYTHONPATH"] = "src"
    cmd = [
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8503",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)
    time.sleep(10)
    yield
    process.terminate()
    process.wait()


@pytest.mark.e2e
def test_global_search_flow(streamlit_server: None) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8503")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.keyboard.press("Enter")
        time.sleep(5)

        # Use sidebar search
        search_input = page.get_by_label("Search across jobs, apps, contacts")
        search_input.fill("Unique")
        page.get_by_role("button", name="Search").click()
        time.sleep(5)

        # Verify results in Jobs tab
        expect(page.get_by_test_id("search-result-job")).to_be_attached()
        expect(page.get_by_text("Unique Job Title")).to_be_visible()

        # Search for something in notes
        search_input.fill("Important")
        page.get_by_role("button", name="Search").click()
        time.sleep(5)

        # Switch to Applications tab
        # Tabs are identified by text usually in Streamlit
        page.get_by_role("tab").filter(has_text="Applications").click()
        time.sleep(2)
        expect(page.get_by_test_id("search-result-app")).to_be_attached()
        expect(page.get_by_text("Important search note here")).to_be_visible()

        # Search for contact
        search_input.fill("John Searcher")
        page.get_by_role("button", name="Search").click()
        time.sleep(5)

        # Switch to Contacts tab
        page.get_by_role("tab").filter(has_text="Contacts").click()
        time.sleep(2)
        expect(page.get_by_test_id("search-result-contact")).to_be_attached()
        # The text might be outside the data-testid div but inside the card container.
        # Let's just check for the text on the page while the tab is active.
        expect(page.get_by_text("John Searcher").first).to_be_visible()

        browser.close()
