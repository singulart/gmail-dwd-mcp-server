from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gmail_dwd_mcp.hydration import (
    HydrateError,
    HydrateMeta,
    HydrateResult,
    HydratedMessage,
    HydratedThread,
    HydrationOptions,
)
from gmail_dwd_mcp.server import AppContext, get_threads, mcp


def _ctx(hydrator: MagicMock, *, max_batch_size: int = 10) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.lifespan_context = AppContext(
        gmail=MagicMock(),
        hydrator=hydrator,
        max_batch_size=max_batch_size,
    )
    return ctx


def test_get_threads_tool_registered() -> None:
    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert "get_threads" in names


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_threads_delegates_three_ids_in_one_hydrate_call(
    mock_tool_span: MagicMock,
) -> None:
    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        threads=[
            HydratedThread(id="t1", messages=[HydratedMessage(id="m1", body="a")]),
            HydratedThread(id="t2", messages=[HydratedMessage(id="m2", body="b")]),
            HydratedThread(id="t3", messages=[HydratedMessage(id="m3", body="c")]),
        ],
        meta=HydrateMeta(requested_count=3, success_count=3, error_count=0),
    )
    thread_ids = ["t1", "t2", "t3"]

    result = get_threads("user@example.com", thread_ids, _ctx(hydrator))

    mock_tool_span.assert_called_once_with("get_threads", email="user@example.com")
    hydrator.hydrate.assert_called_once_with(
        "user@example.com",
        thread_ids,
        HydrationOptions(),
    )
    assert len(result.threads) == 3
    assert result.errors == []
    assert result.meta.requested_count == 3
    assert result.threads[0].messages[0].body == "a"
    dumped = result.model_dump(by_alias=True)
    assert "plaintextBody" not in dumped
    assert "htmlBody" not in dumped


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_threads_returns_partial_success(mock_tool_span: MagicMock) -> None:
    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        threads=[HydratedThread(id="ok", messages=[HydratedMessage(id="m", body="text")])],
        errors=[HydrateError(thread_id="bad", message="Thread not found: bad", code="NOT_FOUND")],
        meta=HydrateMeta(requested_count=2, success_count=1, error_count=1),
    )

    result = get_threads("user@example.com", ["ok", "bad"], _ctx(hydrator))

    assert len(result.threads) == 1
    assert result.threads[0].id == "ok"
    assert len(result.errors) == 1
    assert result.errors[0].thread_id == "bad"
    assert result.errors[0].code == "NOT_FOUND"
    _ = mock_tool_span


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_threads_rejects_batch_over_max_without_hydrate(
    mock_tool_span: MagicMock,
) -> None:
    hydrator = MagicMock()
    ids = [f"t{i}" for i in range(11)]

    with pytest.raises(ValueError, match="exceeds maximum 10"):
        get_threads("user@example.com", ids, _ctx(hydrator, max_batch_size=10))

    hydrator.hydrate.assert_not_called()
    _ = mock_tool_span


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_threads_passes_include_attachment_ids(mock_tool_span: MagicMock) -> None:
    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        threads=[HydratedThread(id="t", messages=[HydratedMessage(id="m", body="")])],
    )

    get_threads(
        "user@example.com",
        ["t"],
        _ctx(hydrator),
        includeAttachmentIds=False,
    )

    options: HydrationOptions = hydrator.hydrate.call_args.args[2]
    assert options.include_attachment_ids is False
    _ = mock_tool_span
