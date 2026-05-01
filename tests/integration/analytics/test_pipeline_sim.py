from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from jobhunter.db.models import Job, Application, LLMCall, OutreachMessage
from jobhunter.db.enums import JobTier, JobStatus, ApplicationStatus, OutreachMessageStatus
from jobhunter.analytics.regression_detector import check_metrics
from jobhunter.analytics.recommendations import get_recommendations
import uuid


def test_full_pipeline_simulation_analytics(session: Session) -> None:
    """
    Simulates 3 months of data and verifies that analytics commands produce coherent results.
    """
    now = datetime.now(timezone.utc)

    # --- PHASE 1: SEED 3 MONTHS OF DATA ---
    # We'll create two periods:
    # Baseline (months 1-2): Good performance
    # Current (last 7 days): Regression in some metrics

    # 1. Ingested Jobs (Tier A Rate regression)
    # Baseline: 100 jobs, 20 Tier A (20%)
    for i in range(100):
        session.add(
            Job(
                source="test_source",
                url=f"http://example.com/{uuid.uuid4()}",
                url_hash=str(uuid.uuid4()),
                title="Dev",
                company="Company",
                description="Desc",
                scraped_at=now - timedelta(days=20),
                tier=JobTier.A if i < 20 else JobTier.REJECT,
                status=JobStatus.REJECTED if i >= 20 else JobStatus.QUEUED,
            )
        )

    # Current: 20 jobs, 1 Tier A (5%) -> Regression
    for i in range(20):
        session.add(
            Job(
                source="test_source",
                url=f"http://example.com/{uuid.uuid4()}",
                url_hash=str(uuid.uuid4()),
                title="Dev",
                company="Company",
                description="Desc",
                scraped_at=now - timedelta(days=2),
                tier=JobTier.A if i < 1 else JobTier.REJECT,
                status=JobStatus.REJECTED if i >= 1 else JobStatus.QUEUED,
            )
        )

    # 2. Applications (Application Rate)
    # Baseline: 20 Tier A, 10 applied (50%)
    tier_a_baseline = (
        session.query(Job)
        .filter(Job.scraped_at < now - timedelta(days=7), Job.tier == JobTier.A)
        .all()
    )
    for job in tier_a_baseline[:10]:
        session.add(
            Application(
                job_id=job.id, applied_at=now - timedelta(days=15), status=ApplicationStatus.APPLIED
            )
        )

    # 3. Recommendations Heuristics
    # Template zero response: 10 sent, 0 replies in last 4 weeks
    for i in range(10):
        session.add(
            OutreachMessage(
                contact_id=uuid.uuid4(),
                template_type="B_boutique",
                status=OutreachMessageStatus.SENT,
                sent_at=now - timedelta(days=10),
                body="Mock body",
                subject="Mock subject",
            )
        )

    # LLM Budget: $90 spent, budget is $100 -> P1 recommendation
    for i in range(9):
        session.add(
            LLMCall(
                model="claude-3-haiku",
                purpose="scoring",
                success=True,
                cost_usd=10.0,
                called_at=now.replace(day=1),
            )
        )

    session.commit()

    # --- PHASE 2: RUN ANALYTICS ---

    # 1. Regression Detector
    report = check_metrics(session)

    tier_a_metric = next(m for m in report.metrics if m.name == "Tier A Rate")
    assert tier_a_metric.current_value == 5.0
    assert tier_a_metric.baseline_value == 20.0
    assert tier_a_metric.is_regression is True

    # 2. Recommendations
    recs = get_recommendations(session)

    # Should recommend pausing B_boutique template
    assert any("Pausar template 'B_boutique'" in r.action for r in recs)

    # Should warn about budget
    assert any("Revisar uso de LLM" in r.action for r in recs)

    # 3. Verify CLI output (smoke test)
    from typer.testing import CliRunner
    from jobhunter.__main__ import app
    import os

    # 3. Verify CLI output (smoke test)
    from pathlib import Path

    # Create a temporary test DB file for the CLI smoke test
    test_db_file = Path("test_pipeline_sim_smoke.db")
    if test_db_file.exists():
        test_db_file.unlink()

    test_db_url = f"sqlite:///{test_db_file}"

    # Initialize the smoke test DB with the same schema
    from sqlalchemy import create_engine
    from jobhunter.db.base import Base

    smoke_engine = create_engine(test_db_url)
    Base.metadata.create_all(bind=smoke_engine)

    runner = CliRunner()
    # Mocking environment for CLI
    env = os.environ.copy()
    env["TEST_DATABASE_URL"] = test_db_url

    # But we can test if the command exists and handles flags
    result = runner.invoke(app, ["analytics", "check-regressions", "--markdown"], env=env)

    # Cleanup
    if test_db_file.exists():
        test_db_file.unlink()
    assert result.exit_code == 0
    assert "### 📉 Regression Analysis" in result.output
