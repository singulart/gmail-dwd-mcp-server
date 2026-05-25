from __future__ import annotations

import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import build

from gmail_dwd_mcp.auth import WifConfigCache, credentials_for_user
from gmail_dwd_mcp.mime import (
    append_html_signature,
    append_plain_signature,
    html_to_plain,
    message_from_gmail_api,
    plain_to_html,
    strip_trailing_plain_signature,
)
from gmail_dwd_mcp.hydration import (
    SearchThreadsResult,
    triage_thread_from_list_summary,
)
from gmail_dwd_mcp.telemetry import traced_gmail_method


def message_needs_full_fetch(msg: dict[str, Any]) -> bool:
    """Whether messages.get(format=full) is required for body extraction.

    threads.get(format=full) normally embeds each message's MIME payload inline.
    A follow-up fetch is only needed when that payload is absent (unexpected API
    response or a partial message resource). Empty bodies still include payload
    metadata and do not require a second fetch.
    """
    if "raw" in msg:
        return False
    return not msg.get("payload")


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
    ) -> SearchThreadsResult:
        """Discover threads for triage (no bodies, no per-thread fetches).

        API cost: **1** ``threads.list`` call. Each result is a thread id with
        ``messages: []``. Use ``get_thread`` / ``get_threads`` for snippets and
        normalized bodies.
        """
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
        threads_out = [
            triage_thread_from_list_summary(summary)
            for summary in list_resp.get("threads", [])
        ]
        return SearchThreadsResult(
            threads=threads_out,
            next_page_token=list_resp.get("nextPageToken"),
        )

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
            drafts.append(self._draft_from_api(draft, service=service))
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
        signature_html = self._fetch_html_signature(service)
        message = self._build_mime(
            to=to,
            cc=cc or [],
            bcc=bcc or [],
            subject=subject or "",
            body=body,
            html_body=html_body,
            signature_html=signature_html,
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
        return self._draft_from_api(full, service=service)

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

    @staticmethod
    def _fetch_html_signature(service) -> str | None:
        try:
            resp = service.users().settings().sendAs().list(userId="me").execute()
        except Exception:
            return None
        aliases = resp.get("sendAs", [])
        for alias in aliases:
            if alias.get("isDefault"):
                sig = alias.get("signature")
                return sig.strip() if sig else None
        for alias in aliases:
            if alias.get("isPrimary"):
                sig = alias.get("signature")
                return sig.strip() if sig else None
        if aliases:
            sig = aliases[0].get("signature")
            return sig.strip() if sig else None
        return None

    def _draft_from_api(
        self,
        draft: dict[str, Any],
        *,
        service=None,
    ) -> dict[str, Any]:
        message = draft.get("message", {})
        parsed = message_from_gmail_api(
            {**message, "payload": message.get("payload", {})},
            full_content=True,
        )
        html_body = parsed.get("htmlBody")
        plaintext_body = parsed.get("plaintextBody")
        if service:
            signature_html = self._fetch_html_signature(service)
            html_body = self._html_body_with_signature(
                html_body,
                plaintext_body,
                signature_html,
            )
        return {
            "id": draft["id"],
            "subject": parsed.get("subject"),
            "threadId": message.get("threadId"),
            "toRecipients": parsed.get("toRecipients", []),
            "ccRecipients": parsed.get("ccRecipients", []),
            "bccRecipients": [],
            "plaintextBody": plaintext_body,
            "htmlBody": html_body,
            "date": parsed.get("date"),
        }

    @staticmethod
    def _html_body_with_signature(
        html_body: str | None,
        plaintext_body: str | None,
        signature_html: str | None,
    ) -> str | None:
        if not signature_html:
            return html_body
        signature_plain = html_to_plain(signature_html)
        if html_body and signature_html in html_body:
            return html_body
        if html_body:
            return append_html_signature(html_body, signature_html)
        if not plaintext_body:
            return signature_html
        body_plain = strip_trailing_plain_signature(plaintext_body, signature_plain)
        base_html = plain_to_html(body_plain or plaintext_body)
        return append_html_signature(base_html, signature_html)

    @staticmethod
    def _build_mime(
        *,
        to: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str | None,
        html_body: str | None,
        signature_html: str | None = None,
    ) -> MIMEMultipart:
        html_content = html_body
        plain_content = body
        signature_plain = html_to_plain(signature_html) if signature_html else None

        if signature_html:
            if html_content:
                html_content = append_html_signature(html_content, signature_html)
            elif plain_content:
                html_content = append_html_signature(plain_to_html(plain_content), signature_html)
            else:
                html_content = signature_html
            if plain_content:
                plain_content = append_plain_signature(plain_content, signature_plain or "")
            elif html_body:
                plain_content = append_plain_signature(
                    html_to_plain(html_body),
                    signature_plain or "",
                )
            else:
                plain_content = signature_plain or ""

        if html_content:
            msg: MIMEMultipart | MIMEText = MIMEMultipart("alternative")
            if plain_content:
                msg.attach(MIMEText(plain_content, "plain", "utf-8"))
            msg.attach(MIMEText(html_content, "html", "utf-8"))
        else:
            msg = MIMEText(plain_content or "", "plain", "utf-8")

        msg["To"] = ", ".join(to)
        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)
        msg["Subject"] = subject
        return msg
