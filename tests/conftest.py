import pytest
from collections.abc import Generator
from sqlalchemy.orm import Session
from jobhunter.db.session import SessionLocal, engine
from jobhunter.db.base import Base


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """
    Creates the database schema for the test session.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """
    Provides a transactional SQLAlchemy session for each test.
    Rolls back any changes at the end of the test.
    """
    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()
