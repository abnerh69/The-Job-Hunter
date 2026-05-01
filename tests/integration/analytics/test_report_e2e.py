import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Any
from sqlalchemy.orm import Session
from typer.testing import CliRunner
from jobhunter.__main__ import app
from jobhunter.db.models import Job, Application
from jobhunter.db.enums import JobTier, JobStatus, ApplicationStatus


def test_monthly_report_generation_e2e(session: Session, mock_llm_client: Any) -> None:
    """
    Verifies that the monthly report can be generated via CLI with LLM mocking.
    """
    # 1. Setup persistent test DB for CLI subprocess
    test_db_file = Path("test_report_e2e.db")
    if test_db_file.exists():
        test_db_file.unlink()
    test_db_url = f"sqlite:///{test_db_file}"
    os.environ["TEST_DATABASE_URL"] = test_db_url

    from sqlalchemy import create_engine
    from jobhunter.db.base import Base

    test_engine = create_engine(test_db_url)
    Base.metadata.create_all(bind=test_engine)

    from sqlalchemy.orm import sessionmaker

    Session_local = sessionmaker(bind=test_engine)
    db_session = Session_local()

    # 2. Seed some data for the report
    now = datetime.now(timezone.utc)
    last_month = (now.replace(day=1) - timedelta(days=1)).replace(day=1)

    # Create jobs and applications for last month
    job = Job(
        source="test",
        url="http://example.com/1",
        url_hash="hash1",
        title="Dev",
        company="Comp",
        description="Desc",
        scraped_at=last_month + timedelta(days=5),
        tier=JobTier.A,
        status=JobStatus.APPLIED,
    )
    db_session.add(job)
    db_session.flush()

    db_session.add(
        Application(
            job_id=job.id,
            applied_at=last_month + timedelta(days=6),
            status=ApplicationStatus.APPLIED,
        )
    )
    db_session.commit()

    # 3. Create mock prompt file
    prompt_dir = Path("prompts/analytics_report")
    prompt_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = prompt_dir / "v1.md"
    prompt_file.write_text(
        "## SYSTEM\nYou are an analyst.\n## USER_TEMPLATE\nReport for {month}.\nMetrics: {current_metrics}"
    )

    # 4. Run CLI command
    runner = CliRunner()
    # We need to mock AnthropicLLMClient.complete or ensure it uses MockLLMClient
    # Since the CLI creates its own client, we might need a different approach or
    # rely on the fact that we're testing the CLI flow.

    # Actually, generate_narrative_report is called inside analytics_report.
    # If we want to mock it properly in an E2E test, we'd need to monkeypatch
    # but CliRunner.invoke runs in the same process (usually).

    import unittest.mock as mock

    with mock.patch("jobhunter.__main__.AnthropicLLMClient") as mock_client_cls:
        mock_instance = mock_client_cls.return_value
        mock_instance.complete = mock.AsyncMock(
            return_value=mock.MagicMock(text="# Monthly Report\nCoherent content.")
        )

        month_str = last_month.strftime("%Y-%m")
        result = runner.invoke(app, ["analytics", "report", "--month", month_str, "--output", "md"])

        print(result.output)
        assert result.exit_code == 0
        assert "Markdown report saved to reports/" in result.output
        assert "Monthly Report" in result.output

    # 5. Cleanup
    db_session.close()
    if test_db_file.exists():
        test_db_file.unlink()
    os.environ.pop("TEST_DATABASE_URL", None)
    if prompt_file.exists():
        prompt_file.unlink()
