"""Gmail API fetch primitives for thread hydration."""

from __future__ import annotations

import threading
from concurrent.futures import Executor, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from googleapiclient.errors import HttpError

from gmail_dwd_mcp.config import (
    gmail_api_num_retries_from_env,
    gmail_hydrate_max_concurrency_from_env,
)
from gmail_dwd_mcp.rate_limiter import THREADS_GET_QUOTA_UNITS, QuotaRateLimiter

_fetch_executor: ThreadPoolExecutor | None = None
_fetch_executor_lock = threading.Lock()


def get_thread_fetch_executor(*, max_workers: int | None = None) -> ThreadPoolExecutor:
    """Return the process-wide batch fetch executor (lazy, thread-safe)."""
    global _fetch_executor
    with _fetch_executor_lock:
        if _fetch_executor is None:
            workers = (
                max_workers
                if max_workers is not None
                else gmail_hydrate_max_concurrency_from_env()
            )
            _fetch_executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix="gmail-thread-fetch",
            )
        return _fetch_executor


def shutdown_thread_fetch_executor(*, wait: bool = True) -> None:
    """Shut down the process-wide batch fetch executor (idempotent)."""
    global _fetch_executor
    with _fetch_executor_lock:
        if _fetch_executor is not None:
            _fetch_executor.shutdown(wait=wait)
            _fetch_executor = None


class GmailApiError(Exception):
    """Gmail API request failed."""


class ThreadNotFoundError(GmailApiError):
    """Thread id not found (HTTP 404)."""


class RateLimitedError(GmailApiError):
    """Gmail rate limit exceeded (HTTP 429)."""


class PermissionDeniedError(GmailApiError):
    """Caller lacks permission for the mailbox or thread (HTTP 403)."""


@dataclass(frozen=True)
class ThreadFetchResult:
    """Per-thread outcome from :func:`fetch_threads_raw`."""

    raw: dict[str, Any] | None = None
    error: GmailApiError | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


def fetch_thread_raw(
    service: Any,
    thread_id: str,
    *,
    email: str | None = None,
    rate_limiter: QuotaRateLimiter | None = None,
    num_retries: int | None = None,
) -> dict[str, Any]:
    """Fetch a full Gmail thread in one ``threads.get`` call (format=full).

    When ``rate_limiter`` is set, ``email`` must be provided and
    :data:`~gmail_dwd_mcp.rate_limiter.THREADS_GET_QUOTA_UNITS` are reserved first.

    Retries use google-api-python-client's built-in backoff (429, 5xx, rate-limit 403).
    ``num_retries`` defaults to ``GMAIL_API_NUM_RETRIES`` (3); 0 means one attempt.
    """
    if rate_limiter is not None:
        if not email:
            raise ValueError("email is required when rate_limiter is provided")
        rate_limiter.acquire(email, THREADS_GET_QUOTA_UNITS)
    retries = gmail_api_num_retries_from_env() if num_retries is None else num_retries
    try:
        return (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute(num_retries=retries)
        )
    except HttpError as err:
        raise _map_http_error(err, thread_id=thread_id) from err


def _map_http_error(err: HttpError, *, thread_id: str) -> GmailApiError:
    status = err.resp.status if err.resp is not None else err.status_code
    if status == 404:
        return ThreadNotFoundError(f"Thread not found: {thread_id}")
    if status == 429:
        return RateLimitedError("Gmail API rate limit exceeded")
    if status == 403:
        return PermissionDeniedError("Gmail API permission denied")
    return GmailApiError(f"Gmail API error ({status}): {err}")


def fetch_threads_raw(
    service: Any,
    email: str,
    thread_ids: list[str],
    *,
    concurrency: int | None = None,
    rate_limiter: QuotaRateLimiter | None = None,
    num_retries: int | None = None,
    executor: Executor | None = None,
) -> dict[str, ThreadFetchResult]:
    """Fetch multiple threads in parallel with partial success.

    Duplicate ``thread_ids`` are deduped (one ``threads.get`` per unique id).
    Callers preserve input order when assembling downstream results.

    Uses a process-wide :func:`get_thread_fetch_executor` by default; pass
    ``executor`` to override (e.g. tests). Per-batch ``concurrency`` caps
    in-flight fetches via a semaphore, not by creating a new thread pool.
    """
    unique_ids = list(dict.fromkeys(thread_ids))
    if not unique_ids:
        return {}

    max_workers_cap = (
        gmail_hydrate_max_concurrency_from_env()
        if concurrency is None
        else max(concurrency, 1)
    )
    max_in_flight = min(len(unique_ids), max_workers_cap)
    pool = executor if executor is not None else get_thread_fetch_executor()

    results: dict[str, ThreadFetchResult] = {}
    in_flight = threading.Semaphore(max_in_flight)

    def _fetch_one(thread_id: str) -> tuple[str, ThreadFetchResult]:
        with in_flight:
            try:
                raw = fetch_thread_raw(
                    service,
                    thread_id,
                    email=email,
                    rate_limiter=rate_limiter,
                    num_retries=num_retries,
                )
                return thread_id, ThreadFetchResult(raw=raw)
            except GmailApiError as err:
                return thread_id, ThreadFetchResult(error=err)

    futures = [pool.submit(_fetch_one, thread_id) for thread_id in unique_ids]
    for future in as_completed(futures):
        thread_id, result = future.result()
        results[thread_id] = result

    return results
