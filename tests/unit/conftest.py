import pytest
from unittest.mock import MagicMock

@pytest.fixture(scope="session", autouse=True)
def setup_database() -> MagicMock:
    """
    Mock the global database setup to avoid PostgreSQL-specific issues in unit tests.
    """
    return MagicMock()
