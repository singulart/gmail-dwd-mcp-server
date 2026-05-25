"""Thread normalization pipeline for LLM hydration (TASK-B7)."""

from __future__ import annotations

from typing import Any

from gmail_dwd_mcp.body_extraction import extract_body
from gmail_dwd_mcp.hydration import HydratedMessage, HydratedThread, HydrationOptions
from gmail_dwd_mcp.mime import (
    _collect_attachment_ids,
    _header_value,
    _iso_date,
    _parse_addresses,
)
from gmail_dwd_mcp.reply_strip import strip_reply_content
from gmail_dwd_mcp.size_caps import cap_body


def normalize_thread(raw_thread: dict[str, Any], options: HydrationOptions) -> HydratedThread:
    """Shape a Gmail API thread into :class:`HydratedThread` for LLM tools.

    Pipeline order (per message, then per thread):

    1. Extract body — plain preferred, HTML fallback (``extract_body`` / B1–B2).
    2. Strip quoted replies and ``--`` signatures (B3) when ``stripQuotedContent``
       is set; skip for the first (oldest) message in the thread.
    3. Per-message body cap with visible truncation marker (B5).
    4. Per-thread message limit — all messages are returned in Gmail order (oldest
       first). Messages outside the newest ``messageLimit`` are metadata-only:
       ``body`` is empty and ``omittedFromThread`` is true (B5).
    5. Map to :class:`HydratedMessage` / :class:`HydratedThread` (``body`` only).

    Global cross-thread ``totalMaxChars`` (B6) is applied later in ThreadHydrator.
    """
    raw_messages = raw_thread.get("messages") or []
    keep_from_index = max(0, len(raw_messages) - options.message_limit)

    hydrated: list[HydratedMessage] = []
    for index, msg in enumerate(raw_messages):
        if index < keep_from_index:
            hydrated.append(_metadata_only_message(msg))
        else:
            hydrated.append(
                _normalize_message(msg, options, is_first_in_thread=index == 0)
            )

    return HydratedThread(id=raw_thread["id"], messages=hydrated)


def _metadata_only_message(msg: dict[str, Any]) -> HydratedMessage:
    """Headers-only row for messages dropped by ``messageLimit``."""
    payload = msg.get("payload") or {}
    headers = payload.get("headers") or []
    senders = _parse_addresses(_header_value(headers, "From"))
    return HydratedMessage(
        id=msg["id"],
        subject=_header_value(headers, "Subject"),
        sender=senders[0] if senders else None,
        to_recipients=_parse_addresses(_header_value(headers, "To")),
        cc_recipients=_parse_addresses(_header_value(headers, "Cc")),
        date=_iso_date(headers),
        body="",
        attachment_ids=[],
        omitted_from_thread=True,
    )


def _normalize_message(
    msg: dict[str, Any],
    options: HydrationOptions,
    *,
    is_first_in_thread: bool,
) -> HydratedMessage:
    payload = msg.get("payload") or {}
    body = extract_body(payload)
    if options.strip_quoted_content:
        body = strip_reply_content(body, is_first_in_thread=is_first_in_thread)
    body, _truncated = cap_body(body, options.max_body_chars)

    headers = payload.get("headers") or []
    senders = _parse_addresses(_header_value(headers, "From"))
    attachment_ids: list[str] = []
    if options.include_attachment_ids and payload:
        attachment_ids = _collect_attachment_ids(payload)

    return HydratedMessage(
        id=msg["id"],
        subject=_header_value(headers, "Subject"),
        sender=senders[0] if senders else None,
        to_recipients=_parse_addresses(_header_value(headers, "To")),
        cc_recipients=_parse_addresses(_header_value(headers, "Cc")),
        date=_iso_date(headers),
        body=body,
        attachment_ids=attachment_ids,
        omitted_from_thread=False,
    )
