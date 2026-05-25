from __future__ import annotations

import pytest

from gmail_dwd_mcp.body_extraction import extract_body
from gmail_dwd_mcp.html_convert import convert_html_to_text
from tests.conftest import load_payload_fixture
from tests.fixture_loader import load_fixture_raw

MAX_EXPANSION_RATIO = 3


@pytest.mark.parametrize(
    ("html", "expected_substrings"),
    [
        ("<table><tr><td>Cell A</td><td>Cell B</td></tr></table>", ["Cell A", "Cell B"]),
        ("<div>Line one<br>Line two</div>", ["Line one", "Line two"]),
        (
            "<div><p>Outer</p><div><span>Inner</span></div></div>",
            ["Outer", "Inner"],
        ),
    ],
)
def test_convert_html_inline_samples(html: str, expected_substrings: list[str]) -> None:
    text = convert_html_to_text(html)
    for part in expected_substrings:
        assert part in text


def test_convert_html_fixture_html_only() -> None:
    text = convert_html_to_text(_fixture_body_text("html_only.py"))
    assert "Hello" in text
    assert "click here" in text
    assert "example.com" not in text


def test_convert_html_fixture_marketing() -> None:
    text = convert_html_to_text(_fixture_body_text("html_marketing.py"))
    assert "Summer Sale" in text
    assert "SAVE50" in text
    assert "Shop now" in text
    assert "cdn.example" not in text


def test_extract_body_uses_html2text_for_html_only() -> None:
    assert extract_body(load_payload_fixture("html_only.py")) == "Hello click here"


def test_convert_html_output_length_bounded() -> None:
    depth = 200
    html = "<div>" * depth + "nested" + "</div>" * depth
    text = convert_html_to_text(html)
    assert len(text) <= len(html) * MAX_EXPANSION_RATIO
    assert "nested" in text


def test_convert_html_empty_input() -> None:
    assert convert_html_to_text("") == ""
    assert convert_html_to_text("   \n  ") == ""


def _fixture_body_text(fixture_name: str) -> str:
    raw = load_fixture_raw(fixture_name)
    payload = raw.get("payload", raw)
    return payload["bodyText"]
