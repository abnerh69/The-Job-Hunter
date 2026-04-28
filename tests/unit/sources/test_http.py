import asyncio
import httpx
import pytest
import time
from typing import Any
from unittest.mock import MagicMock, patch
from jobhunter.sources.http import SourceHttpClient


@pytest.mark.asyncio
async def test_retries_on_500_then_succeeds() -> None:
    responses = [
        httpx.Response(500, content=b"Internal Server Error"),
        httpx.Response(500, content=b"Internal Server Error"),
        httpx.Response(500, content=b"Internal Server Error"),
        httpx.Response(200, content=b"OK"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as client:
        from tenacity import wait_none
        import jobhunter.sources.http

        # Patch AsyncRetrying to use wait_none()
        original_retrying = jobhunter.sources.http.AsyncRetrying

        def mock_retrying(*args: Any, **kwargs: Any) -> Any:
            kwargs["wait"] = wait_none()
            return original_retrying(*args, **kwargs)

        with patch("jobhunter.sources.http.AsyncRetrying", side_effect=mock_retrying):
            response = await client.get("http://example.com")
            assert response.status_code == 200
            assert len(responses) == 0


@pytest.mark.asyncio
async def test_no_retry_on_404() -> None:
    responses = [
        httpx.Response(404, content=b"Not Found"),
        httpx.Response(200, content=b"OK"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    transport = httpx.MockTransport(handler)
    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as client:
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            await client.get("http://example.com")

        assert excinfo.value.response.status_code == 404
        # Should not have retried, so second response (200) should still be there
        assert len(responses) == 1


@pytest.mark.asyncio
async def test_respects_retry_after_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        httpx.Response(429, headers={"Retry-After": "0.1"}, content=b"Too Many Requests"),
        httpx.Response(200, content=b"OK"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return responses.pop(0)

    transport = httpx.MockTransport(handler)

    # Mock asyncio.sleep to verify it's called with the correct value and avoid waiting
    mock_sleep = MagicMock(side_effect=asyncio.sleep)
    monkeypatch.setattr(asyncio, "sleep", mock_sleep)

    async with SourceHttpClient(client=httpx.AsyncClient(transport=transport)) as client:
        from tenacity import wait_none
        import jobhunter.sources.http

        original_retrying = jobhunter.sources.http.AsyncRetrying

        def mock_retrying(*args: Any, **kwargs: Any) -> Any:
            kwargs["wait"] = wait_none()
            return original_retrying(*args, **kwargs)

        with patch("jobhunter.sources.http.AsyncRetrying", side_effect=mock_retrying):
            response = await client.get("http://example.com")
            assert response.status_code == 200
            # Verify asyncio.sleep was called with 0.1 from Retry-After
            mock_sleep.assert_any_call(0.1)


@pytest.mark.asyncio
async def test_rate_limit_throttles_concurrent_requests() -> None:
    # 3 requests, rate limit 2.
    # The first 2 should start immediately.
    # The 3rd should wait for one of them to finish.

    responses_count = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal responses_count
        responses_count += 1
        await asyncio.sleep(0.2)
        return httpx.Response(200, content=b"OK")

    transport = httpx.MockTransport(handler)

    # Rate limit 2
    async with SourceHttpClient(
        client=httpx.AsyncClient(transport=transport), rate_limit_per_host=2
    ) as client:
        start_time = time.perf_counter()
        # Run 3 requests concurrently
        tasks = [
            client.get("http://example.com/1"),
            client.get("http://example.com/2"),
            client.get("http://example.com/3"),
        ]
        await asyncio.gather(*tasks)
        end_time = time.perf_counter()

        duration = end_time - start_time
        # 2 requests should take ~0.2s, then the 3rd should take another ~0.2s.
        # Total duration should be at least 0.4s.
        assert duration >= 0.35  # Allow some buffer
        assert responses_count == 3
