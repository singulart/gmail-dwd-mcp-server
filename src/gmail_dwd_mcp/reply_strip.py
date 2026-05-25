"""Quoted-reply and generic signature stripping for hydration (email-reply-parser)."""

from __future__ import annotations

import re

from email_reply_parser import EmailReplyParser

# Gmail quote containers and blockquotes before HTML-to-text (see TASK-B3).
_GMAIL_QUOTE_DIV = re.compile(
    r'<div[^>]*\bgmail_quote\b[^>]*>.*?</div>',
    re.IGNORECASE | re.DOTALL,
)
_BLOCKQUOTE = re.compile(
    r"<blockquote\b[^>]*>.*?</blockquote>",
    re.IGNORECASE | re.DOTALL,
)


def strip_html_quote_regions(html: str) -> str:
    """Remove obvious HTML quote regions before converting HTML to plain text."""
    text = _GMAIL_QUOTE_DIV.sub("", html)
    return _BLOCKQUOTE.sub("", text)


def strip_reply_content(text: str, *, is_first_in_thread: bool) -> str:
    """Return visible reply text without quoted prior messages or ``--`` signatures.

    When ``is_first_in_thread`` is True, returns ``text`` unchanged (no prior thread
    quotes; trailing signatures on opening messages are kept in v1).

    When the entire body is a quote, ``parse_reply`` returns an empty string.
    """
    if is_first_in_thread:
        return text
    if not text or not text.strip():
        return text
    return EmailReplyParser.parse_reply(text).strip()
