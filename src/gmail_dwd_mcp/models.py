from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LabelColor(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    text_color: str | None = Field(default=None, alias="textColor")
    background_color: str | None = Field(default=None, alias="backgroundColor")


class Label(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    label_id: str = Field(alias="labelId")
    name: str
    color: LabelColor | None = None
    threads_total: int | None = Field(default=None, alias="threadsTotal")
    threads_unread: int | None = Field(default=None, alias="threadsUnread")


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    snippet: str | None = None
    subject: str | None = None
    sender: str | None = None
    to_recipients: list[str] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[str] = Field(default_factory=list, alias="ccRecipients")
    date: str | None = None
    plaintext_body: str | None = Field(default=None, alias="plaintextBody")
    html_body: str | None = Field(default=None, alias="htmlBody")
    attachment_ids: list[str] = Field(default_factory=list, alias="attachmentIds")


class Thread(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    messages: list[Message] = Field(default_factory=list)


class Draft(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    subject: str | None = None
    thread_id: str | None = Field(default=None, alias="threadId")
    to_recipients: list[str] = Field(default_factory=list, alias="toRecipients")
    cc_recipients: list[str] = Field(default_factory=list, alias="ccRecipients")
    bcc_recipients: list[str] = Field(default_factory=list, alias="bccRecipients")
    plaintext_body: str | None = Field(default=None, alias="plaintextBody")
    html_body: str | None = Field(default=None, alias="htmlBody")
    date: str | None = None


def pydantic_to_json(model: BaseModel | None) -> dict[str, Any]:
    if model is None:
        return {}
    return model.model_dump(by_alias=True, exclude_none=True)
