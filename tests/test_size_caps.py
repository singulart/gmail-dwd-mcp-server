from __future__ import annotations

import pytest

from gmail_dwd_mcp.hydration import DEFAULT_MAX_BODY_CHARS, DEFAULT_MESSAGE_LIMIT, HydrationOptions
from gmail_dwd_mcp.size_caps import TRUNCATION_MARKER, cap_body, limit_messages


@pytest.mark.parametrize(
    ("text", "max_chars", "expected", "truncated"),
    [
        ("short", 100, "short", False),
        ("x" * 20, 20, "x" * 20, False),
        ("x" * 21, 20, "x" * (20 - len(TRUNCATION_MARKER)) + TRUNCATION_MARKER, True),
        ("", 10, "", False),
    ],
)
def test_cap_body_boundaries(
    text: str,
    max_chars: int,
    expected: str,
    truncated: bool,
) -> None:
    result, was_truncated = cap_body(text, max_chars)
    assert result == expected
    assert was_truncated is truncated
    assert len(result) <= max_chars


def test_cap_body_marker_visible_when_truncated() -> None:
    text = "a" * 100
    result, truncated = cap_body(text, 30)
    assert truncated
    assert result.endswith(TRUNCATION_MARKER)
    assert "aaa" in result


def test_cap_body_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError):
        cap_body("x", 0)


def test_limit_messages_keeps_newest_ten_of_twenty() -> None:
    messages = [{"id": f"msg-{i}", "body": f"body-{i}"} for i in range(20)]
    kept, omitted = limit_messages(messages, 10)
    assert omitted == 10
    assert len(kept) == 10
    assert [m["id"] for m in kept] == [f"msg-{i}" for i in range(10, 20)]


def test_limit_messages_no_op_when_under_limit() -> None:
    messages = [{"id": "msg-1"}, {"id": "msg-2"}]
    kept, omitted = limit_messages(messages, 10)
    assert omitted == 0
    assert kept == messages


def test_limit_messages_rejects_invalid_limit() -> None:
    with pytest.raises(ValueError):
        limit_messages([], 0)


def test_hydration_options_defaults_match_b5_constants() -> None:
    opts = HydrationOptions()
    assert opts.message_limit == DEFAULT_MESSAGE_LIMIT
    assert opts.max_body_chars == DEFAULT_MAX_BODY_CHARS
    assert DEFAULT_MESSAGE_LIMIT == 20
    assert DEFAULT_MAX_BODY_CHARS == 16_000
