from __future__ import annotations

import pytest

from gmail_dwd_mcp.hydration import HydrationOptions, hydration_to_json
from gmail_dwd_mcp.normalize import normalize_thread
from gmail_dwd_mcp.size_caps import TRUNCATION_MARKER
from tests.fixture_loader import load_fixture, load_payload_fixture, load_thread_fixture


def _single_message_thread(fixture_name: str, *, thread_id: str = "thread-test") -> dict:
    return {
        "id": thread_id,
        "messages": [
            {
                "id": "msg-1",
                "snippet": "snippet",
                "payload": load_payload_fixture(fixture_name),
            }
        ],
    }


@pytest.mark.parametrize(
    ("fixture_name", "expected_body"),
    [
        ("plain_only.py", "Hello, world!"),
        ("multipart_alternative.py", "Plain version"),
        ("nested_multipart.py", "Nested plain body"),
    ],
)
def test_normalize_thread_fixture_bodies(fixture_name: str, expected_body: str) -> None:
    thread = normalize_thread(
        _single_message_thread(fixture_name),
        HydrationOptions(),
    )
    assert len(thread.messages) == 1
    assert thread.messages[0].body == expected_body


def test_normalize_thread_strips_gmail_quote() -> None:
    thread = normalize_thread(
        _single_message_thread("gmail_quote.py"),
        HydrationOptions(strip_quoted_content=True),
    )
    assert thread.messages[0].body == "Thanks for the update."


def test_normalize_thread_outlook_first_message_keeps_quote_when_first() -> None:
    raw = _single_message_thread("outlook_quoted_reply.py")
    thread = normalize_thread(raw, HydrationOptions(strip_quoted_content=True))
    assert len(thread.messages) == 1
    assert "Original Message" in thread.messages[0].body


def test_normalize_thread_outlook_strips_quote_on_reply() -> None:
    raw = {
        "id": "thread-reply",
        "messages": [
            {
                "id": "msg-1",
                "payload": load_payload_fixture("plain_only.py"),
            },
            {
                "id": "msg-2",
                "payload": load_payload_fixture("outlook_quoted_reply.py"),
            },
        ],
    }
    thread = normalize_thread(raw, HydrationOptions(strip_quoted_content=True))
    assert thread.messages[0].body == "Hello, world!"
    assert thread.messages[1].body == "Sounds good to me."


def test_normalize_thread_caps_body() -> None:
    raw = {
        "id": "t1",
        "messages": [
            {
                "id": "msg-1",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "size": 50,
                        "data": __import__("base64").urlsafe_b64encode(b"x" * 50).decode(),
                    },
                },
            }
        ],
    }
    thread = normalize_thread(raw, HydrationOptions(max_body_chars=20))
    body = thread.messages[0].body
    assert len(body) == 20
    assert body.endswith(TRUNCATION_MARKER)


def test_normalize_thread_message_limit_marks_omitted_messages() -> None:
    raw = load_thread_fixture("long_thread.py")
    thread = normalize_thread(raw, HydrationOptions(message_limit=10))
    assert len(thread.messages) == 12

    omitted = thread.messages[:2]
    kept = thread.messages[2:]
    assert all(m.omitted_from_thread for m in omitted)
    assert all(m.body == "" for m in omitted)
    assert all(not m.omitted_from_thread for m in kept)
    assert [m.id for m in omitted] == ["msg-01", "msg-02"]
    assert [m.id for m in kept] == [f"msg-{i:02d}" for i in range(3, 13)]
    assert kept[-1].body == "Thread message 12"


def test_normalize_thread_output_has_body_only() -> None:
    thread = normalize_thread(
        _single_message_thread("html_only.py"),
        HydrationOptions(),
    )
    dumped = hydration_to_json(thread)
    msg = dumped["messages"][0]
    assert "body" in msg
    assert "htmlBody" not in msg
    assert "plaintextBody" not in msg
    assert "click here" in msg["body"]


def test_normalize_thread_respects_include_attachment_ids() -> None:
    thread = normalize_thread(
        _single_message_thread("nested_multipart.py"),
        HydrationOptions(include_attachment_ids=True),
    )
    assert thread.messages[0].attachment_ids == ["ANGjdJ_example"]

    thread_off = normalize_thread(
        _single_message_thread("nested_multipart.py"),
        HydrationOptions(include_attachment_ids=False),
    )
    assert thread_off.messages[0].attachment_ids == []


def test_normalize_thread_long_thread_fixture_via_load_fixture() -> None:
    raw = load_fixture("long_thread.py")
    thread = normalize_thread(raw, HydrationOptions(message_limit=5))
    assert len(thread.messages) == 12
    assert sum(1 for m in thread.messages if m.omitted_from_thread) == 7
    assert [m.id for m in thread.messages if not m.omitted_from_thread] == [
        f"msg-{i:02d}" for i in range(8, 13)
    ]
    assert thread.messages[-1].id == "msg-12"
    assert thread.messages[-1].body == "Thread message 12"
