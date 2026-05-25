from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from gmail_dwd_mcp.hydration import (
    DEFAULT_MAX_BODY_CHARS,
    DEFAULT_MESSAGE_LIMIT,
    HydrateResult,
    HydratedMessage,
    HydratedThread,
    HydrationOptions,
)
from gmail_dwd_mcp.server import AppContext, get_thread


def _ctx(hydrator: MagicMock) -> MagicMock:
    ctx = MagicMock()
    ctx.request_context.lifespan_context = AppContext(
        gmail=MagicMock(),
        hydrator=hydrator,
        max_batch_size=10,
    )
    return ctx


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_thread_delegates_to_hydrator(mock_tool_span: MagicMock) -> None:
    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        threads=[
            HydratedThread(
                id="thread-1",
                messages=[HydratedMessage(id="m1", body="normalized text")],
            )
        ],
    )
    ctx = _ctx(hydrator)

    result = get_thread(
        "user@example.com",
        "thread-1",
        ctx,
        stripQuotedContent=False,
        messageLimit=10,
        maxBodyChars=8000,
    )

    mock_tool_span.assert_called_once_with("get_thread", email="user@example.com")
    hydrator.hydrate.assert_called_once()
    call = hydrator.hydrate.call_args
    assert call.args[0] == "user@example.com"
    assert call.args[1] == ["thread-1"]
    options: HydrationOptions = call.args[2]
    assert options.strip_quoted_content is False
    assert options.message_limit == 10
    assert options.max_body_chars == 8000
    assert result.id == "thread-1"
    assert result.messages[0].body == "normalized text"
    dumped = result.model_dump(by_alias=True)
    assert "plaintextBody" not in dumped
    assert "htmlBody" not in dumped


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_thread_uses_default_options(mock_tool_span: MagicMock) -> None:
    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        threads=[HydratedThread(id="t", messages=[HydratedMessage(id="m", body="")])],
    )

    get_thread("user@example.com", "t", _ctx(hydrator))

    options: HydrationOptions = hydrator.hydrate.call_args.args[2]
    assert options.message_limit == DEFAULT_MESSAGE_LIMIT
    assert options.max_body_chars == DEFAULT_MAX_BODY_CHARS
    assert options.strip_quoted_content is True
    _ = mock_tool_span


@patch("gmail_dwd_mcp.server.tool_span")
def test_get_thread_propagates_hydrate_error(mock_tool_span: MagicMock) -> None:
    from gmail_dwd_mcp.hydration import HydrateError

    hydrator = MagicMock()
    hydrator.hydrate.return_value = HydrateResult(
        errors=[HydrateError(thread_id="missing", message="Thread not found: missing", code="NOT_FOUND")],
    )

    with pytest.raises(ValueError, match="NOT_FOUND"):
        get_thread("user@example.com", "missing", _ctx(hydrator))
    _ = mock_tool_span
