import pytest
import time
import os
import subprocess
from typing import Generator
from playwright.sync_api import sync_playwright, expect
from jobhunter.db.session import get_session
from jobhunter.db.models import Job
from jobhunter.db.enums import JobTier, JobStatus


@pytest.fixture(scope="module", autouse=True)
def streamlit_server() -> Generator[None, None, None]:
    # Kill any existing streamlit server on 8501
    subprocess.run("kill $(lsof -t -i :8501) 2>/dev/null || true", shell=True)

    # Setup environment
    env = os.environ.copy()
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"
    env["PYTHONPATH"] = "src"

    # Run streamlit
    cmd = [
        "uv",
        "run",
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)

    # Wait for server to start
    time.sleep(10)

    yield

    # Kill server
    process.terminate()
    process.wait()


@pytest.fixture(scope="function")
def seed_data() -> None:
    with get_session() as session:
        # Clear jobs
        session.query(Job).delete()

        # Add a few jobs
        for i in range(5):
            job = Job(
                title=f"Tier A Job {i}",
                company="Company A",
                source="Linkedin",
                url=f"http://test.com/a{i}",
                url_hash=f"hash_a{i}",
                description="desc",
                tier=JobTier.A,
                status=JobStatus.QUEUED,
                fit_score=90 + i,
            )
            session.add(job)

        for i in range(5):
            job = Job(
                title=f"Tier B Job {i}",
                company="Company B",
                source="WWR",
                url=f"http://test.com/b{i}",
                url_hash=f"hash_b{i}",
                description="desc",
                tier=JobTier.B,
                status=JobStatus.QUEUED,
                fit_score=70 + i,
            )
            session.add(job)

        session.commit()


def test_new_matches_filters_and_skip(seed_data: Any) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(3)

        # Go to New Matches
        page.get_by_text("New Matches").click()
        time.sleep(3)

        # Check total jobs (should be 10 by default since A and B are selected)
        # Note: streamlit multiselect default in my code was [A, B]
        expect(page.get_by_text("Total: 10 jobs")).to_be_visible()

        # Filter by Tier A only
        # We need to interact with the multiselect
        # This is tricky in Streamlit. Let's try to find the "B" tag and remove it.
        page.get_by_label("Tier").get_by_text("B").get_by_label("Remove").click()
        time.sleep(2)
        expect(page.get_by_text("Total: 5 jobs")).to_be_visible()

        # Check for card
        expect(page.get_by_text("Tier A Job 4")).to_be_visible()

        # Skip a job
        # Find the card for "Tier A Job 4" and click Skip
        card = page.get_by_text("Tier A Job 4").locator("xpath=../..")
        card.get_by_role("button", name="🗑️ Skip").click()
        time.sleep(1)

        # Confirm skip
        page.get_by_role("button", name="Confirm Skip").click()
        time.sleep(2)

        # Should have 4 jobs now
        expect(page.get_by_text("Total: 4 jobs")).to_be_visible()
        expect(page.get_by_text("Tier A Job 4")).not_to_be_visible()

        browser.close()


def test_new_matches_mark_applied(seed_data: Any) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.get_by_role("textbox", name="Password").press("Enter")
        time.sleep(3)

        # Go to New Matches
        page.get_by_text("New Matches").click()
        time.sleep(3)

        # Click Applied on first job
        page.get_by_role("button", name="✅ Applied").first.click()
        time.sleep(1)

        # Check modal
        expect(page.get_by_text("Mark as Applied")).to_be_visible()

        # Fill form
        page.get_by_label("Notes").fill("Testing application flow")
        page.get_by_role("button", name="Confirm Application").click()
        time.sleep(3)

        # Job should be gone from the list (since it's now 'applied')
        expect(page.get_by_text("Total: 9 jobs")).to_be_visible()

        browser.close()
