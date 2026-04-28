import pytest
from collections.abc import Generator
from sqlalchemy import text
from sqlalchemy.orm import Session
from jobhunter.db.session import SessionLocal, engine
from jobhunter.db.base import Base


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
