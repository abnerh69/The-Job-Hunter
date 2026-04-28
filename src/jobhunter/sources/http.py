import asyncio
import httpx
import structlog
import logging
from typing import Any, Mapping, Dict
from tenacity import (
    stop_after_attempt,
    wait_random_exponential,
    retry_if_exception,
    before_sleep_log,
    RetryCallState,
    AsyncRetrying,
)

__all__ = ["SourceHttpClient", "AsyncRetrying"]

logger = structlog.get_logger(__name__)

USER_AGENT = "jobhunter-eu/0.3 (+https://github.com/Informatica-ASHware/Job-Hunter-EU)"


def is_retryable_exception(exception: BaseException) -> bool:
    """
    Checks if the exception is retryable.

    Args:
        exception: The exception to check.

    Returns:
        bool: True if retryable, False otherwise.
    """
    if isinstance(exception, (httpx.TimeoutException, httpx.ConnectError)):
        return True
    if isinstance(exception, httpx.HTTPStatusError):
        return bool(exception.response.status_code >= 500 or exception.response.status_code == 429)
    return False


class SourceHttpClient:
    """
    HTTP client wrapper for job sources with retry, backoff, and rate limiting.
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        headers: Mapping[str, str] | None = None,
        rate_limit_per_host: int = 2,
    ):
        """
        Initializes the SourceHttpClient.

        Args:
            client: An optional httpx.AsyncClient instance.
            headers: Optional headers to include in all requests.
            rate_limit_per_host: Max concurrent requests per host.
        """
        base_headers = {"User-Agent": USER_AGENT}
        if headers:
            base_headers.update(headers)

        if client:
            # If client is provided, we don't own it and shouldn't close it.
            # Also, we can't easily inject the User-Agent if it's already created,
            # but we assume the caller knows what they are doing.
            self.client = client
            self._own_client = False
        else:
            self.client = httpx.AsyncClient(headers=base_headers)
            self._own_client = True

        self.rate_limit_per_host = rate_limit_per_host
        self._semaphores: Dict[str, asyncio.Semaphore] = {}
        self._semaphores_lock = asyncio.Lock()

    async def _get_semaphore(self, host: str) -> asyncio.Semaphore:
        """Gets or creates a semaphore for the given host."""
        async with self._semaphores_lock:
            if host not in self._semaphores:
                self._semaphores[host] = asyncio.Semaphore(self.rate_limit_per_host)
            return self._semaphores[host]

    async def get(self, url: str, **kwargs: Any) -> httpx.Response:
        """
        Performs a GET request with retries and rate limiting.

        Args:
            url: The URL to request.
            **kwargs: Additional arguments for httpx.AsyncClient.get.

        Returns:
            httpx.Response: The HTTP response.
        """
        return await self._request("GET", url, **kwargs)

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """
        Internal method to perform HTTP requests with retry logic and rate limiting.
        """
        parsed_url = httpx.URL(url)
        host = parsed_url.host or ""
        semaphore = await self._get_semaphore(host)

        # Semaphore acquired outside to satisfy requirement, but retry loop inside.
        # This means 1 concurrent request per host INCLUDING retry/backoff time.
        async with semaphore:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(4),  # 1 original + 3 retries
                wait=wait_random_exponential(multiplier=1, min=1, max=10),
                retry=retry_if_exception(is_retryable_exception),
                before_sleep=before_sleep_log(logger, logging.INFO),
                reraise=True,
            ):
                with attempt:
                    start_time = asyncio.get_event_loop().time()
                    try:
                        response = await self.client.request(method, url, **kwargs)
                        response.raise_for_status()
                        self._log_request(method, url, response, start_time, attempt.retry_state)
                        return response
                    except httpx.HTTPStatusError as exc:
                        if exc.response.status_code == 429:
                            retry_after = exc.response.headers.get("Retry-After")
                            if retry_after:
                                try:
                                    wait_time = float(retry_after)
                                    logger.info(
                                        "429 Too Many Requests, respecting Retry-After",
                                        wait_time=wait_time,
                                    )
                                    await asyncio.sleep(wait_time)
                                except ValueError:
                                    logger.warning(
                                        "Could not parse Retry-After header",
                                        value=retry_after,
                                    )

                        self._log_request(
                            method, url, exc.response, start_time, attempt.retry_state
                        )
                        raise exc
                    except (httpx.TimeoutException, httpx.ConnectError) as exc:
                        self._log_request(
                            method, url, None, start_time, attempt.retry_state, error=str(exc)
                        )
                        raise exc

            # This should not be reached because of reraise=True in AsyncRetrying
            raise RuntimeError("Retry loop finished unexpectedly")

    def _log_request(
        self,
        method: str,
        url: str,
        response: httpx.Response | None,
        start_time: float,
        retry_state: RetryCallState,
        error: str | None = None,
    ) -> None:
        duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        parsed_url = httpx.URL(url)

        log_data = {
            "method": method,
            "host": parsed_url.host,
            "path": parsed_url.path,
            "status_code": response.status_code if response else None,
            "duration_ms": duration_ms,
            "attempt": retry_state.attempt_number,
        }
        if error:
            log_data["error"] = error

        logger.info("HTTP request", **log_data)

    async def close(self) -> None:
        """Closes the underlying httpx.AsyncClient if it was created by this instance."""
        if self._own_client:
            await self.client.aclose()

    async def __aenter__(self) -> "SourceHttpClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()
