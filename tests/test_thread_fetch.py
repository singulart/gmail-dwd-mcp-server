from __future__ import annotations

import base64
from unittest.mock import MagicMock

import pytest

from gmail_dwd_mcp.gmail_service import GmailService, message_needs_full_fetch
from gmail_dwd_mcp.mime import message_from_gmail_api
from gmail_dwd_mcp.models import MessageFormat


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


def test_get_thread_internal_uses_only_threads_get_when_payload_inline() -> None:
    gmail, messages_get = _mock_gmail_service(_thread_with_inline_payload())

    result = gmail._get_thread_internal(
        gmail._service("user@example.com"),
        "thread-1",
        message_format=MessageFormat.FULL_CONTENT,
    )

    gmail._service("user@example.com").users().threads().get.assert_called_once()
    messages_get.execute.assert_not_called()
    assert result["id"] == "thread-1"
    assert len(result["messages"]) == 1
    assert result["messages"][0]["plaintextBody"] == "Hello world"
    assert result["messages"][0]["subject"] == "Test subject"


def test_get_thread_internal_fetches_message_when_payload_missing() -> None:
    thread = _thread_with_inline_payload(include_payload=False)
    fetched = _thread_with_inline_payload()["messages"][0]
    gmail, messages_get = _mock_gmail_service(thread)
    messages_get.execute.return_value = fetched

    result = gmail._get_thread_internal(
        gmail._service("user@example.com"),
        "thread-1",
        message_format=MessageFormat.FULL_CONTENT,
    )

    messages_get.execute.assert_called_once()
    assert result["messages"][0]["plaintextBody"] == "Hello world"


def test_message_from_gmail_api_writes_no_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    msg = _thread_with_inline_payload()["messages"][0]
    parsed = message_from_gmail_api(msg, full_content=True)
    assert parsed["plaintextBody"] == "Hello world"
    assert capsys.readouterr().out == ""
