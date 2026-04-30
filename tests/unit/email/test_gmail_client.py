import base64
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from googleapiclient.errors import HttpError

from jobhunter.email.gmail_client import GmailClient
from jobhunter.email.schemas import GmailMessage, GmailMessageDetail, Label


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.OAUTH_ENCRYPTION_KEY.get_secret_value.return_value = "JWlfIfjk63NDm5PvazwGt4HraiiLWk6kGFtpJ0sRTCc="  # Valid Fernet key
    settings.GMAIL_CLIENT_ID.get_secret_value.return_value = "client_id"
    settings.GMAIL_CLIENT_SECRET.get_secret_value.return_value = "client_secret"
    return settings


@pytest.fixture
def mock_token_repo():
    repo = MagicMock()
    token = MagicMock()
    token.access_token = "encrypted_access"
    token.refresh_token = "encrypted_refresh"
    # Set to future so it's not expired in get_service_initialization test
    token.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    token.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    repo.get_token.return_value = token
    return repo


@pytest.fixture
def gmail_client(mock_token_repo, mock_settings):
    # Completely mock decrypt and encrypt at the module level where they are used
    with patch("jobhunter.email.gmail_client.decrypt", side_effect=lambda x, k: x.replace("encrypted_", "")):
        with patch("jobhunter.email.gmail_client.encrypt", side_effect=lambda x, k: f"encrypted_{x}"):
            client = GmailClient(mock_token_repo, "test@example.com", mock_settings)
            yield client


@pytest.mark.asyncio
async def test_get_service_initialization(gmail_client, mock_token_repo):
    with patch("jobhunter.email.gmail_client.build") as mock_build:
        service = await gmail_client._get_service()
        assert service is not None
        mock_build.assert_called_once()
        mock_token_repo.get_token.assert_called_with("gmail", "test@example.com")


def test_parse_message_multipart(gmail_client):
    raw_msg = {
        "id": "msg123",
        "threadId": "thread456",
        "snippet": "Hello world",
        "internalDate": "1672531200000",  # 2023-01-01
        "labelIds": ["INBOX", "UNREAD"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test Subject"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64decode(data) if (data := "VGV4dCBib2R5") else ""}, # "Text body"
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": base64.urlsafe_b64encode(b"<html>HTML body</html>").decode()},
                },
            ],
        },
    }
    # Wait, base64.urlsafe_b64decode("VGV4dCBib2R5") is b'Text body'
    # Gmail API returns base64url encoded strings.

    raw_msg["payload"]["parts"][0]["body"]["data"] = base64.urlsafe_b64encode(b"Text body").decode()

    parsed = gmail_client._parse_message(raw_msg)
    assert parsed["id"] == "msg123"
    assert parsed["from_email"] == "sender@example.com"
    assert parsed["body_text"] == "Text body"
    assert parsed["body_html"] == "<html>HTML body</html>"
    assert isinstance(parsed["received_at"], datetime)


@pytest.mark.asyncio
async def test_list_messages(gmail_client):
    mock_service = MagicMock()
    gmail_client._service = mock_service

    mock_list = mock_service.users().messages().list().execute
    mock_list.return_value = {"messages": [{"id": "msg1"}]}

    mock_get = mock_service.users().messages().get().execute
    mock_get.return_value = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1672531200000",
        "payload": {"headers": [{"name": "From", "value": "a@b.com"}]},
    }

    messages = await gmail_client.list_messages("query")
    assert len(messages) == 1
    assert isinstance(messages[0], GmailMessage)
    assert messages[0].id == "msg1"


@pytest.mark.asyncio
async def test_get_message_detail(gmail_client):
    mock_service = MagicMock()
    gmail_client._service = mock_service

    mock_get = mock_service.users().messages().get().execute
    mock_get.return_value = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1672531200000",
        "payload": {
            "mimeType": "text/plain",
            "body": {"data": base64.urlsafe_b64encode(b"Detailed body").decode()},
            "headers": [{"name": "From", "value": "a@b.com"}],
        },
    }

    message = await gmail_client.get_message("msg1")
    assert isinstance(message, GmailMessageDetail)
    assert message.body_text == "Detailed body"


@pytest.mark.asyncio
async def test_retry_on_401(gmail_client):
    mock_service = MagicMock()
    gmail_client._service = mock_service

    mock_request = MagicMock()
    # First call fails with 401, second succeeds
    mock_resp = MagicMock()
    mock_resp.status = 401
    mock_request.execute.side_effect = [
        HttpError(resp=mock_resp, content=b"Unauthorized"),
        {"success": True},
    ]

    # Mock _get_service to not actually build a real service again
    gmail_client._get_service = AsyncMock(return_value=mock_service)

    result = await gmail_client._execute_with_refresh(mock_request)
    assert result == {"success": True}
    assert gmail_client._get_service.call_count == 1


@pytest.mark.asyncio
async def test_rate_limiting(gmail_client):
    import time

    mock_service = MagicMock()
    gmail_client._service = mock_service
    mock_request = MagicMock()
    mock_request.execute.return_value = {}

    start_time = time.time()
    await gmail_client._execute_with_refresh(mock_request)
    await gmail_client._execute_with_refresh(mock_request)
    end_time = time.time()

    # Two requests with 200ms delay each -> should take at least 400ms
    assert end_time - start_time >= 0.4
