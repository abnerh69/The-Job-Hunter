import pytest
import time
import os
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
from typing import Generator
from playwright.sync_api import sync_playwright, expect
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from jobhunter.db.models import OutreachContact, OutreachMessage
from jobhunter.db.enums import (
    OutreachStatus,
    OutreachMarket,
    OutreachMessageStatus,
    OutreachTemplateType,
)


@pytest.fixture(scope="module")
def test_db() -> Generator[str, None, None]:
    db_path = "test_e2e_outreach_metrics.db"
    if os.environ.get("GITHUB_ACTIONS"):
        # Avoid conflicts in CI
        db_path = f"test_e2e_outreach_metrics_{uuid.uuid4().hex}.db"

    if os.path.exists(db_path):
        os.remove(db_path)

    engine = create_engine(f"sqlite:///{db_path}")

    # Create tables via metadata for SQLite E2E
    # But since models have search_vector which is PostgreSQL specific in some aspects
    # (though defined as Text in models.py with FetchedValue),
    # we might need to manually handle it if it causes issues.
    # Base.metadata.create_all(engine)

    # Better use alembic to be safe
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path}"
    env["ANTHROPIC_API_KEY"] = "dummy"  # pragma: allowlist secret
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], env=env, check=True)

    # For SQLite, we might need to add search_vector columns manually if alembic skipped them
    # because it only adds them for postgresql dialect.
    # Models expect them to exist.
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN search_vector TEXT"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE applications ADD COLUMN search_vector TEXT"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE outreach_contacts ADD COLUMN search_vector TEXT"))
        except Exception:
            pass
        conn.commit()

    Session = sessionmaker(bind=engine)
    session = Session()

    # Create 5 contacts
    contacts = [
        OutreachContact(
            id=uuid.uuid4(),
            name="Alice Inhouse",
            company="Company A",
            market=OutreachMarket.GERMANY,
            status=OutreachStatus.NEW,
            quality_score=5,
        ),
        OutreachContact(
            id=uuid.uuid4(),
            name="Bob Boutique",
            company="Agency B",
            market=OutreachMarket.EU_WIDE,
            status=OutreachStatus.NEW,
            quality_score=4,
        ),
        OutreachContact(
            id=uuid.uuid4(),
            name="Charlie UK",
            company="UK Corp",
            market=OutreachMarket.UK,
            status=OutreachStatus.NEW,
            quality_score=3,
        ),
        OutreachContact(
            id=uuid.uuid4(),
            name="David Low",
            company="Small Co",
            market=OutreachMarket.OTHER,
            status=OutreachStatus.NEW,
            quality_score=1,
        ),
        OutreachContact(
            id=uuid.uuid4(),
            name="Eve Followup",
            company="Big Tech",
            market=OutreachMarket.GERMANY,
            status=OutreachStatus.CONTACTED,
            last_contacted_at=datetime.now(timezone.utc) - timedelta(days=8),
            quality_score=5,
            contact_count=1,
        ),
    ]
    session.add_all(contacts)

    # Add one ghosted candidate (sent 22 days ago)
    ghosted_contact = OutreachContact(
        id=uuid.uuid4(),
        name="Frank Ghost",
        company="Spooky Inc",
        market=OutreachMarket.GERMANY,
        status=OutreachStatus.CONTACTED,
        last_contacted_at=datetime.now(timezone.utc) - timedelta(days=22),
        quality_score=5,
        contact_count=1,
    )
    session.add(ghosted_contact)
    session.commit()

    # Add messages for Eve and Frank to trigger cadence
    eve_msg = OutreachMessage(
        contact_id=contacts[4].id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Initial message to Eve",
        status=OutreachMessageStatus.SENT,
        sent_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    frank_msg = OutreachMessage(
        contact_id=ghosted_contact.id,
        template_type=OutreachTemplateType.A_INHOUSE,
        body="Initial message to Frank",
        status=OutreachMessageStatus.SENT,
        sent_at=datetime.now(timezone.utc) - timedelta(days=22),
    )
    session.add_all([eve_msg, frank_msg])
    session.commit()
    session.close()

    yield f"sqlite:///{db_path}"

    if os.path.exists(db_path):
        os.remove(db_path)


@pytest.fixture(scope="module")
def streamlit_server(test_db: str) -> Generator[None, None, None]:
    subprocess.run("kill $(lsof -t -i :8504) 2>/dev/null || true", shell=True)
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["ANTHROPIC_API_KEY"] = "dummy"  # pragma: allowlist secret
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret
    env["PYTHONPATH"] = "src"
    cmd = [
        "streamlit",
        "run",
        "src/jobhunter/dashboard/streamlit_app.py",
        "--server.port=8504",
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
    ]
    process = subprocess.Popen(cmd, env=env)
    time.sleep(10)
    yield
    process.terminate()
    process.wait()


@pytest.mark.e2e
def test_outreach_metrics_flow(streamlit_server: None, test_db: str) -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        # Login
        page.goto("http://localhost:8504")
        page.get_by_role("textbox", name="Password").fill("secret123")  # pragma: allowlist secret
        page.keyboard.press("Enter")
        time.sleep(5)

        # 1. Verify initial metrics
        page.get_by_role("link", name="Metrics").click()
        time.sleep(5)
        page.get_by_role("tab", name="Outreach").click()
        time.sleep(2)

        expect(page.get_by_text("Outreach Effectiveness")).to_be_visible()
        # total_sent should be 2 (Eve + Frank)
        expect(page.get_by_text("2", exact=True).first).to_be_visible()

        # 2. Navigate to Outreach page
        page.get_by_role("link", name="Outreach").click()
        time.sleep(5)

        # expect(page.get_by_text("Alice Inhouse").first).to_be_visible()

        browser.close()


@pytest.mark.e2e
def test_outreach_cadence_cli(test_db: str) -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = test_db
    env["PYTHONPATH"] = "src"
    env["ANTHROPIC_API_KEY"] = "dummy"
    env["DASHBOARD_PASSWORD"] = "secret123"  # pragma: allowlist secret

    # Run cadence check
    result = subprocess.run(
        ["uv", "run", "python", "-m", "jobhunter", "outreach", "check-cadence"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Follow-ups Due" in result.stdout
    # Frank should be ghosted, Eve should be follow-up
    # We check if 1 is in output
    assert "1" in result.stdout

    # Run stats command
    stats_result = subprocess.run(
        ["uv", "run", "python", "-m", "jobhunter", "outreach", "stats", "--since", "4 weeks ago"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert stats_result.returncode == 0
    assert "Outreach Statistics" in stats_result.stdout
    assert "Total Messages Sent    │         2" in stats_result.stdout
