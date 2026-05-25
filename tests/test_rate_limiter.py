from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from gmail_dwd_mcp.gmail_fetch import THREADS_GET_QUOTA_UNITS, fetch_thread_raw
from gmail_dwd_mcp.rate_limiter import (
    DEFAULT_UNITS_PER_SECOND,
    QuotaRateLimiter,
    QuotaRateLimiterError,
)
from unittest.mock import MagicMock


class FakeClock:
    def __init__(self) -> None:
        self._now = 0.0

    def monotonic(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


def test_acquire_allows_burst_then_throttles_with_fake_clock() -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    limiter = QuotaRateLimiter(
        100,
        clock=clock.monotonic,
        sleep=lambda s: (sleeps.append(s), clock.advance(s)),
    )

    for _ in range(10):
        limiter.acquire("user@example.com", 10)

    assert sleeps == []
    assert clock.monotonic() == 0.0

    limiter.acquire("user@example.com", 10)
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.1)


def test_buckets_are_independent_per_email() -> None:
    clock = FakeClock()
    sleeps: list[float] = []

    limiter = QuotaRateLimiter(
        50,
        clock=clock.monotonic,
        sleep=lambda s: (sleeps.append(s), clock.advance(s)),
    )

    limiter.acquire("a@example.com", 50)
    limiter.acquire("b@example.com", 50)
    assert sleeps == []


def test_concurrent_acquire_is_thread_safe() -> None:
    limiter = QuotaRateLimiter(500)
    errors: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            limiter.acquire("shared@example.com", 10)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(worker) for _ in range(32)]
        for future in as_completed(futures):
            future.result(timeout=10)

    assert errors == []


def test_fetch_thread_raw_reserves_threads_get_units() -> None:
    clock = FakeClock()
    sleeps: list[float] = []
    limiter = QuotaRateLimiter(
        100,
        clock=clock.monotonic,
        sleep=lambda s: (sleeps.append(s), clock.advance(s)),
    )

    service = MagicMock()
    threads_get = MagicMock()
    threads_get.execute.return_value = {"id": "t1", "messages": []}
    service.users.return_value.threads.return_value.get.return_value = threads_get

    fetch_thread_raw(
        service,
        "t1",
        email="user@example.com",
        rate_limiter=limiter,
    )
    fetch_thread_raw(
        service,
        "t2",
        email="user@example.com",
        rate_limiter=limiter,
    )
    assert sleeps == []

    fetch_thread_raw(
        service,
        "t3",
        email="user@example.com",
        rate_limiter=limiter,
    )
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.2)

    assert service.users.return_value.threads.return_value.get.call_count == 3


def test_fetch_thread_raw_requires_email_with_limiter() -> None:
    with pytest.raises(ValueError, match="email"):
        fetch_thread_raw(MagicMock(), "t1", rate_limiter=QuotaRateLimiter())


def test_threads_get_quota_units_constant() -> None:
    assert THREADS_GET_QUOTA_UNITS == 40
    assert DEFAULT_UNITS_PER_SECOND == 200


def test_acquire_rejects_units_above_per_second_budget() -> None:
    limiter = QuotaRateLimiter(100)
    with pytest.raises(ValueError, match="cannot acquire"):
        limiter.acquire("user@example.com", 101)


def test_acquire_raises_when_clock_does_not_advance() -> None:
    clock = FakeClock()
    limiter = QuotaRateLimiter(
        100,
        clock=clock.monotonic,
        sleep=lambda _seconds: None,
    )
    for _ in range(10):
        limiter.acquire("user@example.com", 10)

    with pytest.raises(QuotaRateLimiterError, match="no progress"):
        limiter.acquire("user@example.com", 10)
