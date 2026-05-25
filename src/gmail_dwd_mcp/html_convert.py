"""HTML-to-text for hydration. TASK-B2 will replace the implementation with html2text."""

from __future__ import annotations

from gmail_dwd_mcp.mime import html_to_plain


def convert_html_to_text(html: str) -> str:
    """Convert HTML email body to plain text (link anchor text is retained; URLs are dropped)."""
    return html_to_plain(html)
