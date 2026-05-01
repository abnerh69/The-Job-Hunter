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
from jobhunter.db.models import Job
from jobhunter.db.enums import JobStatus, JobTier


@pytest.fixture(scope="module")
def test_db() -> Generator[str, None, None]:
    db_path = "test_e2e_assist_flow.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create a Tier-A job
    job = Job(
        id=uuid.uuid4(),
        source="LinkedIn",
        url="https://example.com/assist-me",
        url_hash="hash-assist",
        title="Python AI Engineer",
        company="Assist Corp",
        description="We need a Python AI Engineer. Skills: Python, PyTorch.",
        status=JobStatus.QUEUED,
        tier=JobTier.A,
        fit_score=95,
        score_data={
            "role": {"is_ai_ml_role": True, "primary_stack_match": ["Python", "PyTorch"]},
            "compensation": {"salary_max_usd_month": 12000},
            "match_analysis": {"key_match_points": ["Deep learning", "Python expertise"]},
        },
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)
    session.commit()
    session.close()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server(test_db: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8502) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    env["PYTHONPATH"] = "src"
    # Set CV variants dir to use the ones in the repo
    env["CV_VARIANTS_DIR"] = "cv_variants"

    cmd = [
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8502",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)
    time.sleep(10)
    yield
    process.terminate()
    process.wait()


@pytest.mark.e2e
def test_assist_and_apply_flow(streamlit_server: None) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8502")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.keyboard.press("Enter")
        time.sleep(5)

        # Navigate to New Matches
        page.get_by_role("link", name="New Matches").click()
        time.sleep(5)

        # Verify job is visible
        expect(page.get_by_text("Python AI Engineer")).to_be_visible()

        # Click Assist button
        # Use force=True if needed, but first try to wait for it
        assist_button = page.get_by_role("button", name="🚀 Assist")
        expect(assist_button).to_be_visible()
        assist_button.click()

        # Wait for navigation and page load
        time.sleep(10)

        # Debug: Print page title and take screenshot
        print(f"Current page title: {page.title()}")
        page.screenshot(path="debug_assist_page.png")

        # Verify we are on Assist page - use a more robust selector
        expect(
            page.get_by_role("heading", name="Asistencia para Python AI Engineer")
        ).to_be_visible()

        # Click "Generar Asistencia Completa"
        page.get_by_role("button", name="🚀 Generar Asistencia Completa").click()

        # This will take some time because of the mock LLM calls.
        # In the test environment, MockLLMClient is used via conftest.py if registered,
        # but here we are running a separate process.
        # The streamlit_server fixture should have access to the same codebase.
        # Since we set ANTHROPIC_API_KEY=dummy, if the code tries to call Anthropic it might fail
        # unless MockLLMClient is active in the subprocess.

        # Wait for completion (up to 30s)
        time.sleep(15)

        # Check if assistance is rendered
        expect(page.get_by_text("Asistencia generada con éxito")).to_be_visible()
        expect(page.get_by_role("tab", name="✉️ Cover Letter")).to_be_visible()

        # Edit cover letter
        cl_textarea = page.get_by_label("Edita tu cover letter antes de aplicar")
        cl_textarea.fill("This is my edited cover letter from E2E test.")

        # Save edits
        page.get_by_role("button", name="💾 Save edits").click()
        time.sleep(2)
        expect(page.get_by_text("Cambios guardados en la base de datos")).to_be_visible()

        # Mark as applied
        page.get_by_role("button", name="✅ Mark Applied & Register").click()
        time.sleep(10)

        # Debug screenshot after click apply
        page.screenshot(path="debug_after_apply.png")

        # Should be redirected to Pipeline - check for header
        expect(page.get_by_role("heading", name="📋 Application Pipeline")).to_be_visible()
        expect(page.get_by_text("Assist Corp")).to_be_visible()

        browser.close()
