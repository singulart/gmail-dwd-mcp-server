from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from gmail_dwd_mcp.allowed_hosts import AllowedHostsCache
from gmail_dwd_mcp.auth import WifConfigCache
from gmail_dwd_mcp.config import Settings
from gmail_dwd_mcp.gmail_service import GmailService
from gmail_dwd_mcp.models import MessageFormat

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


@asynccontextmanager
async def app_lifespan(_server: FastMCP) -> AsyncIterator[AppContext]:
    settings = Settings.from_env()
    wif_cache = WifConfigCache(settings)
    gmail = GmailService(wif_cache)
    yield AppContext(gmail=gmail)


def _transport_security() -> TransportSecuritySettings | None:
    """Configure MCP DNS rebinding checks from SSM (HTTP only)."""
    param = os.environ.get("GMAIL_ALLOWED_HOSTS_SSM_PARAMETER")
    if not param:
        return None

    ttl = int(os.environ.get("GMAIL_WIF_CACHE_TTL_SECONDS", "3600"))
    cache = AllowedHostsCache(
        param,
        aws_region=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
        ttl_seconds=max(ttl, 0),
    )
    hosts = cache.get_hosts()
    if not hosts:
        return None

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
    )


mcp = FastMCP(
    "Gmail DWD MCP Server",
    json_response=True,
    stateless_http=True,
    host="0.0.0.0",
    transport_security=_transport_security(),
    lifespan=app_lifespan,
)


def _gmail(ctx: Context[ServerSession, AppContext]) -> GmailService:
    return ctx.request_context.lifespan_context.gmail


@mcp.tool(annotations=READ_ONLY)
def search_threads(
    email: str,
    ctx: Context[ServerSession, AppContext],
    query: str | None = None,
    pageSize: int | None = None,
    pageToken: str | None = None,
    includeTrash: bool | None = None,
) -> dict[str, Any]:
    """Lists email threads from a user's Gmail account (domain-wide delegation).

    Filters threads by Gmail query syntax and supports pagination. Returns thread
    IDs and message summaries (not full bodies). Use get_thread for full content.
    """
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
    messageFormat: MessageFormat | None = None,
) -> dict[str, Any]:
    """Retrieves a specific email thread including its messages."""
    return _gmail(ctx).get_thread(
        email,
        thread_id=threadId,
        message_format=messageFormat,
    )


@mcp.tool(annotations=WRITE)
def list_drafts(
    email: str,
    ctx: Context[ServerSession, AppContext],
    query: str | None = None,
    pageSize: int | None = None,
    pageToken: str | None = None,
) -> dict[str, Any]:
    """Lists draft emails from a user's Gmail account."""
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
    return _gmail(ctx).unlabel_thread(
        email,
        thread_id=threadId,
        label_ids=labelIds,
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
