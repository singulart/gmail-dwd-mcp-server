"""Schema snapshots for LLM read tools (TASK-D3)."""

from __future__ import annotations

import asyncio
import json

from gmail_dwd_mcp.hydration import (
    HydrateError,
    HydrateMeta,
    HydrateResult,
    HydratedMessage,
    HydratedThread,
    TriageMessage,
    TriageThread,
    hydration_to_json,
    triage_thread_from_api_thread,
)
from gmail_dwd_mcp.server import mcp

TRIAGE_MESSAGE_SNAPSHOT = {
    "id": "msg-abc",
    "snippet": "Thanks for the update…",
    "subject": "Re: Project status",
    "sender": "colleague@company.com",
    "toRecipients": ["user@company.com"],
    "ccRecipients": [],
    "date": "Mon, 12 May 2025 14:30:00 +0000",
}

TRIAGE_THREAD_SNAPSHOT = {
    "id": "thread-xyz",
    "messages": [TRIAGE_MESSAGE_SNAPSHOT],
}

HYDRATED_BODY = "Thanks for the update. I'll review today."

HYDRATED_MESSAGE_SNAPSHOT = {
    "id": "msg-abc",
    "subject": "Re: Project status",
    "sender": "colleague@company.com",
    "toRecipients": ["user@company.com"],
    "ccRecipients": [],
    "date": "Mon, 12 May 2025 14:30:00 +0000",
    "body": HYDRATED_BODY,
    "attachmentIds": ["att-001"],
    "omittedFromThread": False,
}

HYDRATED_THREAD_SNAPSHOT = {
    "id": "thread-xyz",
    "messages": [HYDRATED_MESSAGE_SNAPSHOT],
}

GET_THREADS_SNAPSHOT = {
    "threads": [HYDRATED_THREAD_SNAPSHOT],
    "errors": [
        {
            "threadId": "thread-missing",
            "message": "Thread not found: thread-missing",
            "code": "NOT_FOUND",
        }
    ],
    "meta": {
        "requestedCount": 2,
        "successCount": 1,
        "errorCount": 1,
        "gmailApiCalls": 2,
        "quotaUnitsEstimated": 80,
        "totalChars": len(HYDRATED_BODY),
        "truncated": False,
    },
}


def test_triage_message_schema_snapshot() -> None:
    msg = TriageMessage(
        id="msg-abc",
        snippet="Thanks for the update…",
        subject="Re: Project status",
        sender="colleague@company.com",
        to_recipients=["user@company.com"],
        date="Mon, 12 May 2025 14:30:00 +0000",
    )
    assert hydration_to_json(msg) == TRIAGE_MESSAGE_SNAPSHOT


def test_triage_thread_schema_snapshot() -> None:
    thread = TriageThread(
        id="thread-xyz",
        messages=[TriageMessage(**{k: v for k, v in TRIAGE_MESSAGE_SNAPSHOT.items()})],
    )
    assert hydration_to_json(thread) == TRIAGE_THREAD_SNAPSHOT


def test_hydrated_message_schema_snapshot() -> None:
    msg = HydratedMessage(
        id="msg-abc",
        subject="Re: Project status",
        sender="colleague@company.com",
        to_recipients=["user@company.com"],
        date="Mon, 12 May 2025 14:30:00 +0000",
        body=HYDRATED_BODY,
        attachment_ids=["att-001"],
    )
    assert hydration_to_json(msg) == HYDRATED_MESSAGE_SNAPSHOT


def test_hydrated_thread_schema_snapshot() -> None:
    thread = HydratedThread(
        id="thread-xyz",
        messages=[
            HydratedMessage(
                id="msg-abc",
                subject="Re: Project status",
                sender="colleague@company.com",
                to_recipients=["user@company.com"],
                date="Mon, 12 May 2025 14:30:00 +0000",
                body=HYDRATED_BODY,
                attachment_ids=["att-001"],
            )
        ],
    )
    assert hydration_to_json(thread) == HYDRATED_THREAD_SNAPSHOT


def test_get_threads_response_schema_snapshot() -> None:
    result = HydrateResult(
        threads=[
            HydratedThread(
                id="thread-xyz",
                messages=[
                    HydratedMessage(
                        id="msg-abc",
                        subject="Re: Project status",
                        sender="colleague@company.com",
                        to_recipients=["user@company.com"],
                        date="Mon, 12 May 2025 14:30:00 +0000",
                        body=HYDRATED_BODY,
                        attachment_ids=["att-001"],
                    )
                ],
            )
        ],
        errors=[
            HydrateError(
                thread_id="thread-missing",
                message="Thread not found: thread-missing",
                code="NOT_FOUND",
            )
        ],
        meta=HydrateMeta(
            requested_count=2,
            success_count=1,
            error_count=1,
            gmail_api_calls=2,
            quota_units_estimated=80,
            total_chars=len(HYDRATED_BODY),
        ),
    )
    assert hydration_to_json(result) == GET_THREADS_SNAPSHOT


def test_triage_thread_from_api_strips_legacy_body_fields() -> None:
    api_thread = {
        "id": "thread-xyz",
        "messages": [
            {
                "id": "msg-abc",
                "snippet": "Thanks for the update…",
                "subject": "Re: Project status",
                "sender": "colleague@company.com",
                "toRecipients": ["user@company.com"],
                "ccRecipients": [],
                "date": "Mon, 12 May 2025 14:30:00 +0000",
                "plaintextBody": None,
                "htmlBody": None,
                "attachmentIds": [],
            }
        ],
    }
    assert hydration_to_json(triage_thread_from_api_thread(api_thread)) == TRIAGE_THREAD_SNAPSHOT


def test_read_tools_have_no_message_format_param() -> None:
    for tool in asyncio.run(mcp.list_tools()):
        if tool.name not in ("get_thread", "get_threads", "search_threads"):
            continue
        schema = json.dumps(tool.inputSchema)
        assert "messageFormat" not in schema
        assert "FULL_CONTENT" not in schema
