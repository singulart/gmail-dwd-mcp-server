"""Domain types for LLM-oriented thread hydration (triage vs hydrated read paths)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Conservative defaults for hydrate tools (TASK-B5 applies these on the read path).
DEFAULT_MESSAGE_LIMIT = 20
DEFAULT_MAX_BODY_CHARS = 16_000


class _CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class HydrationOptions(_CamelModel):
    """Options for get_thread / get_threads (hydrate path only)."""

    strip_quoted_content: bool = Field(default=True, alias="stripQuotedContent")
    message_limit: int = Field(
        default=DEFAULT_MESSAGE_LIMIT,
        ge=1,
        alias="messageLimit",
        description="Keep newest N messages per thread.",
    )
    max_body_chars: int = Field(
        default=DEFAULT_MAX_BODY_CHARS,
        ge=1,
        alias="maxBodyChars",
        description="Per-message body character ceiling after normalization.",
    )
    total_max_chars: int | None = Field(
        default=None,
        ge=1,
        alias="totalMaxChars",
        description="Optional global cap across threads in one batch (TASK-B6). None disables.",
    )
    include_attachment_ids: bool = Field(default=True, alias="includeAttachmentIds")


class TriageMessage(_CamelModel):
    """Per-message triage fields when enriched elsewhere; search_threads uses ids only."""

    id: str
    snippet: str | None = None
    subject: str | None = None
    sender: str | None = None
    to_recipients: list[str] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[str] = Field(default_factory=list, alias="ccRecipients")
    date: str | None = None


class TriageThread(_CamelModel):
    id: str
    messages: list[TriageMessage] = Field(default_factory=list)


class HydratedMessage(_CamelModel):
    """get_thread / get_threads message: normalized plain text in body only."""

    id: str
    subject: str | None = None
    sender: str | None = None
    to_recipients: list[str] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[str] = Field(default_factory=list, alias="ccRecipients")
    date: str | None = None
    body: str = ""
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")
    omitted_from_thread: bool = Field(
        default=False,
        alias="omittedFromThread",
        description="True when message exceeds messageLimit (metadata only, empty body).",
    )


class HydratedThread(_CamelModel):
    id: str
    messages: list[HydratedMessage] = Field(default_factory=list)


class HydrateError(_CamelModel):
    thread_id: str = Field(alias="threadId")
    message: str
    code: str | None = None


class HydrateMeta(_CamelModel):
    requested_count: int = Field(default=0, alias="requestedCount")
    success_count: int = Field(default=0, alias="successCount")
    error_count: int = Field(default=0, alias="errorCount")
    gmail_api_calls: int = Field(default=0, alias="gmailApiCalls")
    quota_units_estimated: int = Field(default=0, alias="quotaUnitsEstimated")
    total_chars: int = Field(default=0, alias="totalChars")
    truncated: bool = False


class HydrateResult(_CamelModel):
    threads: list[HydratedThread] = Field(default_factory=list)
    errors: list[HydrateError] = Field(default_factory=list)
    meta: HydrateMeta = Field(default_factory=HydrateMeta)


class SearchThreadsResult(_CamelModel):
    """search_threads response: thread ids for discovery. Hydrate separately."""

    threads: list[TriageThread] = Field(default_factory=list)
    next_page_token: str | None = Field(default=None, alias="nextPageToken")


def hydration_to_json(model: BaseModel) -> dict[str, Any]:
    """Serialize hydration models for MCP tool responses (camelCase, omit nulls)."""
    return model.model_dump(by_alias=True, exclude_none=True)


def triage_thread_from_list_summary(summary: dict[str, Any]) -> TriageThread:
    """Minimal triage row from ``threads.list`` (thread id only, no per-message fetch)."""
    return TriageThread(id=summary["id"], messages=[])


def triage_thread_from_api_thread(thread: dict[str, Any]) -> TriageThread:
    """Map a Gmail API thread dict (metadata messages) to :class:`TriageThread`."""
    messages: list[TriageMessage] = []
    for msg in thread.get("messages") or []:
        messages.append(
            TriageMessage(
                id=msg["id"],
                snippet=msg.get("snippet"),
                subject=msg.get("subject"),
                sender=msg.get("sender"),
                to_recipients=msg.get("toRecipients") or [],
                cc_recipients=msg.get("ccRecipients") or [],
                date=msg.get("date"),
            )
        )
    return TriageThread(id=thread["id"], messages=messages)
