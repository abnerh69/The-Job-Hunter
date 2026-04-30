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
    db_path = "test_e2e_new_matches.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Create some jobs
    for i in range(5):
        job = Job(
            id=uuid.uuid4(),
            source="LinkedIn" if i % 2 == 0 else "Indeed",
            url=f"https://example.com/{i}",
            url_hash=f"hash{i}",
            title=f"Python Developer {i}",
            company="Test Corp",
            description="Awesome job",
            status=JobStatus.QUEUED,
            tier=JobTier.A if i < 3 else JobTier.B,
            fit_score=90 + i,
            score_data={
                "role": {"title_normalized": "Python Developer", "primary_stack_match": ["Python"]},
                "compensation": {"salary_max_usd_month": 10000},
                "match_analysis": {"key_match_points": ["Point A", "Point B"]},
                "yellow_flags": ["Test yellow flag"],
            },
            scraped_at=datetime.now(timezone.utc) if "datetime" in globals() else None,
        )
        job.scraped_at = datetime.now(timezone.utc)

        session.add(job)
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
    env["DASHBOARD_PASSWORD"] = "secret123"
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


def test_new_matches_flow(streamlit_server: None) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")
        page.keyboard.press("Enter")
        time.sleep(5)

        page.get_by_role("link", name="New Matches").click()
        time.sleep(5)

        # 1. Verify cards render
        expect(page.get_by_text("Python Developer 4")).to_be_visible()

        # 2. Test Skip (without filtering for now to avoid multiselect issues in CI)
        page.get_by_role("button", name="⏭️ Skip").first.click()
        time.sleep(2)
        expect(page.get_by_text("¿Estás seguro de que deseas archivar")).to_be_visible()
        page.get_by_role("button", name="Sí, archivar").click()
        time.sleep(5)

        # Verify it disappeared (Python Developer 4 was first by fit_score 94)
        expect(page.get_by_text("Python Developer 4")).not_to_be_visible()

        browser.close()
