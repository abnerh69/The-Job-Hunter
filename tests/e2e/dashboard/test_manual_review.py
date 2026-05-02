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
from jobhunter.db.models import Job
from jobhunter.db.enums import JobStatus, JobTier


@pytest.fixture(scope="module")
def test_db_mr() -> Generator[str, None, None]:
    db_path = "test_e2e_manual_review.db"
    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    now = datetime.now(timezone.utc)
    # Create some jobs in manual_review
    for i in range(3):
        # i=0 -> 0 days ago, i=1 -> 4 days ago, i=2 -> 8 days ago
        scored_at = now - timedelta(days=i * 4)
        job = Job(
            id=uuid.uuid4(),
            source="LinkedIn",
            url=f"https://example.com/mr/{i}",
            url_hash=f"mr_hash{i}",
            title=f"Manual Review Job {i}",
            company="MR Corp",
            description="Ambiguous job description",
            status=JobStatus.MANUAL_REVIEW,
            tier=JobTier.C,
            fit_score=60 + i,
            score_data={
                "recommendation": {"reason_short": f"Test reason {i}"},
                "yellow_flags": ["Flag 1"],
                "company": {"stage": "growth", "domain_inferred": "Tech"},
                "role": {
                    "title_normalized": "Dev",
                    "seniority_inferred": "mid",
                    "stack_overlap_pct": 50,
                },
                "logistics": {"remote_type": "hybrid", "timezone_requirement": "any"},
                "compensation": {"salary_min_usd_month": 3000, "salary_max_usd_month": 4000},
                "match_analysis": {"key_match_points": ["Point"], "key_gaps": ["Gap"]},
            },
            scored_at=scored_at,
            scraped_at=now,
        )
        session.add(job)
    session.commit()
    session.close()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server_mr(test_db_mr: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8501) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db_mr
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
def test_manual_review_flow(streamlit_server_mr: None) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        page.goto("http://localhost:8501")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.keyboard.press("Enter")
        time.sleep(5)

        page.get_by_role("link", name="Manual Review").click()
        time.sleep(5)

        # 1. Verify metrics
        expect(page.get_by_text("Jobs esperando review")).to_be_visible()
        # expect(page.get_by_text("3")).to_be_visible()
        expect(page.get_by_text("Antiguos (> 7 días)")).to_be_visible()
        # expect(page.get_by_text("1")).to_be_visible()

        # 2. Verify cards render
        # Job 2 is oldest (8d ago), Job 1 (4d ago), Job 0 (0d ago)
        # Default order is scored_at ASC, so Job 2 should be first
        expect(page.get_by_text("Manual Review Job 2")).to_be_visible()
        expect(page.get_by_text("Test reason 2")).to_be_visible()

        # 3. Test Promote to Queue
        page.get_by_role("button", name="🚀 Promote").first.click()
        time.sleep(5)

        # Verify it disappeared
        expect(page.get_by_text("Manual Review Job 2")).not_to_be_visible()

        # Job 1 should now be first
        expect(page.get_by_text("Manual Review Job 1")).to_be_visible()

        browser.close()
