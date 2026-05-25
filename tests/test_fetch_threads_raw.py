from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pytest

from gmail_dwd_mcp.gmail_fetch import (
    ThreadFetchResult,
    ThreadNotFoundError,
    fetch_threads_raw,
    get_thread_fetch_executor,
    shutdown_thread_fetch_executor,
)


@pytest.fixture(autouse=True)
def _isolate_thread_fetch_executor() -> None:
    shutdown_thread_fetch_executor()
    yield
    shutdown_thread_fetch_executor()


@patch("gmail_dwd_mcp.gmail_fetch.fetch_thread_raw")
def test_fetch_threads_raw_runs_fetches_in_parallel(mock_fetch_thread_raw: MagicMock) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()
    delay = 0.08

    def slow_fetch(_service: MagicMock, thread_id: str, **_kwargs) -> dict:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(delay)
        with lock:
            active -= 1
        return {"id": thread_id}

    mock_fetch_thread_raw.side_effect = slow_fetch
    thread_ids = [f"thread-{i}" for i in range(5)]

    with ThreadPoolExecutor(max_workers=5) as pool:
        start = time.monotonic()
        results = fetch_threads_raw(
            MagicMock(),
            "user@example.com",
            thread_ids,
            concurrency=5,
            executor=pool,
        )
    elapsed = time.monotonic() - start

    assert len(results) == 5
    assert all(r.ok for r in results.values())
    assert mock_fetch_thread_raw.call_count == 5
    assert peak >= 4
    assert elapsed < delay * 5


@patch("gmail_dwd_mcp.gmail_fetch.fetch_thread_raw")
def test_fetch_threads_raw_partial_success(mock_fetch_thread_raw: MagicMock) -> None:
    def fetch_side_effect(_service, thread_id: str, **_kwargs) -> dict:
        if thread_id == "bad":
            raise ThreadNotFoundError("Thread not found: bad")
        return {"id": thread_id}

    mock_fetch_thread_raw.side_effect = fetch_side_effect

    results = fetch_threads_raw(
        MagicMock(),
        "user@example.com",
        ["good-1", "bad", "good-2"],
        concurrency=3,
    )

    assert results["good-1"].ok and results["good-1"].raw == {"id": "good-1"}
    assert results["good-2"].ok and results["good-2"].raw == {"id": "good-2"}
    assert not results["bad"].ok
    assert isinstance(results["bad"].error, ThreadNotFoundError)
    assert mock_fetch_thread_raw.call_count == 3


@patch("gmail_dwd_mcp.gmail_fetch.fetch_thread_raw")
def test_fetch_threads_raw_dedupes_thread_ids(mock_fetch_thread_raw: MagicMock) -> None:
    mock_fetch_thread_raw.return_value = {"id": "thread-a"}

    results = fetch_threads_raw(
        MagicMock(),
        "user@example.com",
        ["thread-a", "thread-b", "thread-a"],
        concurrency=2,
    )

    assert mock_fetch_thread_raw.call_count == 2
    called_ids = {call.args[1] for call in mock_fetch_thread_raw.call_args_list}
    assert called_ids == {"thread-a", "thread-b"}
    assert set(results) == {"thread-a", "thread-b"}
    assert results["thread-a"] == ThreadFetchResult(raw={"id": "thread-a"})


def test_fetch_threads_raw_empty_input() -> None:
    assert fetch_threads_raw(MagicMock(), "user@example.com", []) == {}


@patch("gmail_dwd_mcp.gmail_fetch.fetch_thread_raw")
def test_fetch_threads_raw_reuses_process_executor(mock_fetch_thread_raw: MagicMock) -> None:
    mock_fetch_thread_raw.return_value = {"id": "t"}
    get_thread_fetch_executor(max_workers=3)
    first = get_thread_fetch_executor()
    fetch_threads_raw(MagicMock(), "user@example.com", ["t1"])
    second = get_thread_fetch_executor()
    assert first is second
    assert mock_fetch_thread_raw.call_count == 1


@patch("gmail_dwd_mcp.gmail_fetch.fetch_thread_raw")
def test_fetch_threads_raw_caps_workers_by_concurrency(
    mock_fetch_thread_raw: MagicMock,
) -> None:
    active = 0
    peak = 0
    lock = threading.Lock()
    delay = 0.05

    def slow_fetch(_service: MagicMock, _thread_id: str, **_kwargs) -> dict:
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(delay)
        with lock:
            active -= 1
        return {"id": "t"}

    mock_fetch_thread_raw.side_effect = slow_fetch

    with ThreadPoolExecutor(max_workers=5) as pool:
        start = time.monotonic()
        fetch_threads_raw(
            MagicMock(),
            "user@example.com",
            ["t1", "t2", "t3", "t4", "t5"],
            concurrency=2,
            executor=pool,
        )
        elapsed = time.monotonic() - start

    assert mock_fetch_thread_raw.call_count == 5
    assert peak <= 2
    assert elapsed >= delay * 2
