import base64
from dataclasses import dataclass
import json
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

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


class GmailClient:
    def get_service(self):
        creds = None
        if settings.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(settings.token_path), SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not settings.credentials_path.exists():
                    raise FileNotFoundError(
                        "Missing Gmail OAuth client file. Add backend/credentials.json first."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(settings.credentials_path),
                    SCOPES,
                )
                creds = flow.run_local_server(port=0)

            settings.token_path.write_text(creds.to_json(), encoding="utf-8")

        return build("gmail", "v1", credentials=creds)

    def fetch_emails(self, max_results: int = 10):
        service = self.get_service()
        response = (
            service.users()
            .messages()
            .list(userId="me", q="category:primary", maxResults=max_results)
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
