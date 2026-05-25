"""End-to-end thread hydration: Gmail fetch + normalization (TASK-C5)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from gmail_dwd_mcp.gmail_fetch import (
    GmailApiError,
    PermissionDeniedError,
    RateLimitedError,
    ThreadFetchResult,
    ThreadNotFoundError,
    fetch_threads_raw,
)
from gmail_dwd_mcp.hydration import (
    HydrateError,
    HydrateMeta,
    HydrateResult,
    HydratedThread,
    HydrationOptions,
)
from gmail_dwd_mcp.hydration_logging import log_hydrate_complete, log_hydrate_thread_errors
from gmail_dwd_mcp.normalize import normalize_thread
from gmail_dwd_mcp.rate_limiter import THREADS_GET_QUOTA_UNITS, QuotaRateLimiter
from gmail_dwd_mcp.size_caps import TRUNCATION_MARKER

GetService = Callable[[str], Any]


def _error_code(err: GmailApiError) -> str:
    if isinstance(err, ThreadNotFoundError):
        return "NOT_FOUND"
    if isinstance(err, RateLimitedError):
        return "RATE_LIMITED"
    if isinstance(err, PermissionDeniedError):
        return "PERMISSION_DENIED"
    return "GMAIL_API_ERROR"


def _thread_char_count(thread: HydratedThread) -> int:
    return sum(len(msg.body) for msg in thread.messages)


def _thread_truncated(thread: HydratedThread) -> bool:
    return any(
        msg.omitted_from_thread or TRUNCATION_MARKER in msg.body for msg in thread.messages
    )


def _apply_global_char_budget(
    threads: list[HydratedThread],
    options: HydrationOptions,
) -> tuple[list[HydratedThread], bool]:
    """TASK-B6 global cap; no-op until B6 is implemented."""
    _ = threads, options
    return threads, False


class ThreadHydrator:
    """Single entry point for get_thread / get_threads hydrate paths."""

    def __init__(
        self,
        *,
        get_service: GetService,
        rate_limiter: QuotaRateLimiter | None = None,
    ) -> None:
        self._get_service = get_service
        self._rate_limiter = rate_limiter

    def hydrate(
        self,
        email: str,
        thread_ids: list[str],
        options: HydrationOptions | None = None,
    ) -> HydrateResult:
        started = time.monotonic()
        opts = options or HydrationOptions()
        ordered_unique = list(dict.fromkeys(thread_ids))
        if not ordered_unique:
            result = HydrateResult(
                meta=HydrateMeta(
                    requested_count=len(thread_ids),
                    success_count=0,
                    error_count=0,
                )
            )
            log_hydrate_complete(
                duration_ms=int((time.monotonic() - started) * 1000),
                result=result,
            )
            return result

        service = self._get_service(email)
        fetch_results = fetch_threads_raw(
            service,
            email,
            ordered_unique,
            rate_limiter=self._rate_limiter,
        )

        threads: list[HydratedThread] = []
        errors: list[HydrateError] = []

        for thread_id in ordered_unique:
            result = fetch_results[thread_id]
            if result.ok and result.raw is not None:
                threads.append(normalize_thread(result.raw, opts))
            else:
                err = result.error or GmailApiError("Unknown fetch error")
                errors.append(
                    HydrateError(
                        thread_id=thread_id,
                        message=str(err),
                        code=_error_code(err),
                    )
                )

        threads, global_truncated = _apply_global_char_budget(threads, opts)
        truncated = global_truncated or any(_thread_truncated(t) for t in threads)

        api_calls = len(ordered_unique)
        result = HydrateResult(
            threads=threads,
            errors=errors,
            meta=HydrateMeta(
                requested_count=len(thread_ids),
                success_count=len(threads),
                error_count=len(errors),
                gmail_api_calls=api_calls,
                quota_units_estimated=api_calls * THREADS_GET_QUOTA_UNITS,
                total_chars=sum(_thread_char_count(t) for t in threads),
                truncated=truncated,
            ),
        )
        log_hydrate_thread_errors(result)
        log_hydrate_complete(
            duration_ms=int((time.monotonic() - started) * 1000),
            result=result,
        )
        return result
