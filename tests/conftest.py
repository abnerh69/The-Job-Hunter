import pytest
from collections.abc import Generator
from sqlalchemy import text
from sqlalchemy.orm import Session
import json
from pathlib import Path
from jobhunter.db.session import SessionLocal, engine
from jobhunter.db.base import Base
from jobhunter.db.models import Job, Application, OutreachContact
from jobhunter.db.enums import JobStatus, ApplicationStatus, OutreachStatus, LLMPurpose
from jobhunter.llm.anthropic_client import LLMResponse
from jobhunter.llm.pricing import calculate_cost_usd
from jobhunter.scoring.scorer import JobScorer
from uuid import UUID


class MockLLMClient:
    """
    Mock LLM client that returns responses from fixtures based on prompt patterns.
    """

    def __init__(self, fixtures_dir: Path):
        self.fixtures_dir = fixtures_dir
        self.call_count = 0

    async def complete(
        self,
        system: str,
        user: str,
        model: str,
        purpose: LLMPurpose,
        session: Session | None = None,
        job_id: UUID | None = None,
        prompt_version: str | None = None,
        max_tokens: int = 1500,
    ) -> LLMResponse:
        self.call_count += 1
        user_lower = user.lower()

        fixture_name = "tier_b_borderline.json"  # Default

        # Use substrings that are definitely in the rendered USER_TEMPLATE
        if "python and ai stack" in user_lower:
            fixture_name = "tier_a_python_ai.json"
        elif "flutter apps development" in user_lower:
            fixture_name = "tier_a_flutter.json"
        elif "manual review needed for maintenance" in user_lower:
            fixture_name = "tier_c_manual_review.json"
        elif "eu work permit required strictly" in user_lower:
            fixture_name = "reject_eu_only.json"
        elif "low salary offered for this junior role" in user_lower:
            fixture_name = "reject_low_salary.json"
        elif "invalid post that looks like a spam job" in user_lower:
            fixture_name = "invalid_response.json"
        elif "this will return malformed first" in user_lower:
            # Special case for testing retry of parsing: return malformed first, then valid
            if self.call_count == 1:
                fixture_name = "malformed_json.txt"
            else:
                fixture_name = "tier_a_python_ai.json"

        fixture_path = self.fixtures_dir / fixture_name
        with open(fixture_path) as f:
            text = f.read()

        input_tokens = 500
        output_tokens = 300
        cost_usd = calculate_cost_usd(model, input_tokens, output_tokens)

        # If session is provided, record the call like the real client does
        if session:
            from jobhunter.db.repos.llm_calls import LLMCallRepo

            repo = LLMCallRepo(session)
            repo.record_call(
                model=model,
                purpose=purpose,
                success=True,
                job_id=job_id,
                prompt_version=prompt_version,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost_usd,
                duration_ms=100,
            )

        return LLMResponse(
            text=text,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            duration_ms=100,
            stop_reason="end_turn",
        )


@pytest.fixture
def mock_llm_client() -> MockLLMClient:
    """Provides a MockLLMClient."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "scoring_responses"
    return MockLLMClient(fixtures_dir)


@pytest.fixture
def mock_job_scorer(mock_llm_client: MockLLMClient) -> JobScorer:
    """Provides a JobScorer using a MockLLMClient."""
    return JobScorer(llm_client=mock_llm_client)  # type: ignore[arg-type]


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> Generator[None, None, None]:
    """
    Creates the database schema for the test session.
    """
    # Drop everything first to ensure a clean state
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS weekly_metrics CASCADE"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f"DROP TABLE IF EXISTS {table.name} CASCADE"))
            conn.commit()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Re-create the materialized view for PostgreSQL
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(
                text("""
                CREATE MATERIALIZED VIEW weekly_metrics AS
                SELECT
                    date_trunc('week', applied_at)::date AS week,
                    COUNT(*) AS apps_sent,
                    COUNT(*) FILTER (WHERE status NOT IN ('applied', 'ghosted', 'withdrawn')) AS apps_with_response,
                    COUNT(*) FILTER (WHERE status IN ('screening', 'interview_1', 'interview_n', 'offer')) AS interviews,
                    COUNT(*) FILTER (WHERE status = 'offer') AS offers,
                    AVG(salary_offered_max) FILTER (WHERE status = 'offer') AS avg_offer_max
                FROM applications
                GROUP BY 1
            """)
            )
            conn.execute(
                text("CREATE UNIQUE INDEX idx_weekly_metrics_week ON weekly_metrics (week)")
            )
            conn.commit()
    yield
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS weekly_metrics CASCADE"))
            for table in reversed(Base.metadata.sorted_tables):
                conn.execute(text(f"DROP TABLE IF EXISTS {table.name} CASCADE"))
            conn.commit()
    else:
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    """
    Provides a transactional SQLAlchemy session for each test.
    Rolls back any changes at the end of the test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(session: Session) -> Session:
    """Alias for session fixture for compatibility."""
    return session


@pytest.fixture
def sample_job(db_session: Session) -> Job:
    """Provides a sample Job instance persisted in the DB."""
    fixtures_path = Path(__file__).parent / "fixtures"
    with open(fixtures_path / "sample_jobs.json") as f:
        jobs_data = json.load(f)

    data = jobs_data[0]
    job = Job(
        source=data["source"],
        url=data["url"],
        url_hash=data["url_hash"],
        title=data["title"],
        company=data["company"],
        description=data["description"],
        status=JobStatus.NEW,
    )
    db_session.add(job)
    db_session.flush()
    return job


@pytest.fixture
def sample_application(db_session: Session, sample_job: Job) -> Application:
    """Provides a sample Application instance persisted in the DB."""
    app = Application(
        job_id=sample_job.id,
        status=ApplicationStatus.APPLIED,
        application_method="LinkedIn",
    )
    db_session.add(app)
    db_session.flush()
    return app


@pytest.fixture
def sample_outreach_contact(db_session: Session) -> OutreachContact:
    """Provides a sample OutreachContact instance persisted in the DB."""
    contact = OutreachContact(
        name="John Doe",
        linkedin_url="https://linkedin.com/in/johndoe",
        status=OutreachStatus.NEW,
    )
    db_session.add(contact)
    db_session.flush()
    return contact
