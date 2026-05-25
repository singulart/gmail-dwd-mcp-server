"""Quota-aware token-bucket rate limiter for Gmail API calls (per impersonated user)."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_UNITS_PER_SECOND = 200
# Per https://developers.google.com/gmail/api/reference/quota (threads.get row).
THREADS_GET_QUOTA_UNITS = 40


class QuotaRateLimiterError(Exception):
    """Rate limiter configuration or progress failure."""


@dataclass
class _BucketState:
    tokens: float
    last_refill: float


class QuotaRateLimiter:
    """Token bucket keyed by impersonated email; ``acquire`` blocks until budget exists."""

    def __init__(
        self,
        units_per_second: float = DEFAULT_UNITS_PER_SECOND,
        *,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        if units_per_second <= 0:
            raise ValueError("units_per_second must be positive")
        self._units_per_second = float(units_per_second)
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._buckets: dict[str, _BucketState] = {}
        self._lock = threading.Lock()

    def acquire(self, email: str, units: int) -> None:
        """Block until ``units`` quota are available for ``email`` (at most one wait)."""
        if units <= 0:
            return
        if units > self._units_per_second:
            raise ValueError(
                f"cannot acquire {units} units in one request; "
                f"maximum per-second budget is {self._units_per_second}"
            )

        wait_seconds = self._reserve(email, units)
        if wait_seconds <= 0:
            return

        if not math.isfinite(wait_seconds) or wait_seconds <= 0:
            raise QuotaRateLimiterError("invalid wait interval from rate limiter")

        self._sleep(wait_seconds)

        if self._reserve(email, units) > 0:
            raise QuotaRateLimiterError(
                "quota rate limiter made no progress after sleep; "
                "ensure the clock advances and units do not exceed the per-second budget"
            )

    def _reserve(self, email: str, units: int) -> float:
        with self._lock:
            now = self._clock()
            bucket = self._buckets.get(email)
            if bucket is None:
                bucket = _BucketState(tokens=self._units_per_second, last_refill=now)
                self._buckets[email] = bucket

            elapsed = max(0.0, now - bucket.last_refill)
            bucket.tokens = min(
                self._units_per_second,
                bucket.tokens + elapsed * self._units_per_second,
            )
            bucket.last_refill = now

            if bucket.tokens >= units:
                bucket.tokens -= units
                return 0.0

            deficit = units - bucket.tokens
            return deficit / self._units_per_second
