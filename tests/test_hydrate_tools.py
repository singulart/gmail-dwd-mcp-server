from __future__ import annotations

import pytest

from gmail_dwd_mcp.hydrate_tools import (
    hydrated_thread_response,
    hydration_options_from_tool,
    validate_hydrate_batch_size,
)
from gmail_dwd_mcp.hydration import (
    DEFAULT_MAX_BODY_CHARS,
    DEFAULT_MESSAGE_LIMIT,
    HydrateError,
    HydrateResult,
    HydratedMessage,
    HydratedThread,
)


def test_hydration_options_from_tool_uses_defaults_when_unset() -> None:
    opts = hydration_options_from_tool()
    assert opts.strip_quoted_content is True
    assert opts.message_limit == DEFAULT_MESSAGE_LIMIT
    assert opts.max_body_chars == DEFAULT_MAX_BODY_CHARS
    assert opts.total_max_chars is None


def test_hydration_options_from_tool_applies_overrides() -> None:
    opts = hydration_options_from_tool(
        strip_quoted_content=False,
        message_limit=5,
        max_body_chars=1000,
        total_max_chars=50_000,
    )
    assert opts.strip_quoted_content is False
    assert opts.message_limit == 5
    assert opts.max_body_chars == 1000
    assert opts.total_max_chars == 50_000


def test_hydrated_thread_response_serializes_thread() -> None:
    result = HydrateResult(
        threads=[
            HydratedThread(
                id="t1",
                messages=[HydratedMessage(id="m1", body="hello")],
            )
        ],
    )
    data = hydrated_thread_response(result)
    assert data["id"] == "t1"
    assert data["messages"][0]["body"] == "hello"
    assert "plaintextBody" not in data
    assert "htmlBody" not in data


def test_validate_hydrate_batch_size_rejects_oversized_batch() -> None:
    with pytest.raises(ValueError, match="exceeds maximum 3"):
        validate_hydrate_batch_size(["a", "b", "c", "d"], 3)


def test_hydrated_thread_response_raises_on_error() -> None:
    result = HydrateResult(
        errors=[HydrateError(thread_id="t1", message="Thread not found", code="NOT_FOUND")],
    )
    with pytest.raises(ValueError, match="NOT_FOUND: Thread not found"):
        hydrated_thread_response(result)
