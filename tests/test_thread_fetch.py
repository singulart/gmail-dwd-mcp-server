from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from gmail_dwd_mcp.gmail_service import GmailService, message_needs_full_fetch
from gmail_dwd_mcp.hydration import hydration_to_json, triage_thread_from_api_thread
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


def _mock_gmail_service(thread_response: dict) -> tuple[GmailService, MagicMock]:
    messages_get = MagicMock()
    threads_get = MagicMock()
    threads_get.execute.return_value = thread_response

    users = MagicMock()
    users.threads.return_value.get.return_value = threads_get
    users.messages.return_value.get.return_value = messages_get

    service = MagicMock()
    service.users.return_value = users

    gmail = GmailService(wif_cache=MagicMock())
    gmail._service = MagicMock(return_value=service)  # type: ignore[method-assign]
    return gmail, messages_get


def test_message_needs_full_fetch_with_inline_payload() -> None:
    msg = _thread_with_inline_payload()["messages"][0]
    assert message_needs_full_fetch(msg) is False


def test_message_needs_full_fetch_without_payload() -> None:
    msg = _thread_with_inline_payload(include_payload=False)["messages"][0]
    assert message_needs_full_fetch(msg) is True


def test_fetch_triage_thread_uses_metadata_only() -> None:
    gmail, messages_get = _mock_gmail_service(_thread_with_inline_payload())

    raw = gmail._fetch_triage_thread(gmail._service("user@example.com"), "thread-1")
    triage = hydration_to_json(triage_thread_from_api_thread(raw))

    gmail._service("user@example.com").users().threads().get.assert_called_once()
    call_kwargs = (
        gmail._service("user@example.com").users().threads().get.call_args.kwargs
    )
    assert call_kwargs["format"] == "metadata"
    messages_get.execute.assert_not_called()
    assert triage["id"] == "thread-1"
    assert len(triage["messages"]) == 1
    assert triage["messages"][0]["snippet"] == "Hello world"
    assert triage["messages"][0]["subject"] == "Test subject"
    assert "body" not in triage["messages"][0]
    assert "plaintextBody" not in triage["messages"][0]
    assert "htmlBody" not in triage["messages"][0]


def test_message_from_gmail_api_writes_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    msg = _thread_with_inline_payload()["messages"][0]
    parsed = message_from_gmail_api(msg, full_content=True)
    assert parsed["plaintextBody"] == "Hello world"
    assert capsys.readouterr().out == ""
