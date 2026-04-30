from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from jobhunter.auth.google import GoogleOAuthHandler
from jobhunter.config import Settings
from jobhunter.crypto import decrypt, encrypt
from jobhunter.db.base import Base
from jobhunter.db.models import OAuthToken


@pytest.fixture
def mock_settings() -> Settings:
    return Settings(
        ANTHROPIC_API_KEY=SecretStr("dummy"),
        DASHBOARD_PASSWORD=SecretStr("dummy"),
        GMAIL_CLIENT_ID=SecretStr("client-id"),
        GMAIL_CLIENT_SECRET=SecretStr("client-secret"),
        OAUTH_ENCRYPTION_KEY=SecretStr(Fernet.generate_key().decode()),
    )


@pytest.fixture
def db_session() -> Any:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_google_oauth_handler_initialization(db_session: Any, mock_settings: Settings) -> None:
    handler = GoogleOAuthHandler(db_session, mock_settings)
    assert handler.session == db_session
    assert handler.settings == mock_settings


def test_get_authorization_url(db_session: Any, mock_settings: Settings) -> None:
    handler = GoogleOAuthHandler(db_session, mock_settings)
    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_flow_init:
        mock_flow = MagicMock()
        mock_flow.authorization_url.return_value = ("https://auth.url", "state")
        mock_flow_init.return_value = mock_flow

        url = handler.get_authorization_url()
        assert url == "https://auth.url"


@patch("googleapiclient.discovery.build")
def test_exchange_code_for_tokens(
    mock_build: MagicMock, db_session: Any, mock_settings: Settings
) -> None:
    handler = GoogleOAuthHandler(db_session, mock_settings)

    # Mock Flow
    with patch("google_auth_oauthlib.flow.InstalledAppFlow.from_client_config") as mock_flow_init:
        mock_flow = MagicMock()
        mock_credentials = MagicMock()
        mock_credentials.token = "access-token"
        mock_credentials.refresh_token = "refresh-token"
        mock_credentials.expiry = datetime.now() + timedelta(hours=1)
        mock_credentials.scopes = ["scope1"]
        mock_flow.credentials = mock_credentials
        mock_flow_init.return_value = mock_flow

        # Mock Gmail Service for email address
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.users().getProfile().execute.return_value = {"emailAddress": "test@gmail.com"}

        result = handler.exchange_code_for_tokens("auth-code")

        assert result["email"] == "test@gmail.com"

        # Verify DB persistence
        token_record = (
            db_session.query(OAuthToken).filter_by(account_email="test@gmail.com").first()
        )
        assert token_record is not None

        assert mock_settings.OAUTH_ENCRYPTION_KEY is not None
        key = mock_settings.OAUTH_ENCRYPTION_KEY.get_secret_value()
        assert decrypt(token_record.access_token, key) == "access-token"
        assert decrypt(token_record.refresh_token, key) == "refresh-token"


def test_get_credentials_and_refresh(db_session: Any, mock_settings: Settings) -> None:
    assert mock_settings.OAUTH_ENCRYPTION_KEY is not None
    key = mock_settings.OAUTH_ENCRYPTION_KEY.get_secret_value()

    # Pre-populate DB with expired token
    expiry = datetime.now(timezone.utc) - timedelta(minutes=5)
    token_record = OAuthToken(
        provider="gmail",
        account_email="expired@gmail.com",
        access_token=encrypt("old-access", key),
        refresh_token=encrypt("refresh-token", key),
        expires_at=expiry,
        scopes=["scope1"],
    )
    db_session.add(token_record)
    db_session.commit()

    handler = GoogleOAuthHandler(db_session, mock_settings)
    assert mock_settings.OAUTH_ENCRYPTION_KEY is not None

    with patch("google.oauth2.credentials.Credentials.refresh"):
        # We need to capture the credentials object created inside get_credentials
        # or mock the whole Credentials class.

        with patch("google.oauth2.credentials.Credentials") as MockCreds:
            mock_creds_inst = MockCreds.return_value
            mock_creds_inst.expired = True
            mock_creds_inst.refresh_token = "refresh-token"
            mock_creds_inst.token = "new-access"
            mock_creds_inst.expiry = datetime.now() + timedelta(hours=1)

            handler.get_credentials("expired@gmail.com")

            assert mock_creds_inst.refresh.called

            # Verify DB updated
            db_session.expire_all()
            updated_record = (
                db_session.query(OAuthToken).filter_by(account_email="expired@gmail.com").first()
            )
            assert decrypt(updated_record.access_token, key) == "new-access"


@patch("httpx.post")
def test_revoke_tokens(mock_post: MagicMock, db_session: Any, mock_settings: Settings) -> None:
    assert mock_settings.OAUTH_ENCRYPTION_KEY is not None
    key = mock_settings.OAUTH_ENCRYPTION_KEY.get_secret_value()

    token_record = OAuthToken(
        provider="gmail",
        account_email="revoke@gmail.com",
        access_token=encrypt("access", key),
        refresh_token=encrypt("refresh", key),
    )
    db_session.add(token_record)
    db_session.commit()

    mock_post.return_value = MagicMock(status_code=200)

    handler = GoogleOAuthHandler(db_session, mock_settings)
    assert mock_settings.OAUTH_ENCRYPTION_KEY is not None
    success = handler.revoke_tokens("revoke@gmail.com")

    assert success
    assert mock_post.called

    # Verify DB deleted
    deleted_record = (
        db_session.query(OAuthToken).filter_by(account_email="revoke@gmail.com").first()
    )
    assert deleted_record is None
