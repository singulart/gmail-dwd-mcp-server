"""Per-message and per-thread size limits for hydration (TASK-B5)."""

from __future__ import annotations

from typing import TypeVar

TRUNCATION_MARKER = "[... truncated ...]"

T = TypeVar("T")


def cap_body(text: str, max_body_chars: int) -> tuple[str, bool]:
    """Truncate body text to ``max_body_chars``, appending ``TRUNCATION_MARKER`` when cut."""
    if max_body_chars < 1:
        raise ValueError("max_body_chars must be >= 1")
    if len(text) <= max_body_chars:
        return text, False
    if max_body_chars <= len(TRUNCATION_MARKER):
        return TRUNCATION_MARKER[:max_body_chars], True
    keep = max_body_chars - len(TRUNCATION_MARKER)
    return text[:keep] + TRUNCATION_MARKER, True


def limit_messages(messages: list[T], message_limit: int) -> tuple[list[T], int]:
    """Keep the newest ``message_limit`` messages (Gmail thread order: oldest first).

    Returns ``(kept_messages, omitted_count)``.
    """
    if message_limit < 1:
        raise ValueError("message_limit must be >= 1")
    if len(messages) <= message_limit:
        return list(messages), 0
    omitted_count = len(messages) - message_limit
    return list(messages[-message_limit:]), omitted_count
