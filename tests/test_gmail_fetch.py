from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from gmail_dwd_mcp.gmail_fetch import (
    GmailApiError,
    PermissionDeniedError,
    RateLimitedError,
    ThreadNotFoundError,
    fetch_thread_raw,
)


def _http_error(status: int) -> HttpError:
    resp = MagicMock()
    resp.status = status
    return HttpError(resp, b"error")


def test_fetch_thread_raw_invokes_single_threads_get() -> None:
    service = MagicMock()
    threads_get = MagicMock()
    threads_get.execute.return_value = {"id": "thread-1", "messages": []}
    service.users.return_value.threads.return_value.get.return_value = threads_get

    result = fetch_thread_raw(service, "thread-1")

    service.users.return_value.threads.return_value.get.assert_called_once_with(
        userId="me",
        id="thread-1",
        format="full",
    )
    threads_get.execute.assert_called_once()
    assert result["id"] == "thread-1"


@pytest.mark.parametrize(
    ("status", "expected_type"),
    [
        (404, ThreadNotFoundError),
        (429, RateLimitedError),
        (403, PermissionDeniedError),
        (500, GmailApiError),
    ],
)
def test_fetch_thread_raw_maps_http_errors(status: int, expected_type: type[Exception]) -> None:
    service = MagicMock()
    threads_get = MagicMock()
    threads_get.execute.side_effect = _http_error(status)
    service.users.return_value.threads.return_value.get.return_value = threads_get

    with pytest.raises(expected_type):
        fetch_thread_raw(service, "missing-thread")
