import pytest
from unittest.mock import MagicMock
from typing import Any


@pytest.fixture(scope="session", autouse=True)
def setup_database() -> None:
    # Do nothing, bypass session-level DB setup for unit tests in this directory
    pass


@pytest.fixture
def session() -> Any:
    return MagicMock()


@pytest.fixture
def db_session() -> Any:
    return MagicMock()
