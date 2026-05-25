from __future__ import annotations

from unittest.mock import MagicMock, patch

from gmail_dwd_mcp.gmail_service import GmailService


def test_search_threads_returns_triage_shape_without_body_fields() -> None:
    gmail = GmailService(wif_cache=MagicMock())
    mock_service = MagicMock()
    mock_service.users.return_value.threads.return_value.list.return_value.execute.return_value = {
        "threads": [{"id": "thread-1"}],
    }
    gmail._service = MagicMock(return_value=mock_service)  # type: ignore[method-assign]

    triage_raw = {
        "id": "thread-1",
        "messages": [
            {
                "id": "msg-1",
                "snippet": "Preview text",
                "subject": "Hello",
                "sender": "a@example.com",
                "toRecipients": ["b@example.com"],
                "ccRecipients": [],
                "date": "Mon, 1 Jan 2024 12:00:00 +0000",
            }
        ],
    }
    with patch.object(gmail, "_fetch_triage_thread", return_value=triage_raw):
        result = gmail.search_threads("user@example.com")

    assert len(result["threads"]) == 1
    thread = result["threads"][0]
    msg = thread["messages"][0]
    assert msg["snippet"] == "Preview text"
    assert "body" not in msg
    assert "plaintextBody" not in msg
    assert "htmlBody" not in msg
