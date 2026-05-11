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


def _make_session() -> Session:
    """Create a SQLAlchemy Session, honoring TEST_DATABASE_URL when set.

    Internal helper shared by the CLI context manager (`get_session`) and the
    FastAPI dependency (`get_db`). Centralizes the lazy test-engine bootstrap
    so both entry points behave identically.
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
            return _test_session_local()
        return SessionLocal()
    return SessionLocal()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a Session and closes it on teardown.

    Must NOT be decorated with ``@contextmanager`` — FastAPI's ``Depends``
    requires a *raw* generator function. Use this for ``Depends(get_db)``
    in API routes. For CLI / script usage, use ``get_session`` (below),
    which wraps this in a context manager.
    """
    session = _make_session()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for CLI / scripts: ``with get_session() as session: ...``.

    Do NOT pass this to FastAPI ``Depends`` — use ``get_db`` instead.
    """
    session = _make_session()
    try:
        yield session
    finally:
        session.close()
