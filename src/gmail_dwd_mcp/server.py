from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from gmail_dwd_mcp.auth import WifConfigCache
from gmail_dwd_mcp.config import Settings
from gmail_dwd_mcp.gmail_fetch import (
    get_thread_fetch_executor,
    shutdown_thread_fetch_executor,
)
from gmail_dwd_mcp.gmail_service import GmailService
from gmail_dwd_mcp.hydrate_tools import (
    hydrate_batch_response,
    hydrated_thread_response,
    hydration_options_from_tool,
    validate_hydrate_batch_size,
)
from gmail_dwd_mcp.telemetry import setup_telemetry, tool_span
from gmail_dwd_mcp.hydration import HydrateResult, HydratedThread, SearchThreadsResult
from gmail_dwd_mcp.thread_hydrator import ThreadHydrator

READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
WRITE = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=False,
    openWorldHint=False,
)
WRITE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
DESTRUCTIVE_IDEMPOTENT = ToolAnnotations(
    readOnlyHint=False,
    destructiveHint=True,
    idempotentHint=True,
    openWorldHint=False,
)


@dataclass
class AppContext:
    gmail: GmailService
    hydrator: ThreadHydrator
    max_batch_size: int


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings.from_env()
    get_thread_fetch_executor(max_workers=settings.gmail_hydrate_max_concurrency)
    wif_cache = WifConfigCache(settings)
    gmail = GmailService(wif_cache)
    hydrator = ThreadHydrator(get_service=gmail._service)
    try:
        yield AppContext(
            gmail=gmail,
            hydrator=hydrator,
            max_batch_size=settings.gmail_hydrate_max_batch_size,
        )
    finally:
        shutdown_thread_fetch_executor()


mcp = FastMCP(
    "Gmail DWD MCP Server",
    json_response=True,
    stateless_http=True,
    host="0.0.0.0",
    lifespan=app_lifespan,
)


def _gmail(ctx: Context[ServerSession, AppContext]) -> GmailService:
    return ctx.request_context.lifespan_context.gmail


def _hydrator(ctx: Context[ServerSession, AppContext]) -> ThreadHydrator:
    return ctx.request_context.lifespan_context.hydrator


@mcp.tool(annotations=READ_ONLY)
def search_threads(
    email: str,
    ctx: Context[ServerSession, AppContext],
    query: str | None = None,
    pageSize: int | None = None,
    pageToken: str | None = None,
    includeTrash: bool | None = None,
) -> SearchThreadsResult:
    """Lists email threads from a user's Gmail account.  
    If response includes a `nextPageToken`, you can use it to fetch the next page of threads.
    Returns SearchThread rows (id, snippet) from threads.list — no messages array.
    Use get_threads to hydrate full text.

    Filter threads using `query`; syntax described below:
    
| **Search operator**                                       | **Description**                                                                                                                                                                      | **Example**                                                                                                                       |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------- |
| `from:`                                                   | Find emails sent from a specific person.                                                                                                                                             | `from:me`        `from:amy@example.com`                                                                                           |
| `to:`                                                     | Find emails sent to a specific person.                                                                                                                                               | `to:me`        `to:john@example.com`                                                                                              |
| `cc:` `bcc:`                                              | Find emails that include specific people in the "Cc" or "Bcc" fields.                                                                                                                | `cc:john@example.com`        `bcc:david@example.com`                                                                              |
| `subject:`                                                | Find emails by a word or phrase in the subject line.                                                                                                                                 | `subject:dinner`        `subject:anniversary party`                                                                               |
| `after:` `before:` `older:` `newer:`                      | Search for emails received during a certain time period.                                                                                                                             | `after:2004/04/16`        `after:04/16/2004`        `before:2004/04/18`        `before:04/18/2004`                                |
| `older_than:`        `newer_than:`                        | Search for emails older or newer than a time period. Use `d` (day), `m` (month), or `y` (year).                                                                                      | `older_than:1y`        `newer_than:2d`                                                                                            |
| `OR` or `{ }`                                             | Find emails that match one or more of your search criteria.                                                                                                                          | `from:amy OR from:david`        `{from:amy from:david}`                                                                           |
| `AND`                                                     | Find emails that match all of your search criteria.                                                                                                                                  | `from:amy AND to:david`                                                                                                           |
| `-`                                                       | Exclude emails from your search criteria.                                                                                                                                            | `dinner -movie`                                                                                                                   |
| `AROUND`                                                  | Find emails with words near each other. Use the number to say how many words apart the words can be.        Add quotes to find messages in which the word you put first stays first. | `holiday AROUND 10 vacation`        `"secret AROUND 25 birthday"`                                                                 |
| `label:`                                                  | Find emails under one of your labels.                                                                                                                                                | `label:friends`        `label:important`                                                                                          |
| `has:`                                                    | Find emails that include:        *   Attachments*   Inline images*   YouTube videos*   Drive files*   Google Docs*   Google Sheets<br>*   Google Slides          | `has:attachment`        `has:youtube`        `has:drive`        `has:document`        `has:spreadsheet`        `has:presentation` |
| `filename:`                                               | Find emails that have attachments with a certain name or file type.                                                                                                                  | `filename:pdf`        `filename:homework.txt`                                                                                     |
| `" "`                                                     | Search for emails with an exact word or phrase.                                                                                                                                      | `"dinner and movie tonight"`                                                                                                      |
| `( )`                                                     | Group multiple search terms together.                                                                                                                                                | `subject:(dinner movie)`                                                                                                          |
| `is:`                                                     | Search for emails by their status:        *   Important<br>*   Starred<br>*   Unread<br>*   Read                                                                                     | `is:important`        `is:starred`        `is:unread`        `is:read`                                                            |
| `+`                                                       | Find emails that match a word exactly.                                                                                                                                               | `+unicorn`                                                                                                                        |
| `rfc822msgid`                                             | Find emails with a specific message-id header.                                                                                                                                       | `rfc822msgid:200503292@example.com`                                                                                               |
    """
    with tool_span("search_threads", email=email):
        return _gmail(ctx).search_threads(
            email,
            query=query,
            page_size=pageSize,
            page_token=pageToken,
            include_trash=includeTrash,
        )


@mcp.tool(annotations=READ_ONLY)
def get_thread(
    email: str,
    threadId: str,
    ctx: Context[ServerSession, AppContext],
    stripQuotedContent: bool | None = None,
    messageLimit: int | None = None,
    maxBodyChars: int | None = None,
    totalMaxChars: int | None = None,
) -> HydratedThread:
    """Retrieves a normalized email thread for LLM consumption (plain text in body)."""
    options = hydration_options_from_tool(
        strip_quoted_content=stripQuotedContent,
        message_limit=messageLimit,
        max_body_chars=maxBodyChars,
        total_max_chars=totalMaxChars,
    )
    with tool_span("get_thread", email=email):
        result = _hydrator(ctx).hydrate(email, [threadId], options)
        return hydrated_thread_response(result)


@mcp.tool(annotations=READ_ONLY)
def get_threads(
    email: str,
    threadIds: list[str],
    ctx: Context[ServerSession, AppContext],
    stripQuotedContent: bool | None = None,
    messageLimit: int | None = None,
    maxBodyChars: int | None = None,
    totalMaxChars: int | None = None,
    includeAttachmentIds: bool | None = None,
) -> HydrateResult:
    """Retrieves multiple normalized email threads (partial success: threads, errors, meta)."""
    lifespan = ctx.request_context.lifespan_context
    validate_hydrate_batch_size(threadIds, lifespan.max_batch_size)
    options = hydration_options_from_tool(
        strip_quoted_content=stripQuotedContent,
        message_limit=messageLimit,
        max_body_chars=maxBodyChars,
        total_max_chars=totalMaxChars,
        include_attachment_ids=includeAttachmentIds,
    )
    with tool_span("get_threads", email=email):
        result = _hydrator(ctx).hydrate(email, threadIds, options)
        return hydrate_batch_response(result)


@mcp.tool(annotations=WRITE)
def list_drafts(
    email: str,
    ctx: Context[ServerSession, AppContext],
    query: str | None = None,
    pageSize: int | None = None,
    pageToken: str | None = None,
) -> dict[str, Any]:
    """Lists draft emails from a user's Gmail account."""
    with tool_span("list_drafts", email=email):
        return _gmail(ctx).list_drafts(
            email,
            query=query,
            page_size=pageSize,
            page_token=pageToken,
        )


@mcp.tool(annotations=WRITE)
def create_draft(
    email: str,
    to: list[str],
    ctx: Context[ServerSession, AppContext],
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    subject: str | None = None,
    body: str | None = None,
    htmlBody: str | None = None,
    replyToMessageId: str | None = None,
) -> dict[str, Any]:
    """Creates a new draft email in the user's Gmail account."""
    with tool_span("create_draft", email=email):
        return _gmail(ctx).create_draft(
            email,
            to=to,
            cc=cc,
            bcc=bcc,
            subject=subject,
            body=body,
            html_body=htmlBody,
            reply_to_message_id=replyToMessageId,
        )


@mcp.tool(annotations=READ_ONLY)
def list_labels(
    email: str,
    ctx: Context[ServerSession, AppContext],
    pageSize: int | None = None,
    pageToken: str | None = None,
) -> dict[str, Any]:
    """Lists user-defined labels. System labels use well-known IDs (INBOX, TRASH, etc.)."""
    with tool_span("list_labels", email=email):
        return _gmail(ctx).list_labels(
            email,
            page_size=pageSize,
            page_token=pageToken,
        )


@mcp.tool(annotations=WRITE)
def create_label(
    email: str,
    displayName: str,
    ctx: Context[ServerSession, AppContext],
    color: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Creates a new label in the user's Gmail account."""
    with tool_span("create_label", email=email):
        return _gmail(ctx).create_label(
            email,
            display_name=displayName,
            color=color,
        )


@mcp.tool(annotations=WRITE_IDEMPOTENT)
def label_message(
    email: str,
    messageId: str,
    labelIds: list[str],
    ctx: Context[ServerSession, AppContext],
) -> dict[str, Any]:
    """Adds one or more labels to a specific message."""
    with tool_span("label_message", email=email):
        return _gmail(ctx).label_message(
            email,
            message_id=messageId,
            label_ids=labelIds,
        )


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT)
def unlabel_message(
    email: str,
    messageId: str,
    labelIds: list[str],
    ctx: Context[ServerSession, AppContext],
) -> dict[str, Any]:
    """Removes one or more labels from a specific message."""
    with tool_span("unlabel_message", email=email):
        return _gmail(ctx).unlabel_message(
            email,
            message_id=messageId,
            label_ids=labelIds,
        )


@mcp.tool(annotations=WRITE_IDEMPOTENT)
def label_thread(
    email: str,
    threadId: str,
    labelIds: list[str],
    ctx: Context[ServerSession, AppContext],
) -> dict[str, Any]:
    """Adds labels to an entire thread (all current and future messages)."""
    with tool_span("label_thread", email=email):
        return _gmail(ctx).label_thread(
            email,
            thread_id=threadId,
            label_ids=labelIds,
        )


@mcp.tool(annotations=DESTRUCTIVE_IDEMPOTENT)
def unlabel_thread(
    email: str,
    threadId: str,
    labelIds: list[str],
    ctx: Context[ServerSession, AppContext],
) -> dict[str, Any]:
    """Removes labels from an entire thread."""
    with tool_span("unlabel_thread", email=email):
        return _gmail(ctx).unlabel_thread(
            email,
            thread_id=threadId,
            label_ids=labelIds,
        )


def main() -> None:
    setup_telemetry()
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    if transport not in ("stdio", "sse", "streamable-http"):
        raise SystemExit(f"Invalid MCP_TRANSPORT: {transport!r}")
    mcp.run(transport=transport)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
