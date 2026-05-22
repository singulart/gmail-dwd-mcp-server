from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build

from gmail_dwd_mcp.auth import WifConfigCache, credentials_for_user
from gmail_dwd_mcp.mime import message_from_gmail_api
from gmail_dwd_mcp.models import MessageFormat
from gmail_dwd_mcp.telemetry import traced_gmail_method


class GmailService:
    def __init__(self, wif_cache: WifConfigCache) -> None:
        self._wif_cache = wif_cache

    def _service(self, email: str):
        creds = credentials_for_user(self._wif_cache, email)
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    @traced_gmail_method
    def search_threads(
        self,
        email: str,
        *,
        query: str | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
        include_trash: bool | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        user_id = "me"
        max_results = min(page_size or 20, 50)
        list_query = query or ""
        if include_trash:
            if list_query:
                list_query = f"{list_query} in:anywhere"
            else:
                list_query = "in:anywhere"

        list_resp = (
            service.users()
            .threads()
            .list(userId=user_id, q=list_query or None, maxResults=max_results, pageToken=page_token)
            .execute()
        )
        threads_out: list[dict[str, Any]] = []
        for summary in list_resp.get("threads", []):
            thread = self._get_thread_internal(
                service,
                summary["id"],
                message_format=MessageFormat.MINIMAL,
            )
            threads_out.append(thread)

        result: dict[str, Any] = {"threads": threads_out}
        if list_resp.get("nextPageToken"):
            result["nextPageToken"] = list_resp["nextPageToken"]
        return result

    @traced_gmail_method
    def get_thread(
        self,
        email: str,
        *,
        thread_id: str,
        message_format: MessageFormat | str | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        fmt = self._resolve_format(message_format)
        return self._get_thread_internal(service, thread_id, message_format=fmt)

    def _get_thread_internal(
        self,
        service,
        thread_id: str,
        *,
        message_format: MessageFormat,
    ) -> dict[str, Any]:
        full_content = message_format != MessageFormat.MINIMAL
        fmt = "full" if full_content else "metadata"
        metadata_headers = ["Subject", "From", "To", "Cc", "Date"]
        thread = (
            service.users()
            .threads()
            .get(
                userId="me",
                id=thread_id,
                format=fmt,
                metadataHeaders=metadata_headers if fmt == "metadata" else None,
            )
            .execute()
        )
        messages: list[dict[str, Any]] = []
        for msg in thread.get("messages", []):
            if full_content and "raw" not in msg:
                full_msg = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="full")
                    .execute()
                )
                messages.append(message_from_gmail_api(full_msg, full_content=True))
            else:
                messages.append(message_from_gmail_api(msg, full_content=full_content))
        return {"id": thread["id"], "messages": messages}

    @traced_gmail_method
    def list_drafts(
        self,
        email: str,
        *,
        query: str | None = None,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        max_results = min(page_size or 20, 50)
        list_resp = (
            service.users()
            .drafts()
            .list(
                userId="me",
                q=query or None,
                maxResults=max_results,
                pageToken=page_token,
            )
            .execute()
        )
        drafts: list[dict[str, Any]] = []
        for item in list_resp.get("drafts", []):
            draft = (
                service.users()
                .drafts()
                .get(userId="me", id=item["id"], format="full")
                .execute()
            )
            drafts.append(self._draft_from_api(draft))
        result: dict[str, Any] = {"drafts": drafts}
        if list_resp.get("nextPageToken"):
            result["nextPageToken"] = list_resp["nextPageToken"]
        return result

    @traced_gmail_method
    def create_draft(
        self,
        email: str,
        *,
        to: list[str],
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        subject: str | None = None,
        body: str | None = None,
        html_body: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        message = self._build_mime(
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject or "",
            body=body,
            html_body=html_body,
        )
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        create_body: dict[str, Any] = {"message": {"raw": raw}}
        if reply_to_message_id:
            original = (
                service.users()
                .messages()
                .get(userId="me", id=reply_to_message_id, format="metadata")
                .execute()
            )
            create_body["message"]["threadId"] = original.get("threadId")

        created = service.users().drafts().create(userId="me", body=create_body).execute()
        full = (
            service.users()
            .drafts()
            .get(userId="me", id=created["id"], format="full")
            .execute()
        )
        return self._draft_from_api(full)

    @traced_gmail_method
    def list_labels(
        self,
        email: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        resp = service.users().labels().list(userId="me").execute()
        labels = [
            self._label_from_api(label)
            for label in resp.get("labels", [])
            if label.get("type") == "user"
        ]
        if page_token:
            start = int(page_token)
        else:
            start = 0
        end = start + page_size if page_size else len(labels)
        page = labels[start:end]
        result: dict[str, Any] = {"labels": page}
        if end < len(labels):
            result["nextPageToken"] = str(end)
        return result

    @traced_gmail_method
    def create_label(
        self,
        email: str,
        *,
        display_name: str,
        color: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        body: dict[str, Any] = {
            "name": display_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        if color:
            body["color"] = {
                "textColor": color.get("textColor"),
                "backgroundColor": color.get("backgroundColor"),
            }
        created = service.users().labels().create(userId="me", body=body).execute()
        return self._label_from_api(created)

    @traced_gmail_method
    def label_message(self, email: str, *, message_id: str, label_ids: list[str]) -> dict[str, Any]:
        return self._modify_message(email, message_id, add=label_ids)

    @traced_gmail_method
    def unlabel_message(
        self, email: str, *, message_id: str, label_ids: list[str]
    ) -> dict[str, Any]:
        return self._modify_message(email, message_id, remove=label_ids)

    @traced_gmail_method
    def label_thread(self, email: str, *, thread_id: str, label_ids: list[str]) -> dict[str, Any]:
        return self._modify_thread(email, thread_id, add=label_ids)

    @traced_gmail_method
    def unlabel_thread(self, email: str, *, thread_id: str, label_ids: list[str]) -> dict[str, Any]:
        return self._modify_thread(email, thread_id, remove=label_ids)

    def _modify_message(
        self,
        email: str,
        message_id: str,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        body: dict[str, Any] = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        service.users().messages().modify(userId="me", id=message_id, body=body).execute()
        return {}

    def _modify_thread(
        self,
        email: str,
        thread_id: str,
        *,
        add: list[str] | None = None,
        remove: list[str] | None = None,
    ) -> dict[str, Any]:
        service = self._service(email)
        body: dict[str, Any] = {}
        if add:
            body["addLabelIds"] = add
        if remove:
            body["removeLabelIds"] = remove
        service.users().threads().modify(userId="me", id=thread_id, body=body).execute()
        return {}

    @staticmethod
    def _resolve_format(message_format: MessageFormat | str | None) -> MessageFormat:
        if message_format is None or message_format in (
            MessageFormat.MESSAGE_FORMAT_UNSPECIFIED,
            "MESSAGE_FORMAT_UNSPECIFIED",
        ):
            return MessageFormat.FULL_CONTENT
        if isinstance(message_format, str):
            return MessageFormat(message_format)
        return message_format

    @staticmethod
    def _label_from_api(label: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "labelId": label["id"],
            "name": label.get("name", ""),
        }
        if "color" in label:
            result["color"] = {
                "textColor": label["color"].get("textColor"),
                "backgroundColor": label["color"].get("backgroundColor"),
            }
        if "messagesTotal" in label:
            result["threadsTotal"] = label.get("messagesTotal")
        if "messagesUnread" in label:
            result["threadsUnread"] = label.get("messagesUnread")
        return result

    def _draft_from_api(self, draft: dict[str, Any]) -> dict[str, Any]:
        message = draft.get("message", {})
        headers = message.get("payload", {}).get("headers", [])
        parsed = message_from_gmail_api(
            {**message, "payload": message.get("payload", {})},
            full_content=True,
        )
        return {
            "id": draft["id"],
            "subject": parsed.get("subject"),
            "threadId": message.get("threadId"),
            "toRecipients": parsed.get("toRecipients", []),
            "ccRecipients": parsed.get("ccRecipients", []),
            "bccRecipients": [],
            "plaintextBody": parsed.get("plaintextBody"),
            "htmlBody": parsed.get("htmlBody"),
            "date": parsed.get("date"),
        }

    @staticmethod
    def _build_mime(
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str | None,
        html_body: str | None,
    ) -> MIMEMultipart:
        if html_body:
            msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
            if body:
                msg.attach(MIMEText(body, "plain", "utf-8"))
            msg.attach(MIMEText(html_body, "html", "utf-8"))
        else:
            msg = MIMEText(body or "", "plain", "utf-8")

        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Subject"] = subject
        return msg
