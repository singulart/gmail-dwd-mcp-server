from __future__ import annotations

import base64

import pytest

from gmail_dwd_mcp.gmail_service import GmailService, message_needs_full_fetch
from gmail_dwd_mcp.mime import message_from_gmail_api


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _thread_with_inline_payload(*, include_payload: bool = True) -> dict:
    message: dict = {
        "id": "msg-1",
        "snippet": "Hello world",
    }
    if include_payload:
        message["payload"] = {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Test subject"},
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
            ],
            "body": {"size": 11, "data": _b64("Hello world")},
        }
    return {"id": "thread-1", "messages": [message]}


def test_message_needs_full_fetch_with_inline_payload() -> None:
    msg = _thread_with_inline_payload()["messages"][0]
    assert message_needs_full_fetch(msg) is False


def test_message_needs_full_fetch_without_payload() -> None:
    msg = _thread_with_inline_payload(include_payload=False)["messages"][0]
    assert message_needs_full_fetch(msg) is True


def test_message_from_gmail_api_writes_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    msg = _thread_with_inline_payload()["messages"][0]
    parsed = message_from_gmail_api(msg, full_content=True)
    assert parsed["plaintextBody"] == "Hello world"
    assert capsys.readouterr().out == ""
