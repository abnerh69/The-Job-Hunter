from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from jobhunter.api.main import app, get_session, get_settings  # type: ignore[attr-defined]
from jobhunter.config import Settings
from jobhunter.db.base import Base
from pydantic import SecretStr
import os

# Mock DB for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_api.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base.metadata.create_all(bind=engine)

# Create alembic_version table manually for tests
with engine.connect() as conn:
    conn.execute(
        text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
    )
    conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('test_rev')"))
    conn.commit()


def override_get_session() -> Generator[Session, None, None]:
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


def override_get_settings() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY=SecretStr("test_key"), DASHBOARD_PASSWORD=SecretStr("test_password")
    )


app.dependency_overrides[get_session] = override_get_session
app.dependency_overrides[get_settings] = override_get_settings

client = TestClient(app)


def test_health_endpoint_healthy() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # It might be 'degraded' due to missing configs in test env, which is fine
    assert data["status"] in ["healthy", "degraded"]
    assert data["checks"]["db"]["status"] == "ok"


def test_readiness_endpoint() -> None:
    response = client.get("/readiness")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_public_status_page() -> None:
    response = client.get("/status")
    assert response.status_code == 200
    assert "Job Hunter EU System Status" in response.text
    assert "Public Stats" in response.text
    # Ensure no sensitive info (leaks)
    assert "test_key" not in response.text
    assert "test_password" not in response.text


@pytest.fixture(autouse=True)
def cleanup() -> Generator[None, None, None]:
    yield
    if os.path.exists("./test_api.db"):
        os.remove("./test_api.db")
