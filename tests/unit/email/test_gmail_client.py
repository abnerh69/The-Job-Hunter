from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Any, AsyncGenerator

import pytest
from googleapiclient.errors import HttpError  # type: ignore

from jobhunter.email.gmail_client import GmailClient


@pytest.fixture
def mock_settings() -> MagicMock:
    settings = MagicMock()
    settings.OAUTH_ENCRYPTION_KEY.get_secret_value.return_value = (
        "JWlfIfjk63NDm5PvazwGt4HraiiLWk6kGFtpJ0sRTCc="
    )
    settings.GMAIL_CLIENT_ID.get_secret_value.return_value = "client_id"
    settings.GMAIL_CLIENT_SECRET.get_secret_value.return_value = "client_secret"
    return settings


@pytest.fixture
def mock_token_repo() -> MagicMock:
    repo = MagicMock()
    token = MagicMock()
    token.access_token = "encrypted_access"
    token.refresh_token = "encrypted_refresh"
    token.expires_at = datetime(2099, 1, 1, tzinfo=timezone.utc)
    token.scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    repo.get_token.return_value = token
    return repo


@pytest.fixture
async def gmail_client(
    mock_token_repo: MagicMock, mock_settings: MagicMock
) -> AsyncGenerator[GmailClient, None]:
    # Completely mock decrypt and encrypt at the module level where they are used
    with patch(
        "jobhunter.email.gmail_client.decrypt", side_effect=lambda x, k: x.replace("encrypted_", "")
    ):
        with patch(
            "jobhunter.email.gmail_client.encrypt", side_effect=lambda x, k: f"encrypted_{x}"
        ):
            client = GmailClient(mock_token_repo, "test@example.com", mock_settings)
            yield client


@pytest.mark.asyncio
async def test_get_service_initialization(
    gmail_client: GmailClient, mock_token_repo: MagicMock
) -> None:
    with patch("jobhunter.email.gmail_client.build") as mock_build:
        service = await gmail_client._get_service()
        assert service is not None
        mock_build.assert_called_once()
        mock_token_repo.get_token.assert_called_with("gmail", "test@example.com")


def test_base64_decode_padding(gmail_client: GmailClient) -> None:
    # "abc" -> "YWJj", no padding needed
    assert gmail_client._base64_decode("YWJj") == "abc"
    # "abcd" -> "YWJjZA", needs padding "=="
    assert gmail_client._base64_decode("YWJjZA") == "abcd"
    # "abcde" -> "YWJjZGU", needs padding "="
    assert gmail_client._base64_decode("YWJjZGU") == "abcde"


def test_parse_message_multipart(gmail_client: GmailClient) -> None:
    raw_msg = {
        "id": "msg123",
        "threadId": "thread456",
        "snippet": "Hello world",
        "internalDate": "1672531200000",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test Subject"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": "VGV4dCBib2R5"},  # "Text body" (no padding needed)
                },
            ],
        },
    }
    parsed = gmail_client._parse_message(raw_msg)
    assert parsed["from_email"] == "sender@example.com"
    assert parsed["body_text"] == "Text body"


@pytest.mark.asyncio
async def test_list_messages_with_headers(gmail_client: GmailClient) -> None:
    mock_service = MagicMock()
    gmail_client._service = mock_service

    mock_list = mock_service.users().messages().list().execute
    mock_list.return_value = {"messages": [{"id": "msg1"}]}

    mock_get = mock_service.users().messages().get().execute
    mock_get.return_value = {
        "id": "msg1",
        "threadId": "thread1",
        "internalDate": "1672531200000",
        "payload": {
            "headers": [
                {"name": "From", "value": "recruiter@company.com"},
                {"name": "Subject", "value": "Job Offer"},
            ]
        },
    }

    messages = await gmail_client.list_messages("query")
    assert len(messages) == 1
    assert messages[0].from_email == "recruiter@company.com"
    assert messages[0].subject == "Job Offer"


@pytest.mark.asyncio
async def test_retry_on_401_with_factory(gmail_client: GmailClient) -> None:
    mock_service = MagicMock()
    gmail_client._service = mock_service

    mock_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status = 401
    # 401 then success
    mock_request.execute.side_effect = [
        HttpError(resp=mock_resp, content=b"Unauthorized"),
        {"success": True},
    ]

    # Factory must be an async function returning a mock request
    async def factory() -> Any:
        return mock_request

    factory_spy = AsyncMock(side_effect=factory)

    # Mock _get_service to reset _service
    async def mock_get_service_side_effect() -> MagicMock:
        gmail_client._service = mock_service
        return mock_service

    with patch.object(gmail_client, "_get_service", side_effect=mock_get_service_side_effect):
        result = await gmail_client._execute_with_retry(factory_spy)
        assert result == {"success": True}
        assert factory_spy.call_count == 2


@pytest.mark.asyncio
async def test_rate_limiting(gmail_client: GmailClient) -> None:
    import time

    gmail_client._service = MagicMock()
    mock_request = MagicMock()
    mock_request.execute.return_value = {}

    async def factory() -> Any:
        return mock_request

    start_time = time.time()
    await gmail_client._execute_with_retry(factory)
    await gmail_client._execute_with_retry(factory)
    end_time = time.time()

    assert end_time - start_time >= 0.4
