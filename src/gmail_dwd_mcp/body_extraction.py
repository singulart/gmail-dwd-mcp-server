"""Extract a single plain-text body from Gmail API message payload trees."""

from __future__ import annotations

import base64
from typing import Any

from gmail_dwd_mcp.html_convert import convert_html_to_text
from gmail_dwd_mcp.reply_strip import strip_html_quote_regions


def extract_body(payload: dict[str, Any]) -> str:
    """Return normalized plain text from a Gmail API message payload.

    Prefers the first non-empty text/plain part; otherwise converts the first
    text/html part. Skips attachment parts and walks nested multipart structures
    (alternative, mixed, related). Returns \"\" when no usable body is present.
    """
    plain = _find_part_text(payload, "text/plain")
    if plain.strip():
        return plain.strip()
    html = _find_part_text(payload, "text/html")
    if html.strip():
        return convert_html_to_text(strip_html_quote_regions(html))
    return ""


def _decode_body_data(data: str) -> str:
    return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")


def _is_attachment_part(part: dict[str, Any]) -> bool:
    if part.get("filename"):
        return True
    body = part.get("body") or {}
    return bool(body.get("attachmentId") and not body.get("data"))


def _find_part_text(payload: dict[str, Any], mime_type: str) -> str:
    if _is_attachment_part(payload):
        return ""
    part_mime = payload.get("mimeType", "")
    body = payload.get("body") or {}
    data = body.get("data")
    if part_mime == mime_type and data:
        return _decode_body_data(data)

    parts = payload.get("parts") or []
    if part_mime.startswith("multipart/") and parts:
        # Prefer text/plain over text/html among direct alternative children.
        if part_mime == "multipart/alternative":
            for child in parts:
                if not _is_attachment_part(child) and child.get("mimeType") == mime_type:
                    text = _find_part_text(child, mime_type)
                    if text.strip():
                        return text
        for child in parts:
            text = _find_part_text(child, mime_type)
            if text.strip():
                return text
    elif parts:
        for child in parts:
            text = _find_part_text(child, mime_type)
            if text.strip():
                return text
    return ""
