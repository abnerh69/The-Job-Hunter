from typing import Generator
import pytest
from jobhunter.db.base import Base
from jobhunter.db.session import engine


@pytest.fixture(scope="module", autouse=True)
def setup_unit_test_db() -> Generator[None, None, None]:
    """
    Creates the database schema for the test module.
    """
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
