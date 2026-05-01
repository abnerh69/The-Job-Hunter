import pytest
import time
import os
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from typing import Generator
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from jobhunter.db.base import Base
from jobhunter.db.models import Job, Application, ApplicationEvent
from jobhunter.db.enums import JobStatus, JobTier, ApplicationStatus, ApplicationEventType


@pytest.fixture(scope="module")
def test_db() -> Generator[str, None, None]:
    db_path = "test_e2e_pipeline.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create a job and an application
    job_id = uuid.uuid4()
    job = Job(
        id=job_id,
        source="LinkedIn",
        url="https://example.com/job1",
        url_hash="hash_job1",
        title="Software Engineer",
        company="Tech Corp",
        description="Great role",
        status=JobStatus.APPLIED,
        tier=JobTier.A,
        fit_score=95,
        scraped_at=datetime.now(timezone.utc),
    )
    session.add(job)

    app_id = uuid.uuid4()
    app = Application(
        id=app_id,
        job_id=job_id,
        applied_at=datetime.now(timezone.utc) - timedelta(days=2),
        application_method="LinkedIn",
        status=ApplicationStatus.APPLIED,
        next_action="Follow up",
        next_action_due=datetime.now(timezone.utc).date() + timedelta(days=3),
        notes="Initial notes",
    )
    session.add(app)

    # Add an event
    event = ApplicationEvent(
        application_id=app_id,
        event_type=ApplicationEventType.STATUS_CHANGE,
        event_data={"old_status": "NONE", "new_status": "applied", "note": "Initial application"},
        occurred_at=datetime.now(timezone.utc) - timedelta(days=2),
    )
    session.add(event)

    session.commit()
    session.close()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server(test_db: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8501) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    env["PYTHONPATH"] = "src"
    cmd = [
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8501",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)
    time.sleep(10)
    yield
    process.terminate()
    process.wait()


@pytest.mark.e2e
def test_pipeline_kanban_flow(streamlit_server: None) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.keyboard.press("Enter")
        time.sleep(5)

        # Navigate to Pipeline
        page.get_by_role("link", name="Pipeline").click()
        time.sleep(5)

        # 1. Verify Kanban column and card
        expect(page.get_by_text("APPLIED")).to_be_visible()
        # Use first() to avoid strict mode violation if company name appears in metrics too
        expect(page.get_by_text("Tech Corp").first).to_be_visible()
        expect(page.get_by_text("Software Engineer").first).to_be_visible()

        # 2. Open Detail Modal
        page.get_by_role("button", name="👁️ Detalle").click()
        time.sleep(3)
        expect(page.get_by_text("Detalle de Aplicación")).to_be_visible()
        expect(page.get_by_text("Status Actual: applied")).to_be_visible()

        # 3. Test Transition in Modal
        # Move to Screening
        page.get_by_role("button", name="Mover a screening").click()
        time.sleep(5)

        # Verify status in modal updated
        expect(page.get_by_text("Status Actual: screening")).to_be_visible()

        # Close modal to see Kanban
        page.get_by_role("button", name="Cerrar", exact=True).click()
        time.sleep(2)

        # 4. Test Quick Move Button (➡️)
        # From screening to interview_1
        page.get_by_role("button", name="➡️").click()
        time.sleep(5)

        # Verify new status
        page.get_by_role("button", name="👁️ Detalle").click()
        time.sleep(3)
        expect(page.get_by_text("Status Actual: interview_1")).to_be_visible()

        browser.close()
