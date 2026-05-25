from __future__ import annotations

from gmail_dwd_mcp.body_extraction import extract_body
from tests.fixture_loader import b64_text, load_fixture, load_fixture_raw


def test_body_text_materializes_to_gmail_body_data() -> None:
    raw = load_fixture_raw("plain_only.py")
    assert raw["payload"]["bodyText"] == "Hello, world!"
    assert "body" not in raw["payload"]

    payload = load_fixture("plain_only.py")["payload"]
    assert payload["body"]["data"] == b64_text("Hello, world!")
    assert payload["body"]["size"] == len("Hello, world!".encode("utf-8"))


def test_materialized_fixtures_work_with_extract_body() -> None:
    assert extract_body(load_fixture("plain_only.py")["payload"]) == "Hello, world!"
    assert extract_body(load_fixture("multipart_alternative.py")["payload"]) == "Plain version"
