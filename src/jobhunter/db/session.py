from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from jobhunter.config import Settings

# Initialize settings
settings: Settings = Settings()  # type: ignore[call-arg]

# Create engine
# In SQLAlchemy 2.0, future=True is default, but we can be explicit if we want
engine: Engine = create_engine(settings.DATABASE_URL)

# Create SessionLocal class
SessionLocal: sessionmaker[Session] = sessionmaker(autocommit=False, autoflush=False, bind=engine)


_test_engine: Engine | None = None
_test_session_local: sessionmaker[Session] | None = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Dependency to get a SQLAlchemy session.
    Ensures the session is closed after use.

    Yields:
        Session: The SQLAlchemy session.
    """
    import os

    global _test_engine, _test_session_local

    test_db_url = os.getenv("TEST_DATABASE_URL")
    if test_db_url:
        if _test_engine is None:
            _test_engine = create_engine(test_db_url)
            _test_session_local = sessionmaker(
                autocommit=False, autoflush=False, bind=_test_engine, expire_on_commit=False
            )
        if _test_session_local:
            session = _test_session_local()
        else:
            session = SessionLocal()
    else:
        session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
