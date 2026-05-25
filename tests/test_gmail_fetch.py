from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError
from googleapiclient.http import HttpRequest

from gmail_dwd_mcp.config import (
    DEFAULT_GMAIL_API_NUM_RETRIES,
    Settings,
    gmail_api_num_retries_from_env,
)
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
    threads_get.execute.assert_called_once_with(num_retries=DEFAULT_GMAIL_API_NUM_RETRIES)
    assert result["id"] == "thread-1"


def test_fetch_thread_raw_passes_num_retries_override() -> None:
    service = MagicMock()
    threads_get = MagicMock()
    threads_get.execute.return_value = {"id": "thread-1", "messages": []}
    service.users.return_value.threads.return_value.get.return_value = threads_get

    fetch_thread_raw(service, "thread-1", num_retries=0)

    threads_get.execute.assert_called_once_with(num_retries=0)


def _threads_get_request(http: MagicMock) -> HttpRequest:
    request = HttpRequest(
        http=http,
        postproc=lambda _resp, content: json.loads(content.decode()),
        uri="https://gmail.googleapis.com/gmail/v1/users/me/threads/thread-1",
        method="GET",
    )
    request._sleep = lambda _seconds: None
    request._rand = lambda: 0.0
    return request


def test_fetch_thread_raw_retries_429_then_succeeds() -> None:
    calls: list[int] = []

    def fake_request(_uri: str, _method: str, *args, **kwargs):
        calls.append(1)
        resp = MagicMock()
        if len(calls) == 1:
            resp.status = 429
            return resp, b"rate limited"
        resp.status = 200
        return resp, b'{"id":"thread-1","messages":[]}'

    http = MagicMock()
    http.request = fake_request
    service = MagicMock()
    service.users.return_value.threads.return_value.get.return_value = _threads_get_request(http)

    result = fetch_thread_raw(service, "thread-1", num_retries=2)

    assert len(calls) == 2
    assert result["id"] == "thread-1"


@pytest.mark.parametrize("num_retries", [0, 3])
def test_fetch_thread_raw_404_does_not_retry(num_retries: int) -> None:
    calls: list[int] = []

    def fake_request(_uri: str, _method: str, *args, **kwargs):
        calls.append(1)
        resp = MagicMock()
        resp.status = 404
        return resp, b"not found"

    http = MagicMock()
    http.request = fake_request
    service = MagicMock()
    service.users.return_value.threads.return_value.get.return_value = _threads_get_request(http)

    with pytest.raises(ThreadNotFoundError):
        fetch_thread_raw(service, "missing-thread", num_retries=num_retries)

    assert len(calls) == 1


def test_gmail_api_num_retries_from_env_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GMAIL_API_NUM_RETRIES", raising=False)
    assert gmail_api_num_retries_from_env() == DEFAULT_GMAIL_API_NUM_RETRIES


def test_gmail_api_num_retries_from_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GMAIL_API_NUM_RETRIES", "5")
    assert gmail_api_num_retries_from_env() == 5


def test_settings_gmail_api_num_retries_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_WIF_CREDENTIAL_CONFIG_SSM_PARAMETER", "/test/wif")
    monkeypatch.setenv("GMAIL_API_NUM_RETRIES", "0")
    settings = Settings.from_env()
    assert settings.gmail_api_num_retries == 0


def test_settings_gmail_hydrate_max_batch_size_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_WIF_CREDENTIAL_CONFIG_SSM_PARAMETER", "/test/wif")
    monkeypatch.setenv("GMAIL_HYDRATE_MAX_BATCH_SIZE", "15")
    settings = Settings.from_env()
    assert settings.gmail_hydrate_max_batch_size == 15


def test_settings_gmail_hydrate_max_concurrency_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GCP_WIF_CREDENTIAL_CONFIG_SSM_PARAMETER", "/test/wif")
    monkeypatch.setenv("GMAIL_HYDRATE_MAX_CONCURRENCY", "8")
    settings = Settings.from_env()
    assert settings.gmail_hydrate_max_concurrency == 8


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
        fetch_thread_raw(service, "missing-thread", num_retries=0)
