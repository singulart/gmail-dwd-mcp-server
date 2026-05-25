from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from gmail_dwd_mcp.gmail_fetch import ThreadFetchResult, ThreadNotFoundError
from gmail_dwd_mcp.hydration_logging import (
    LOG_EVENT_HYDRATE_COMPLETE,
    LOG_EVENT_HYDRATE_THREAD_ERROR,
)
from gmail_dwd_mcp.thread_hydrator import ThreadHydrator


@pytest.fixture
def caplog_hydration(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    caplog.set_level(logging.DEBUG)
    return caplog


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_logs_summary_fields(
    mock_fetch: MagicMock,
    caplog_hydration: pytest.LogCaptureFixture,
) -> None:
    mock_fetch.return_value = {
        "ok": ThreadFetchResult(
            raw={
                "id": "ok",
                "messages": [
                    {
                        "id": "m1",
                        "payload": {
                            "mimeType": "text/plain",
                            "headers": [],
                            "body": {"size": 5, "data": "aGVsbG8="},
                        },
                    }
                ],
            }
        ),
        "bad": ThreadFetchResult(error=ThreadNotFoundError("Thread not found: bad")),
    }

    ThreadHydrator(get_service=lambda _e: MagicMock()).hydrate(
        "user@example.com",
        ["ok", "bad"],
    )

    complete = [
        r
        for r in caplog_hydration.records
        if r.msg == LOG_EVENT_HYDRATE_COMPLETE and r.levelno == logging.INFO
    ]
    assert len(complete) == 1
    record = complete[0]
    assert record.batch_size == 2
    assert record.success_count == 1
    assert record.error_count == 1
    assert record.output_chars == 5
    assert record.truncated is False
    assert record.duration_ms >= 0

    assert "hello" not in record.getMessage().lower()
    assert not any("plaintextBody" in str(r.__dict__) for r in caplog_hydration.records)


@patch("gmail_dwd_mcp.thread_hydrator.fetch_threads_raw")
def test_hydrate_logs_per_thread_error(
    mock_fetch: MagicMock,
    caplog_hydration: pytest.LogCaptureFixture,
) -> None:
    mock_fetch.return_value = {
        "missing": ThreadFetchResult(error=ThreadNotFoundError("Thread not found: missing")),
    }

    ThreadHydrator(get_service=lambda _e: MagicMock()).hydrate(
        "user@example.com",
        ["missing"],
    )

    errors = [
        r
        for r in caplog_hydration.records
        if r.msg == LOG_EVENT_HYDRATE_THREAD_ERROR and r.levelno == logging.ERROR
    ]
    assert len(errors) == 1
    assert errors[0].thread_id == "missing"
    assert errors[0].error_code == "NOT_FOUND"
    assert "Thread not found" not in errors[0].getMessage()


def test_log_hydrate_complete_includes_truncated_flag(
    caplog_hydration: pytest.LogCaptureFixture,
) -> None:
    from gmail_dwd_mcp.hydration import HydrateMeta, HydrateResult
    from gmail_dwd_mcp.hydration_logging import log_hydrate_complete

    log_hydrate_complete(
        duration_ms=12,
        result=HydrateResult(
            meta=HydrateMeta(
                requested_count=1,
                success_count=1,
                error_count=0,
                total_chars=100,
                truncated=True,
            ),
        ),
    )

    record = caplog_hydration.records[-1]
    assert record.truncated is True
    assert record.output_chars == 100
    assert "xxxx" not in record.getMessage()


def test_hydrate_empty_batch_logs_zero_counts(
    caplog_hydration: pytest.LogCaptureFixture,
) -> None:
    ThreadHydrator(get_service=lambda _e: MagicMock()).hydrate("user@example.com", [])

    record = next(
        r for r in caplog_hydration.records if r.msg == LOG_EVENT_HYDRATE_COMPLETE
    )
    assert record.batch_size == 0
    assert record.success_count == 0
    assert record.error_count == 0
    assert record.output_chars == 0
