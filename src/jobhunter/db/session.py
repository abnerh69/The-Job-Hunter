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


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Dependency to get a SQLAlchemy session.
    Ensures the session is closed after use.

    Yields:
        Session: The SQLAlchemy session.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
