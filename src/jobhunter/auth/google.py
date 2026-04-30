import logging
import webbrowser
from datetime import timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, cast
from urllib.parse import parse_qs, urlparse

import google.oauth2.credentials
import google_auth_oauthlib.flow  # type: ignore
import httpx
from google.auth.transport.requests import Request
from sqlalchemy.orm import Session

from jobhunter.config import Settings
from jobhunter.crypto import decrypt, encrypt
from jobhunter.db.models import OAuthToken

logger = logging.getLogger(__name__)

# Minimal scopes required for reading inbox and managing labels
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GoogleOAuthHandler:
    """
    Handles Google OAuth2 flow and token management.
    """

    def __init__(self, session: Session, settings: Settings):
        self.session = session
        self.settings = settings
        self._validate_config()

    def _validate_config(self) -> None:
        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise ValueError(
                "GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET must be configured in settings."
            )
        if not self.settings.OAUTH_ENCRYPTION_KEY:
            raise ValueError("OAUTH_ENCRYPTION_KEY must be configured in settings.")

    def get_authorization_url(self) -> str:
        """
        Generates the authorization URL to start the OAuth2 flow.
        """
        flow = self._get_flow()
        authorization_url, _ = flow.authorization_url(
            access_type="offline",
            include_granted_scopes="true",
            prompt="consent",
        )
        return str(authorization_url)

    def exchange_code_for_tokens(self, code: str) -> dict[str, Any]:
        """
        Exchanges the authorization code for access and refresh tokens.
        """
        flow = self._get_flow()
        # The flow needs the redirect_uri to be set correctly for exchange
        flow.redirect_uri = self.settings.GMAIL_REDIRECT_URI
        flow.fetch_token(code=code)
        credentials = flow.credentials
        return self._save_credentials(credentials)

    def run_local_server_flow(self) -> dict[str, Any]:
        """
        Runs the full flow: opens browser, starts local server, captures code, and saves tokens.
        """
        authorization_url = self.get_authorization_url()
        webbrowser.open(authorization_url)

        # Start ephemeral server
        parsed_redirect = urlparse(self.settings.GMAIL_REDIRECT_URI)
        port = parsed_redirect.port or 8765

        code_container: dict[str, str | None] = {"code": None}

        class CallbackHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                query = parse_qs(urlparse(self.path).query)
                if "code" in query:
                    code_container["code"] = query["code"][0]
                    self.send_response(200)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"Authentication successful! You can close this tab.")
                else:
                    self.send_response(400)
                    self.send_header("Content-type", "text/html")
                    self.end_headers()
                    self.wfile.write(b"Authentication failed. No code found.")

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress server logs
                return

        server = HTTPServer(("localhost", port), CallbackHandler)

        # Run server until code is captured
        while code_container["code"] is None:
            server.handle_request()

        server.server_close()

        return self.exchange_code_for_tokens(code_container["code"])

    def _get_flow(self) -> Any:
        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise ValueError("GMAIL credentials not configured")

        client_config = {
            "installed": {
                "client_id": self.settings.GMAIL_CLIENT_ID.get_secret_value(),
                "client_secret": self.settings.GMAIL_CLIENT_SECRET.get_secret_value(),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [self.settings.GMAIL_REDIRECT_URI],
            }
        }
        return google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
            client_config, scopes=SCOPES
        )

    def _save_credentials(
        self, credentials: google.oauth2.credentials.Credentials
    ) -> dict[str, Any]:
        """
        Encrypts and persists the credentials to the database.
        """
        # To get the email, we'd need 'https://www.googleapis.com/auth/userinfo.email' scope.
        # But the requirement says "minimal scope".
        # Let's see if we can get it from the credentials.

        # If no email is found, we might need to prompt or just use a generic one.
        # For now, let's assume we want to identify by email.

        from googleapiclient.discovery import build  # type: ignore

        service = build("gmail", "v1", credentials=credentials)
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress")

        if not self.settings.OAUTH_ENCRYPTION_KEY:
            raise ValueError("OAUTH_ENCRYPTION_KEY not configured")

        encryption_key = self.settings.OAUTH_ENCRYPTION_KEY.get_secret_value()

        encrypted_access = encrypt(cast(str, credentials.token), encryption_key)
        encrypted_refresh = (
            encrypt(cast(str, credentials.refresh_token), encryption_key)
            if credentials.refresh_token
            else None
        )

        token_record = (
            self.session.query(OAuthToken).filter_by(provider="gmail", account_email=email).first()
        )

        if not token_record:
            token_record = OAuthToken(provider="gmail", account_email=email)
            self.session.add(token_record)

        token_record.access_token = encrypted_access
        if encrypted_refresh:
            token_record.refresh_token = encrypted_refresh
        token_record.expires_at = (
            credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
        )
        token_record.scopes = list(credentials.scopes)

        self.session.commit()
        return {"email": email, "scopes": credentials.scopes}

    def get_credentials(self, email: str) -> google.oauth2.credentials.Credentials:
        """
        Retrieves and decrypts credentials from the database.
        Refreshes the access token if expired.
        """
        token_record = (
            self.session.query(OAuthToken).filter_by(provider="gmail", account_email=email).first()
        )

        if not token_record:
            raise ValueError(f"No tokens found for {email}")

        if not self.settings.OAUTH_ENCRYPTION_KEY:
            raise ValueError("OAUTH_ENCRYPTION_KEY not configured")

        encryption_key = self.settings.OAUTH_ENCRYPTION_KEY.get_secret_value()
        access_token = decrypt(token_record.access_token, encryption_key)
        refresh_token = (
            decrypt(token_record.refresh_token, encryption_key)
            if token_record.refresh_token
            else None
        )

        if not self.settings.GMAIL_CLIENT_ID or not self.settings.GMAIL_CLIENT_SECRET:
            raise ValueError("GMAIL credentials not configured")

        credentials = google.oauth2.credentials.Credentials(  # type: ignore
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.GMAIL_CLIENT_ID.get_secret_value(),
            client_secret=self.settings.GMAIL_CLIENT_SECRET.get_secret_value(),
            scopes=token_record.scopes,
            expiry=token_record.expires_at.replace(tzinfo=None)
            if token_record.expires_at
            else None,
        )

        if credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
            # Save updated tokens
            token_record.access_token = encrypt(cast(str, credentials.token), encryption_key)
            if credentials.refresh_token:
                token_record.refresh_token = encrypt(
                    cast(str, credentials.refresh_token), encryption_key
                )
            token_record.expires_at = (
                credentials.expiry.replace(tzinfo=timezone.utc) if credentials.expiry else None
            )
            self.session.commit()

        return credentials

    def revoke_tokens(self, email: str) -> bool:
        """
        Revokes tokens both remotely (Google) and locally (Database).
        """
        token_record = (
            self.session.query(OAuthToken).filter_by(provider="gmail", account_email=email).first()
        )

        if not token_record:
            logger.warning(f"No tokens found for {email} to revoke.")
            return False

        if not self.settings.OAUTH_ENCRYPTION_KEY:
            raise ValueError("OAUTH_ENCRYPTION_KEY not configured")

        encryption_key = self.settings.OAUTH_ENCRYPTION_KEY.get_secret_value()

        # Try to revoke remotely
        tokens_to_revoke = []
        if token_record.refresh_token:
            tokens_to_revoke.append(decrypt(token_record.refresh_token, encryption_key))
        else:
            tokens_to_revoke.append(decrypt(token_record.access_token, encryption_key))

        for token in tokens_to_revoke:
            try:
                response = httpx.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": token},
                    headers={"content-type": "application/x-www-form-urlencoded"},
                )
                if response.status_code == 200:
                    logger.info(f"Successfully revoked token remotely for {email}")
                else:
                    logger.warning(f"Failed to revoke token remotely for {email}: {response.text}")
            except Exception as e:
                logger.error(f"Error revoking token remotely for {email}: {e}")

        # Delete locally regardless of remote success
        self.session.delete(token_record)
        self.session.commit()
        logger.info(f"Deleted tokens locally for {email}")

        return True

    def list_authenticated_emails(self) -> list[str]:
        """
        Returns a list of emails that have active OAuth tokens.
        """
        records = self.session.query(OAuthToken).filter_by(provider="gmail").all()
        return [r.account_email for r in records]
