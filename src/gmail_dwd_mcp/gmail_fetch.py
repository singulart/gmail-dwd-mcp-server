"""Gmail API fetch primitives for thread hydration."""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError

from gmail_dwd_mcp.rate_limiter import THREADS_GET_QUOTA_UNITS, QuotaRateLimiter


class GmailApiError(Exception):
    """Gmail API request failed."""


class ThreadNotFoundError(GmailApiError):
    """Thread id not found (HTTP 404)."""


class RateLimitedError(GmailApiError):
    """Gmail rate limit exceeded (HTTP 429)."""


class PermissionDeniedError(GmailApiError):
    """Caller lacks permission for the mailbox or thread (HTTP 403)."""


def fetch_thread_raw(
    service: Any,
    thread_id: str,
    *,
    email: str | None = None,
    rate_limiter: QuotaRateLimiter | None = None,
) -> dict[str, Any]:
    """Fetch a full Gmail thread in one ``threads.get`` call (format=full).

    When ``rate_limiter`` is set, ``email`` must be provided and
    :data:`~gmail_dwd_mcp.rate_limiter.THREADS_GET_QUOTA_UNITS` are reserved first.
    """
    if rate_limiter is not None:
        if not email:
            raise ValueError("email is required when rate_limiter is provided")
        rate_limiter.acquire(email, THREADS_GET_QUOTA_UNITS)
    try:
        return (
            service.users()
            .threads()
            .get(userId="me", id=thread_id, format="full")
            .execute()
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
