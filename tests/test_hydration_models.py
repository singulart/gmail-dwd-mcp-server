from __future__ import annotations

import pytest
from pydantic import ValidationError

from gmail_dwd_mcp.hydration import (
    DEFAULT_MAX_BODY_CHARS,
    DEFAULT_MESSAGE_LIMIT,
    HydrateError,
    HydrateMeta,
    HydrateResult,
    HydratedMessage,
    HydratedThread,
    HydrationOptions,
    TriageMessage,
    TriageThread,
    hydration_to_json,
)


def test_hydration_options_defaults_camel_case() -> None:
    opts = HydrationOptions()
    data = opts.model_dump(by_alias=True, exclude_none=True)
    assert data == {
        "stripQuotedContent": True,
        "messageLimit": DEFAULT_MESSAGE_LIMIT,
        "maxBodyChars": DEFAULT_MAX_BODY_CHARS,
        "includeAttachmentIds": True,
    }
    assert opts.total_max_chars is None
    assert "totalMaxChars" not in data


def test_hydration_options_total_max_chars_none_and_set() -> None:
    assert HydrationOptions(total_max_chars=None).total_max_chars is None
    assert HydrationOptions.model_validate(
        {"totalMaxChars": None, "messageLimit": 5}
    ).total_max_chars is None

    opts = HydrationOptions(total_max_chars=80_000)
    assert opts.model_dump(by_alias=True)["totalMaxChars"] == 80_000


def test_hydration_options_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        HydrationOptions(message_limit=0)
    with pytest.raises(ValidationError):
        HydrationOptions(max_body_chars=0)
    with pytest.raises(ValidationError):
        HydrationOptions(total_max_chars=0)


def test_hydrated_message_has_body_only_no_legacy_body_fields() -> None:
    fields = set(HydratedMessage.model_fields)
    assert "body" in fields
    assert "html_body" not in fields
    assert "plaintext_body" not in fields
    assert "htmlBody" not in fields
    assert "plaintextBody" not in fields


def test_hydrated_message_serializes_camel_case() -> None:
    msg = HydratedMessage(
        id="m1",
        subject="Hi",
        sender="a@example.com",
        to_recipients=["b@example.com"],
        body="Hello",
        attachment_ids=["att-1"],
        omitted_from_thread=True,
    )
    assert msg.model_dump(by_alias=True) == {
        "id": "m1",
        "subject": "Hi",
        "sender": "a@example.com",
        "toRecipients": ["b@example.com"],
        "ccRecipients": [],
        "date": None,
        "body": "Hello",
        "attachmentIds": ["att-1"],
        "omittedFromThread": True,
    }


def test_triage_message_no_body_fields() -> None:
    fields = set(TriageMessage.model_fields)
    assert "snippet" in fields
    assert "body" not in fields
    assert "html_body" not in fields
    assert "plaintext_body" not in fields

    triage = TriageMessage(
        id="m1",
        snippet="preview",
        subject="Subj",
        sender="a@example.com",
    )
    dumped = triage.model_dump(by_alias=True)
    assert "body" not in dumped
    assert "htmlBody" not in dumped
    assert dumped["snippet"] == "preview"


def test_triage_thread_and_hydrated_thread_camel_case() -> None:
    triage = TriageThread(id="t1", messages=[TriageMessage(id="m1", snippet="s")])
    assert triage.model_dump(by_alias=True)["messages"][0]["id"] == "m1"

    hydrated = HydratedThread(
        id="t1",
        messages=[HydratedMessage(id="m1", body="text")],
    )
    assert hydrated.model_dump(by_alias=True)["messages"][0]["body"] == "text"


def test_hydrate_result_round_trip() -> None:
    result = HydrateResult(
        threads=[HydratedThread(id="t1", messages=[HydratedMessage(id="m1", body="x")])],
        errors=[HydrateError(thread_id="t2", message="not found", code="NOT_FOUND")],
        meta=HydrateMeta(
            requested_count=2,
            success_count=1,
            error_count=1,
            gmail_api_calls=1,
            quota_units_estimated=5,
            total_chars=42,
            truncated=True,
        ),
    )
    data = hydration_to_json(result)
    assert data["meta"]["totalChars"] == 42
    assert data["meta"]["truncated"] is True
    assert data["errors"][0]["threadId"] == "t2"
    assert data["errors"][0]["code"] == "NOT_FOUND"
    assert data["threads"][0]["messages"][0]["body"] == "x"
    assert "plaintextBody" not in str(data)
