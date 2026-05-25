"""HTML-to-text conversion for the hydration pipeline (html2text)."""

from __future__ import annotations

import html2text


def _new_converter() -> html2text.HTML2Text:
    converter = html2text.HTML2Text()
    converter.ignore_links = True
    converter.ignore_images = True
    converter.ignore_emphasis = True
    converter.body_width = 0
    return converter


_CONVERTER = _new_converter()


def convert_html_to_text(html: str) -> str:
    """Convert HTML email body to plain text.

    Link anchor text is retained; URLs are not emitted (ignore_links).
    Script/style blocks are skipped by html2text.
    """
    if not html or not html.strip():
        return ""
    return _CONVERTER.handle(html).strip()
