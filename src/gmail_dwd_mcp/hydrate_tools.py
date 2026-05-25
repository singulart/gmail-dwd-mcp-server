"""MCP hydrate tool helpers (get_thread / get_threads)."""

from __future__ import annotations

from typing import Any

from gmail_dwd_mcp.hydration import HydrateResult, HydrationOptions, hydration_to_json


def hydration_options_from_tool(
    *,
    strip_quoted_content: bool | None = None,
    message_limit: int | None = None,
    max_body_chars: int | None = None,
    total_max_chars: int | None = None,
    include_attachment_ids: bool | None = None,
) -> HydrationOptions:
    """Build :class:`HydrationOptions`, applying only params the caller set."""
    overrides: dict[str, Any] = {}
    if strip_quoted_content is not None:
        overrides["strip_quoted_content"] = strip_quoted_content
    if message_limit is not None:
        overrides["message_limit"] = message_limit
    if max_body_chars is not None:
        overrides["max_body_chars"] = max_body_chars
    if total_max_chars is not None:
        overrides["total_max_chars"] = total_max_chars
    if include_attachment_ids is not None:
        overrides["include_attachment_ids"] = include_attachment_ids
    return HydrationOptions(**overrides)


def hydrated_thread_response(result: HydrateResult) -> dict[str, Any]:
    """Serialize a single successful :class:`HydratedThread` for get_thread."""
    if result.errors:
        err = result.errors[0]
        raise ValueError(f"{err.code}: {err.message}")
    if not result.threads:
        raise ValueError("NOT_FOUND: Thread not found")
    return hydration_to_json(result.threads[0])
