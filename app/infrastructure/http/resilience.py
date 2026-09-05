import asyncio
import os
import random
import time
from typing import Any, Awaitable, Callable, Dict, TypeVar

import httpx

T = TypeVar("T")

PROVIDER_LIMITS = {
    "sec": 5,
    "market_data": 10,
    "web_search": 5,
}
RETRYABLE_STATUS = {429, 502, 503}
NON_RETRYABLE_STATUS = {400, 401, 403, 404}


class NonRetryableError(Exception):
    """Fatal provider error that must not be retried (400/404/invalid ticker)."""


class CircuitOpenError(Exception):
    """Provider circuit is open due to repeated failures."""


class ProviderRateLimiter:
    def __init__(self, limits: Dict[str, int] | None = None) -> None:
        self._semaphores = {
            name: asyncio.Semaphore(limit)
            for name, limit in (limits or PROVIDER_LIMITS).items()
        }

    def semaphore(self, provider_name: str) -> asyncio.Semaphore:
        if provider_name not in self._semaphores:
            self._semaphores[provider_name] = asyncio.Semaphore(5)
        return self._semaphores[provider_name]


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, reset_seconds: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_seconds = reset_seconds
        self._failures: Dict[str, int] = {}
        self._opened_at: Dict[str, float] = {}

    def allow(self, provider_name: str) -> bool:
        opened = self._opened_at.get(provider_name)
        if opened is None:
            return True
        if time.monotonic() - opened >= self.reset_seconds:
            self._opened_at.pop(provider_name, None)
            self._failures[provider_name] = 0
            return True
        return False

    def record_success(self, provider_name: str) -> None:
        self._failures[provider_name] = 0
        self._opened_at.pop(provider_name, None)

    def record_failure(self, provider_name: str) -> None:
        self._failures[provider_name] = self._failures.get(provider_name, 0) + 1
        if self._failures[provider_name] >= self.failure_threshold:
            self._opened_at[provider_name] = time.monotonic()


rate_limiter = ProviderRateLimiter()
circuit_breaker = CircuitBreaker()


def _backoff_seconds(attempt: int) -> float:
    base = float(os.getenv("RESILIENCE_BACKOFF_BASE", "0.05"))
    return (base * (2 ** (attempt - 1))) + random.random() * base


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, (asyncio.TimeoutError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    if isinstance(exc, httpx.TransportError):
        return True
    return False


def _is_non_retryable(exc: BaseException) -> bool:
    if isinstance(exc, NonRetryableError):
        return True
    if isinstance(exc, ValueError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in NON_RETRYABLE_STATUS
    return False


async def resilient_request(
    provider_name: str,
    coroutine_func: Callable[..., Awaitable[T]],
    *args: Any,
    timeout: float = 5.0,
    max_attempts: int = 3,
    **kwargs: Any,
) -> T:
    """Acquire a per-provider semaphore, apply timeout, and retry transient errors."""
    if not circuit_breaker.allow(provider_name):
        raise CircuitOpenError(f"Circuit open for provider '{provider_name}'.")

    last_error: BaseException | None = None
    attempts = max(1, max_attempts)
    for attempt in range(1, attempts + 1):
        async with rate_limiter.semaphore(provider_name):
            try:
                result = await asyncio.wait_for(coroutine_func(*args, **kwargs), timeout=timeout)
                circuit_breaker.record_success(provider_name)
                return result
            except Exception as exc:
                last_error = exc
                if _is_non_retryable(exc):
                    circuit_breaker.record_failure(provider_name)
                    raise NonRetryableError(str(exc)) from exc
                if not _is_retryable(exc) or attempt == attempts:
                    circuit_breaker.record_failure(provider_name)
                    raise
        await asyncio.sleep(_backoff_seconds(attempt))

    assert last_error is not None
    raise last_error
