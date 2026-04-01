import base64
from dataclasses import dataclass
import json
from typing import Any

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import settings


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


@dataclass
class GmailEmailPayload:
    gmail_message_id: str
    thread_id: str | None
    subject: str
    sender: str | None
    recipients: str | None
    sent_at: str | None
    snippet: str
    body_text: str
    attachment_names: list[str]
    raw_payload: str


@dataclass
class GmailFullSyncResult:
    emails: list[GmailEmailPayload]
    history_id: str


@dataclass
class GmailHistoryDelta:
    emails: list[GmailEmailPayload]
    deleted_message_ids: list[str]
    history_id: str


class HistoryIdExpiredError(Exception):
    pass


class GmailClient:
    def get_service(self):
        creds = None
        if settings.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(settings.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except RefreshError:
                    creds = None
                    settings.token_path.unlink(missing_ok=True)

            if not creds or not creds.valid:
                creds = self._run_oauth_flow()
                settings.token_path.write_text(creds.to_json(), encoding="utf-8")
        elif settings.token_path.exists():
            settings.token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=creds)

    def _run_oauth_flow(self):
        if not settings.credentials_path.exists():
            raise FileNotFoundError(
                "Missing Gmail OAuth client file. Add backend/credentials.json first."
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(settings.credentials_path),
            SCOPES,
        )
        return flow.run_local_server(port=0)

    def get_current_history_id(self, service=None):
        service = service or self.get_service()
        profile = service.users().getProfile(userId="me").execute()
        return str(profile["historyId"])

    def fetch_full_sync(self, progress_callback=None):
        service = self.get_service()
        emails = []
        page_token = None
        page_count = 0

        while True:
            response = (
                service.users()
                .messages()
                .list(userId="me", maxResults=500, pageToken=page_token)
                .execute()
            )
            messages = response.get("messages", [])
            page_count += 1

            for message in messages:
                detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message["id"], format="full")
                    .execute()
                )
                emails.append(self._parse_email(detail))

            if progress_callback is not None:
                progress_callback(page_count=page_count, fetched_count=len(emails))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return GmailFullSyncResult(
            emails=emails,
            history_id=self.get_current_history_id(service=service),
        )

    def fetch_incremental_changes(self, history_id: str, progress_callback=None):
        service = self.get_service()
        page_token = None
        latest_history_id = history_id
        changed_message_ids: set[str] = set()
        deleted_message_ids: set[str] = set()
        processed_history_records = 0

        while True:
            try:
                response = (
                    service.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=history_id,
                        maxResults=500,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as exc:
                if getattr(exc.resp, "status", None) == 404:
                    raise HistoryIdExpiredError("Stored Gmail historyId is expired.") from exc
                raise

            latest_history_id = str(response.get("historyId", latest_history_id))
            history_records = response.get("history", [])
            processed_history_records += len(history_records)

            for entry in history_records:
                for item in entry.get("messagesDeleted", []):
                    message = item.get("message", {})
                    message_id = message.get("id")
                    if message_id:
                        deleted_message_ids.add(message_id)

                for bucket in ("messagesAdded", "labelsAdded", "labelsRemoved"):
                    for item in entry.get(bucket, []):
                        message = item.get("message", {})
                        message_id = message.get("id")
                        if message_id:
                            changed_message_ids.add(message_id)

                for message in entry.get("messages", []):
                    message_id = message.get("id")
                    if message_id:
                        changed_message_ids.add(message_id)

            if progress_callback is not None:
                progress_callback(
                    processed_history_records=processed_history_records,
                    changed_count=len(changed_message_ids),
                    deleted_count=len(deleted_message_ids),
                )

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        changed_message_ids -= deleted_message_ids
        emails = []
        total_changed = max(len(changed_message_ids), 1)

        for position, message_id in enumerate(sorted(changed_message_ids), start=1):
            try:
                detail = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="full")
                    .execute()
                )
            except HttpError as exc:
                if getattr(exc.resp, "status", None) == 404:
                    deleted_message_ids.add(message_id)
                    continue
                raise

            emails.append(self._parse_email(detail))
            if progress_callback is not None:
                progress_callback(
                    processed_history_records=processed_history_records,
                    changed_count=position,
                    deleted_count=len(deleted_message_ids),
                )

        return GmailHistoryDelta(
            emails=emails,
            deleted_message_ids=sorted(deleted_message_ids),
            history_id=self.get_current_history_id(service=service),
        )

    def fetch_emails(self, max_results: int = 10):
        service = self.get_service()
        response = (
            service.users()
            .messages()
            .list(userId="me", maxResults=max_results)
            .execute()
        )
        messages = response.get("messages", [])
        emails = []
        for message in messages:
            detail = (
                service.users()
                .messages()
                .get(userId="me", id=message["id"], format="full")
                .execute()
            )
            emails.append(self._parse_email(detail))
        return emails

    def _parse_email(self, detail: dict[str, Any]):
        payload = detail.get("payload", {})
        headers = payload.get("headers", [])
        subject = self._get_header(headers, "Subject") or "No Subject"
        sender = self._get_header(headers, "From")
        recipients = self._get_header(headers, "To")
        sent_at = self._get_header(headers, "Date")
        body_text, attachment_names = self._extract_parts(payload)
        if not body_text:
            body_text = detail.get("snippet", "")

        return GmailEmailPayload(
            gmail_message_id=detail["id"],
            thread_id=detail.get("threadId"),
            subject=subject,
            sender=sender,
            recipients=recipients,
            sent_at=sent_at,
            snippet=detail.get("snippet", ""),
            body_text=body_text,
            attachment_names=attachment_names,
            raw_payload=json.dumps(detail),
        )

    def _get_header(self, headers: list[dict[str, str]], key: str):
        return next((item.get("value") for item in headers if item.get("name") == key), None)

    def _extract_parts(self, payload: dict[str, Any]):
        attachment_names: list[str] = []
        body_segments: list[str] = []

        def walk(part: dict[str, Any]):
            filename = part.get("filename")
            if filename:
                attachment_names.append(filename)

            mime_type = part.get("mimeType", "")
            body = part.get("body", {})
            data = body.get("data")
            if data and mime_type in {"text/plain", "text/html"}:
                try:
                    decoded = base64.urlsafe_b64decode(data.encode("utf-8"))
                    text = decoded.decode("utf-8", errors="ignore")
                    body_segments.append(text)
                except Exception:
                    pass

            for child in part.get("parts", []):
                walk(child)

        walk(payload)
        body_text = "\n".join(segment.strip() for segment in body_segments if segment.strip())
        return body_text, attachment_names
