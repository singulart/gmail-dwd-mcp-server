"""Gmail API fetch primitives for thread hydration."""

from __future__ import annotations

from typing import Any

from googleapiclient.errors import HttpError


class GmailApiError(Exception):
    """Gmail API request failed."""


class ThreadNotFoundError(GmailApiError):
    """Thread id not found (HTTP 404)."""


class RateLimitedError(GmailApiError):
    """Gmail rate limit exceeded (HTTP 429)."""


class PermissionDeniedError(GmailApiError):
    """Caller lacks permission for the mailbox or thread (HTTP 403)."""


def fetch_thread_raw(service: Any, thread_id: str) -> dict[str, Any]:
    """Fetch a full Gmail thread in one ``threads.get`` call (format=full)."""
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
