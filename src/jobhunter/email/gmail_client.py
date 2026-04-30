import asyncio
import base64
import logging
from datetime import datetime, timezone
from typing import Any, cast

import google.oauth2.credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from jobhunter.config import Settings
from jobhunter.crypto import decrypt, encrypt
from jobhunter.db.repos.oauth_tokens import OAuthTokenRepo
from jobhunter.email.schemas import GmailMessage, GmailMessageDetail, Label

logger = logging.getLogger(__name__)


class GmailClient:
    """
    Wrapper over Gmail API with token management and rate limiting.
    """

    def __init__(self, token_repo: OAuthTokenRepo, account_email: str, settings: Settings):
        self.token_repo = token_repo
        self.account_email = account_email
        self.settings = settings
        self._semaphore = asyncio.Semaphore(1)  # 1 request per 200ms is roughly handled by sleeping
        self._service: Resource | None = None

    async def _get_service(self) -> Resource:
        """
        Retrieves and decrypts credentials from the database, refreshes if needed,
        and returns the Gmail API service resource.
        """
        if self._service:
            return self._service

        token_record = self.token_repo.get_token("gmail", self.account_email)
        if not token_record:
            raise ValueError(f"No tokens found for {self.account_email}")

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

        credentials = google.oauth2.credentials.Credentials(
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
            logger.info("Refreshing Gmail access token", email=self.account_email)
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
            self.token_repo.session.commit()

        self._service = build("gmail", "v1", credentials=credentials)
        return self._service

    def _parse_message(self, raw: dict[str, Any]) -> dict[str, Any]:
        """
        Parses a raw Gmail message into a structured dictionary.
        Handles multipart payloads and base64 decoding.
        """
        payload = raw.get("payload", {})
        headers = payload.get("headers", [])

        header_map = {h["name"].lower(): h["value"] for h in headers}

        # Extract basic info
        message_data = {
            "id": raw["id"],
            "threadId": raw["threadId"],
            "snippet": raw.get("snippet"),
            "labels": raw.get("labelIds", []),
            "from_email": header_map.get("from", ""),
            "to_email": header_map.get("to", ""),
            "subject": header_map.get("subject", ""),
            "received_at": datetime.fromtimestamp(
                int(raw["internalDate"]) / 1000, tz=timezone.utc
            ),
        }

        # Parse body
        body_text = ""
        body_html = ""

        def _get_parts(part: dict[str, Any]) -> None:
            nonlocal body_text, body_html
            mime_type = part.get("mimeType")
            body = part.get("body", {})
            data = body.get("data")

            if data:
                decoded_data = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                if mime_type == "text/plain":
                    body_text += decoded_data
                elif mime_type == "text/html":
                    body_html += decoded_data

            if "parts" in part:
                for subpart in part["parts"]:
                    _get_parts(subpart)

        _get_parts(payload)

        # If it was a simple message without 'parts' in payload
        if not body_text and not body_html:
            body = payload.get("body", {})
            data = body.get("data")
            if data:
                decoded_data = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                if payload.get("mimeType") == "text/plain":
                    body_text = decoded_data
                elif payload.get("mimeType") == "text/html":
                    body_html = decoded_data

        message_data["body_text"] = body_text
        message_data["body_html"] = body_html

        return message_data

    @retry(
        retry=retry_if_exception_type(HttpError),
        stop=stop_after_attempt(2),
        wait=wait_fixed(0),  # Immediate retry if we refreshed tokens
        reraise=True,
    )
    async def _execute_with_refresh(self, request: Any) -> Any:
        """
        Executes a Google API request with automatic token refresh on 401.
        """
        async with self._semaphore:
            # We enforce 200ms between requests (very simple rate limiting)
            await asyncio.sleep(0.2)
            try:
                return request.execute()
            except HttpError as e:
                if e.resp.status == 401:
                    logger.info("Access token expired, forcing refresh", email=self.account_email)
                    self._service = None  # Force re-creation and refresh
                    await self._get_service()
                    # Re-bind the request to the new service if possible?
                    # Actually, if we use the request object passed, it might still have old credentials.
                    # Better to let the caller handle the service re-acquisition.
                    # But wait, request.execute() uses the credentials from the service it was built from.
                    # If we refresh, we need a NEW request object.
                    # So this retry logic is better placed in methods or using a lambda.
                    raise
                raise

    async def list_messages(self, query: str, max_results: int = 50) -> list[GmailMessage]:
        """
        Lists Gmail messages matching a query.
        """
        try:
            full_messages = []

            async def _do_list() -> dict[str, Any]:
                service = await self._get_service()
                return await self._execute_with_refresh(
                    service.users().messages().list(userId="me", q=query, maxResults=max_results)
                )

            results = await _do_list()
            messages_summaries = results.get("messages", [])

            for summary in messages_summaries:

                async def _do_get() -> dict[str, Any]:
                    service = await self._get_service()
                    return await self._execute_with_refresh(
                        service.users()
                        .messages()
                        .get(userId="me", id=summary["id"], format="minimal")
                    )

                raw_msg = await _do_get()
                parsed = self._parse_message(raw_msg)
                full_messages.append(GmailMessage(**parsed))

            return full_messages
        except HttpError as e:
            logger.error("Failed to list messages", error=str(e))
            raise

    async def get_message(self, message_id: str) -> GmailMessageDetail:
        """
        Retrieves full details of a Gmail message.
        """
        try:

            async def _do_get() -> dict[str, Any]:
                service = await self._get_service()
                return await self._execute_with_refresh(
                    service.users().messages().get(userId="me", id=message_id)
                )

            raw_msg = await _do_get()
            parsed = self._parse_message(raw_msg)
            return GmailMessageDetail(**parsed)
        except HttpError as e:
            logger.error("Failed to get message", message_id=message_id, error=str(e))
            raise

    async def list_labels(self) -> list[Label]:
        """
        Lists all Gmail labels.
        """
        try:

            async def _do_list() -> dict[str, Any]:
                service = await self._get_service()
                return await self._execute_with_refresh(service.users().labels().list(userId="me"))

            results = await _do_list()
            labels = results.get("labels", [])
            return [Label(id=l["id"], name=l["name"], type=l.get("type")) for l in labels]
        except HttpError as e:
            logger.error("Failed to list labels", error=str(e))
            raise

    async def add_label(self, message_id: str, label_name: str) -> None:
        """
        Adds a label to a message. Creates the label if it doesn't exist.
        """
        try:
            # Check if label exists
            labels = await self.list_labels()
            label_id = next((l.id for l in labels if l.name == label_name), None)

            if not label_id:
                # Create label

                async def _do_create() -> dict[str, Any]:
                    service = await self._get_service()
                    return await self._execute_with_refresh(
                        service.users()
                        .labels()
                        .create(
                            userId="me", body={"name": label_name, "labelListVisibility": "labelShow"}
                        )
                    )

                new_label = await _do_create()
                label_id = new_label["id"]

            async def _do_modify() -> dict[str, Any]:
                service = await self._get_service()
                return await self._execute_with_refresh(
                    service.users()
                    .messages()
                    .modify(userId="me", id=message_id, body={"addLabelIds": [label_id]})
                )

            await _do_modify()
        except HttpError as e:
            logger.error(
                "Failed to add label", message_id=message_id, label=label_name, error=str(e)
            )
            raise

    async def remove_label(self, message_id: str, label_name: str) -> None:
        """
        Removes a label from a message.
        """
        try:
            labels = await self.list_labels()
            label_id = next((l.id for l in labels if l.name == label_name), None)

            if not label_id:
                logger.warning("Label not found for removal", label=label_name)
                return

            async def _do_modify() -> dict[str, Any]:
                service = await self._get_service()
                return await self._execute_with_refresh(
                    service.users()
                    .messages()
                    .modify(userId="me", id=message_id, body={"removeLabelIds": [label_id]})
                )

            await _do_modify()
        except HttpError as e:
            logger.error(
                "Failed to remove label", message_id=message_id, label=label_name, error=str(e)
            )
            raise
