"""MCP hydrate tool helpers (get_thread / get_threads)."""

from __future__ import annotations

from typing import Any

from gmail_dwd_mcp.hydration import (
    HydrateResult,
    HydratedThread,
    HydrationOptions,
)


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


def validate_hydrate_batch_size(thread_ids: list[str], max_batch_size: int) -> None:
    """Reject oversized batches before any Gmail API calls."""
    if len(thread_ids) > max_batch_size:
        raise ValueError(
            f"Batch size {len(thread_ids)} exceeds maximum {max_batch_size}. "
            f"Request at most {max_batch_size} thread IDs per get_threads call."
        )


def hydrate_batch_response(result: HydrateResult) -> HydrateResult:
    """Return partial-success batch result for get_threads (MCP output schema)."""
    return result


def hydrated_thread_response(result: HydrateResult) -> HydratedThread:
    """Return a single successful thread for get_thread (MCP output schema)."""
    if result.errors:
        err = result.errors[0]
        raise ValueError(f"{err.code}: {err.message}")
    if not result.threads:
        raise ValueError("NOT_FOUND: Thread not found")
    return result.threads[0]
