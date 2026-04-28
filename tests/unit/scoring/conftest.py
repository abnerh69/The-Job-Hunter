import pytest


@pytest.fixture(autouse=True)
def skip_db_setup() -> None:
    """
    Prevents global database setup in tests/conftest.py for these unit tests.
    """
    pass
