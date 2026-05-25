from __future__ import annotations

from unittest.mock import MagicMock, patch

from gmail_dwd_mcp.gmail_fetch import (
    PermissionDeniedError,
    RateLimitedError,
    ThreadFetchResult,
    ThreadNotFoundError,
)
from gmail_dwd_mcp.hydration import HydrationOptions, hydration_to_json
from gmail_dwd_mcp.thread_hydrator import ThreadHydrator
from gmail_dwd_mcp.rate_limiter import THREADS_GET_QUOTA_UNITS
from tests.fixture_loader import b64_text, load_payload_fixture, load_thread_fixture


def _single_message_thread(fixture_name: str, *, thread_id: str) -> dict:
    return {
        "id": thread_id,
        "messages": [
            {
                "id": "msg-1",
                "snippet": "snippet",
                "payload": load_payload_fixture(fixture_name),
            }
        ],
    }


def _hydrator() -> ThreadHydrator:
    return ThreadHydrator(get_service=lambda _email: MagicMock())


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_success_normalizes_fixture(mock_fetch: MagicMock) -> None:
    raw = _single_message_thread("plain_only.py", thread_id="thread-1")
    mock_fetch.return_value = {"thread-1": ThreadFetchResult(raw=raw)}

    result = _hydrator().hydrate("user@example.com", ["thread-1"])

    assert len(result.threads) == 1
    assert result.threads[0].id == "thread-1"
    assert result.threads[0].messages[0].body == "Hello, world!"
    assert result.errors == []
    assert result.meta.requested_count == 1
    assert result.meta.success_count == 1
    assert result.meta.error_count == 0
    assert result.meta.gmail_api_calls == 1
    assert result.meta.quota_units_estimated == THREADS_GET_QUOTA_UNITS
    assert result.meta.total_chars == len("Hello, world!")
    assert result.meta.truncated is False


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_strips_quoted_content(mock_fetch: MagicMock) -> None:
    raw = _single_message_thread("gmail_quote.py", thread_id="thread-q")
    mock_fetch.return_value = {"thread-q": ThreadFetchResult(raw=raw)}

    result = _hydrator().hydrate(
        "user@example.com",
        ["thread-q"],
        HydrationOptions(strip_quoted_content=True),
    )

    assert result.threads[0].messages[0].body == "Thanks for the update."


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_partial_success(mock_fetch: MagicMock) -> None:
    good = _single_message_thread("plain_only.py", thread_id="good")
    mock_fetch.return_value = {
        "good": ThreadFetchResult(raw=good),
        "bad": ThreadFetchResult(error=ThreadNotFoundError("Thread not found: bad")),
    }

    result = _hydrator().hydrate("user@example.com", ["good", "bad"])

    assert len(result.threads) == 1
    assert result.threads[0].id == "good"
    assert len(result.errors) == 1
    assert result.errors[0].thread_id == "bad"
    assert result.errors[0].code == "NOT_FOUND"
    assert result.meta.requested_count == 2
    assert result.meta.success_count == 1
    assert result.meta.error_count == 1
    assert result.meta.gmail_api_calls == 2


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_error_codes(mock_fetch: MagicMock) -> None:
    mock_fetch.return_value = {
        "r": ThreadFetchResult(error=RateLimitedError("rate limited")),
        "p": ThreadFetchResult(error=PermissionDeniedError("denied")),
    }

    result = _hydrator().hydrate("user@example.com", ["r", "p"])

    codes = {e.thread_id: e.code for e in result.errors}
    assert codes == {"r": "RATE_LIMITED", "p": "PERMISSION_DENIED"}


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_preserves_thread_order(mock_fetch: MagicMock) -> None:
    def raw_for(tid: str) -> dict:
        return _single_message_thread("plain_only.py", thread_id=tid)

    mock_fetch.return_value = {
        "b": ThreadFetchResult(raw=raw_for("b")),
        "a": ThreadFetchResult(raw=raw_for("a")),
        "c": ThreadFetchResult(raw=raw_for("c")),
    }

    result = _hydrator().hydrate("user@example.com", ["b", "a", "c"])

    assert [t.id for t in result.threads] == ["b", "a", "c"]


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_dedupes_fetch_input(mock_fetch: MagicMock) -> None:
    raw = _single_message_thread("plain_only.py", thread_id="dup")
    mock_fetch.return_value = {"dup": ThreadFetchResult(raw=raw)}

    result = _hydrator().hydrate("user@example.com", ["dup", "dup"])

    assert len(result.threads) == 1
    assert result.meta.requested_count == 2
    assert result.meta.gmail_api_calls == 1
    mock_fetch.assert_called_once()
    assert mock_fetch.call_args[0][2] == ["dup"]


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_multi_message_thread_fixture(mock_fetch: MagicMock) -> None:
    raw = load_thread_fixture("long_thread.py")
    thread_id = raw["id"]
    mock_fetch.return_value = {thread_id: ThreadFetchResult(raw=raw)}

    result = _hydrator().hydrate(
        "user@example.com",
        [thread_id],
        HydrationOptions(message_limit=2),
    )

    assert len(result.threads) == 1
    thread = result.threads[0]
    assert len(thread.messages) > 2
    omitted = [m for m in thread.messages if m.omitted_from_thread]
    assert omitted
    assert result.meta.truncated is True


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_result_matches_a3_schema(mock_fetch: MagicMock) -> None:
    raw = _single_message_thread("plain_only.py", thread_id="t1")
    mock_fetch.return_value = {
        "t1": ThreadFetchResult(raw=raw),
        "t2": ThreadFetchResult(error=ThreadNotFoundError("missing")),
    }

    data = hydration_to_json(_hydrator().hydrate("user@example.com", ["t1", "t2"]))

    assert set(data) == {"threads", "errors", "meta"}
    assert data["meta"]["requestedCount"] == 2
    assert data["meta"]["gmailApiCalls"] == 2
    assert data["meta"]["quotaUnitsEstimated"] == 2 * THREADS_GET_QUOTA_UNITS
    assert data["threads"][0]["messages"][0]["body"] == "Hello, world!"
    assert "htmlBody" not in str(data)
    assert data["errors"][0]["threadId"] == "t2"
    assert data["errors"][0]["code"] == "NOT_FOUND"


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_total_max_chars_is_noop_until_b6(mock_fetch: MagicMock) -> None:
    raw = _single_message_thread("plain_only.py", thread_id="t1")
    mock_fetch.return_value = {"t1": ThreadFetchResult(raw=raw)}

    baseline = _hydrator().hydrate("user@example.com", ["t1"], HydrationOptions())
    capped = _hydrator().hydrate(
        "user@example.com",
        ["t1"],
        HydrationOptions(total_max_chars=10),
    )

    assert capped.threads[0].messages[0].body == baseline.threads[0].messages[0].body
    assert capped.meta.total_chars == baseline.meta.total_chars


def test_hydrate_empty_thread_ids() -> None:
    result = _hydrator().hydrate("user@example.com", [])

    assert result.threads == []
    assert result.errors == []
    assert result.meta.requested_count == 0
    assert result.meta.gmail_api_calls == 0


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_truncated_when_body_capped(mock_fetch: MagicMock) -> None:
    body = "x" * 50
    raw = {
        "id": "t-cap",
        "messages": [
            {
                "id": "m1",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {"size": 50, "data": b64_text(body)},
                },
            }
        ],
    }
    mock_fetch.return_value = {"t-cap": ThreadFetchResult(raw=raw)}

    result = _hydrator().hydrate(
        "user@example.com",
        ["t-cap"],
        HydrationOptions(max_body_chars=20),
    )

    assert result.meta.truncated is True
