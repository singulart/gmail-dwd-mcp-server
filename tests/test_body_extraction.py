from __future__ import annotations

import pytest

from gmail_dwd_mcp.body_extraction import extract_body
from gmail_dwd_mcp.mime import (
    append_html_signature,
    append_plain_signature,
    html_to_plain,
    message_from_gmail_api,
    plain_to_html,
)
from tests.conftest import b64_text, load_payload_fixture

PAYLOAD_FIXTURES = [
    ("plain_only.py", "Hello, world!"),
    ("html_only.py", "Hello click here"),
    ("multipart_alternative.py", "Plain version"),
    ("nested_multipart.py", "Nested plain body"),
]


@pytest.mark.parametrize("fixture_name,expected", PAYLOAD_FIXTURES)
def test_extract_body_from_fixtures(fixture_name: str, expected: str) -> None:
    payload = load_payload_fixture(fixture_name)
    assert extract_body(payload) == expected


def test_extract_body_html_only_link_text_not_url() -> None:
    payload = {
        "mimeType": "text/html",
        "body": {"data": b64_text('<p>See <a href="https://secret.example/x">docs</a></p>')},
    }
    body = extract_body(payload)
    assert "docs" in body
    assert "secret.example" not in body


def test_extract_body_skips_attachment_parts() -> None:
    payload = load_payload_fixture("nested_multipart.py")
    assert "report.pdf" not in extract_body(payload)


def test_extract_body_empty_payload() -> None:
    assert extract_body({}) == ""
    assert extract_body({"mimeType": "text/plain", "body": {}}) == ""


def test_mime_helpers_unchanged() -> None:
    assert html_to_plain("<p>Hi</p>") == "Hi"
    assert plain_to_html("Hi") == "<div>Hi</div>"
    assert append_plain_signature("Hi", "Sig") == "Hi\n\nSig"
    assert append_html_signature("<p>Hi</p>", "<i>Sig</i>") == "<p>Hi</p><br><br><i>Sig</i>"


def test_message_from_gmail_api_inline_payload_unchanged() -> None:
    msg = {
        "id": "m1",
        "snippet": "x",
        "payload": {
            "mimeType": "text/plain",
            "headers": [{"name": "Subject", "value": "S"}],
            "body": {"data": b64_text("Body text")},
        },
    }
    parsed = message_from_gmail_api(msg, full_content=True)
    assert parsed["plaintextBody"] == "Body text"
    assert parsed["htmlBody"] is None
