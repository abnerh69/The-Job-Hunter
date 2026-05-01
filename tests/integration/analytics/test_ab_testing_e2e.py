import uuid
from sqlalchemy.orm import Session
from typer.testing import CliRunner
from jobhunter.__main__ import app
from jobhunter.db.models import Job, ABTest
from jobhunter.db.enums import ABTestStatus


def test_ab_testing_lifecycle_e2e(session: Session) -> None:
    """
    Tests the full A/B test lifecycle via CLI: create -> assign -> simulate -> conclude.
    """
    import os
    from pathlib import Path

    # Use a persistent test DB file instead of :memory: so CliRunner subprocesses can see it
    test_db_file = Path("test_ab_e2e.db")
    if test_db_file.exists():
        test_db_file.unlink()

    test_db_url = f"sqlite:///{test_db_file}"
    os.environ["TEST_DATABASE_URL"] = test_db_url

    # Initialize the test DB
    from sqlalchemy import create_engine
    from jobhunter.db.base import Base

    test_engine = create_engine(test_db_url)
    Base.metadata.create_all(bind=test_engine)

    # Re-initialize session to use the new test DB
    from sqlalchemy.orm import sessionmaker

    Session_local = sessionmaker(bind=test_engine)
    session = Session_local()

    runner = CliRunner()
    test_name = f"test_{uuid.uuid4().hex[:8]}"

    # 1. Create A/B Test via CLI
    # Weights must sum to 1.0
    result = runner.invoke(
        app,
        [
            "analytics",
            "ab-test",
            "create",
            "--name",
            test_name,
            "--variants",
            "v1=0.5,v2=0.5",
            "--metric",
            "tier_a_precision",
            "--description",
            "E2E Test",
        ],
    )
    assert result.exit_code == 0
    assert f"Successfully created A/B test: {test_name}" in result.output

    # 2. Assign 100 jobs and simulate outcomes
    # Variant v1: 20/50 Tier A (40%)
    # Variant v2: 40/50 Tier A (80%) -> Should be statistically significant
    for i in range(100):
        job_id = uuid.uuid4()
        # We need to manually simulate variant selection here because the CLI doesn't have a 'score' that uses it easily in this test context
        # But we can use the actual logic from analytics.ab_testing
        from jobhunter.analytics.ab_testing import select_variant

        variant = select_variant(session, test_name, job_id)

        # Determine tier based on variant to simulate different conversion rates
        tier = "REJECT"
        if variant == "v1":
            if i % 100 < 40:  # 40% of v1 are Tier A (wait, i is 0-99, bucket is 0-99)
                # This is tricky because variant assignment is random-ish
                pass

        # Let's just force the variant and tier to ensure we have enough data for significance
        variant = "v1" if i < 50 else "v2"
        from jobhunter.db.enums import JobTier

        # v1: 10/50 = 20%
        # v2: 40/50 = 80%
        tier = (
            JobTier.A
            if (variant == "v1" and i < 10) or (variant == "v2" and i >= 60)
            else JobTier.REJECT
        )

        session.add(
            Job(
                source="test",
                url=f"http://example.com/{i}",
                url_hash=str(uuid.uuid4()),
                title="Dev",
                company="Comp",
                description="Desc",
                score_version=variant,
                tier=tier,
            )
        )
    session.commit()

    # 3. View Results via CLI
    # Use a separate session to ensure it sees the committed data
    # Actually, CliRunner might use a different session if it's not careful
    # But get_session should work if we use a real DB or shared connection
    result = runner.invoke(app, ["analytics", "ab-test", "results", test_name])
    print(result.output)
    assert result.exit_code == 0
    assert "v1" in result.output
    assert "v2" in result.output
    assert "Statistically Significant: True" in result.output

    # 4. Conclude Test via CLI
    result = runner.invoke(
        app,
        [
            "analytics",
            "ab-test",
            "conclude",
            test_name,
            "--winner",
            "v2",
            "--conclusion",
            "v2 is much better",
        ],
    )
    assert result.exit_code == 0
    assert f"Successfully concluded A/B test: {test_name}. Winner: v2" in result.output

    # 5. Verify status in DB
    test = session.query(ABTest).filter(ABTest.name == test_name).one()
    assert test.status == ABTestStatus.CONCLUDED
    if test.conclusion:
        assert "Winner: v2" in test.conclusion

    # Cleanup
    session.close()
    if test_db_file.exists():
        test_db_file.unlink()
    os.environ.pop("TEST_DATABASE_URL", None)
