"""Structured operational logging for hydrate batches (TASK-E3)."""

from __future__ import annotations

import logging

from gmail_dwd_mcp.hydration import HydrateResult

logger = logging.getLogger(__name__)

# Stable keys for CloudWatch Logs metric filters (snake_case, no message content).
LOG_EVENT_HYDRATE_COMPLETE = "hydrate_complete"
LOG_EVENT_HYDRATE_THREAD_ERROR = "hydrate_thread_error"


def log_hydrate_thread_errors(result: HydrateResult) -> None:
    """ERROR per failed thread — thread id and code only (no bodies or snippets)."""
    for err in result.errors:
        logger.error(
            LOG_EVENT_HYDRATE_THREAD_ERROR,
            extra={
                "event": LOG_EVENT_HYDRATE_THREAD_ERROR,
                "thread_id": err.thread_id,
                "error_code": err.code or "GMAIL_API_ERROR",
            },
        )


def log_hydrate_complete(*, duration_ms: int, result: HydrateResult) -> None:
    """INFO summary per hydrate invocation (get_thread / get_threads)."""
    meta = result.meta
    logger.info(
        LOG_EVENT_HYDRATE_COMPLETE,
        extra={
            "event": LOG_EVENT_HYDRATE_COMPLETE,
            "batch_size": meta.requested_count,
            "duration_ms": duration_ms,
            "success_count": meta.success_count,
            "error_count": meta.error_count,
            "output_chars": meta.total_chars,
            "truncated": meta.truncated,
        },
    )
