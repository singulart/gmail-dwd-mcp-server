from __future__ import annotations

import pytest

from gmail_dwd_mcp.body_extraction import extract_body
from gmail_dwd_mcp.reply_strip import strip_html_quote_regions, strip_reply_content
from tests.conftest import load_payload_fixture


def test_strip_reply_gmail_quote_fixture() -> None:
    body = extract_body(load_payload_fixture("gmail_quote.py"))
    result = strip_reply_content(body, is_first_in_thread=False)
    assert result == "Thanks for the update."
    assert "wrote:" not in result
    assert "Can we meet tomorrow" not in result


def test_strip_reply_outlook_fixture() -> None:
    body = extract_body(load_payload_fixture("outlook_quoted_reply.py"))
    result = strip_reply_content(body, is_first_in_thread=False)
    assert result == "Sounds good to me."
    assert "Original Message" not in result
    assert "Can we meet tomorrow" not in result


def test_strip_reply_plain_signature_fixture() -> None:
    body = extract_body(load_payload_fixture("plain_signature.py"))
    result = strip_reply_content(body, is_first_in_thread=False)
    assert result == "My reply text."
    assert "Jane Doe" not in result
    assert "VP Sales" not in result


def test_strip_reply_first_message_unchanged() -> None:
    body = extract_body(load_payload_fixture("outlook_quoted_reply.py"))
    assert strip_reply_content(body, is_first_in_thread=True) == body

    with_signature = "Welcome to the thread.\n\n--\nBob"
    assert strip_reply_content(with_signature, is_first_in_thread=True) == with_signature


def test_strip_reply_entire_body_is_quote() -> None:
    quoted = """On Mon, Jan 1, 2024 at 9:00 AM Sender <sender@example.com> wrote:

> Can we meet tomorrow?"""
    assert strip_reply_content(quoted, is_first_in_thread=False) == ""


def test_strip_html_quote_regions_removes_gmail_div() -> None:
    html = """<p>Visible</p>
<div class="gmail_quote"><blockquote>Hidden</blockquote></div>"""
    assert "Hidden" not in strip_html_quote_regions(html)
    assert "<p>Visible</p>" in strip_html_quote_regions(html)


@pytest.mark.parametrize(
    ("html", "needle"),
    [
        ("""<p>Hi</p><div class="gmail_quote">quoted</div>""", "quoted"),
        ("""<p>Hi</p><blockquote type="cite">quoted</blockquote>""", "quoted"),
    ],
)
def test_extract_body_html_prepass_strips_quotes(html: str, needle: str) -> None:
    from tests.fixture_loader import materialize_payload

    payload = {"mimeType": "text/html", "bodyText": html}
    body = extract_body(materialize_payload(payload))
    assert needle not in body
    assert "Hi" in body
