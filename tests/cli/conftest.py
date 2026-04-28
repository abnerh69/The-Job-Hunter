import pytest

@pytest.fixture(autouse=True)
def setup_database() -> None:
    # Override global setup_database to do nothing for CLI tests
    pass

@pytest.fixture(autouse=True)
def mock_db_session() -> None:
    # CLI unit tests should not use real DB sessions
    pass
