from typing import Generator
import pytest
from sqlalchemy import text
from jobhunter.db.base import Base
from jobhunter.db.session import engine


@pytest.fixture(scope="module", autouse=True)
def setup_unit_test_db() -> Generator[None, None, None]:
    """
    Creates the database schema for the test module.
    """
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS weekly_metrics CASCADE"))
            conn.commit()

    Base.metadata.create_all(bind=engine)
    yield

    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.execute(text("DROP MATERIALIZED VIEW IF EXISTS weekly_metrics CASCADE"))
            conn.commit()
    Base.metadata.drop_all(bind=engine)
