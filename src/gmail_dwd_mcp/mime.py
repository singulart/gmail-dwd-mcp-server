from __future__ import annotations

import base64
import email.utils
from email import message_from_bytes
from email.message import Message
from typing import Any


def _header_value(headers: list[dict[str, str]], name: str) -> str | None:
    lower = name.lower()
    for header in headers:
        if header.get("name", "").lower() == lower:
            return header.get("value")
    return None


def _parse_addresses(value: str | None) -> list[str]:
    if not value:
        return []
    return [addr for _, addr in email.utils.getaddresses([value]) if addr]


def _extract_plaintext(part: Message) -> str | None:
    if part.is_multipart():
        for child in part.walk():
            if child.get_content_maintype() == "multipart":
                continue
            if child.get_content_type() == "text/plain" and not child.get_filename():
                payload = child.get_payload(decode=True)
                if payload:
                    charset = child.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")
        return None
    if part.get_content_type() == "text/plain":
        payload = part.get_payload(decode=True)
        if payload:
            charset = part.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")
    return None


def _attachment_ids(part: Message) -> list[str]:
    ids: list[str] = []
    if part.is_multipart():
        for child in part.walk():
            if child.get_content_disposition() == "attachment" and child.get("Content-ID"):
                cid = child.get("Content-ID", "").strip("<>")
                if cid:
                    ids.append(cid)
            elif child.get_filename() and child.get("Content-ID"):
                cid = child.get("Content-ID", "").strip("<>")
                if cid:
                    ids.append(cid)
    return ids


def _iso_date(headers: list[dict[str, str]]) -> str | None:
    raw = _header_value(headers, "Date")
    if not raw:
        return None
    parsed = email.utils.parsedate_to_datetime(raw)
    return parsed.date().isoformat()


def message_from_gmail_api(
    msg: dict[str, Any],
    *,
    full_content: bool,
) -> dict[str, Any]:
    headers = msg.get("payload", {}).get("headers", [])
    if not headers and "payload" in msg:
        headers = msg["payload"].get("headers", [])

    result: dict[str, Any] = {
        "id": msg["id"],
        "snippet": msg.get("snippet"),
        "subject": _header_value(headers, "Subject"),
        "sender": _parse_addresses(_header_value(headers, "From"))[:1],
        "toRecipients": _parse_addresses(_header_value(headers, "To")),
        "ccRecipients": _parse_addresses(_header_value(headers, "Cc")),
        "date": _iso_date(headers),
    }
    sender = result.pop("sender")
    result["sender"] = sender[0] if sender else None

    if full_content and "raw" in msg:
        raw_bytes = base64.urlsafe_b64decode(msg["raw"].encode("utf-8"))
        mime = message_from_bytes(raw_bytes)
        result["plaintextBody"] = _extract_plaintext(mime)
        result["attachmentIds"] = _attachment_ids(mime)
    elif full_content and msg.get("payload"):
        body_data = _extract_body_from_payload(msg["payload"])
        result["plaintextBody"] = body_data
        result["attachmentIds"] = _collect_attachment_ids(msg["payload"])
    else:
        result["plaintextBody"] = None
        result["attachmentIds"] = []

    return result


def _extract_body_from_payload(payload: dict[str, Any]) -> str | None:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {})
    data = body.get("data")
    if mime_type == "text/plain" and data:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []) or []:
        text = _extract_body_from_payload(part)
        if text:
            return text
    return None


def _collect_attachment_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    if payload.get("filename") and payload.get("body", {}).get("attachmentId"):
        ids.append(payload["body"]["attachmentId"])
    for part in payload.get("parts", []) or []:
        ids.extend(_collect_attachment_ids(part))
    return ids
