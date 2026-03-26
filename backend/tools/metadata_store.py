import json
import re
from dataclasses import dataclass
from datetime import datetime

from db import create_session_factory
from models import EmailRecord
from schemas import EmailRecordResponse


@dataclass
class MetadataStore:
    database_url: str

    def __post_init__(self):
        self.engine, self.session_factory = create_session_factory(self.database_url)

    def upsert_email(self, email_payload):
        with self.session_factory() as session:
            record = (
                session.query(EmailRecord)
                .filter(EmailRecord.gmail_message_id == email_payload.gmail_message_id)
                .one_or_none()
            )
            if record is None:
                record = EmailRecord(gmail_message_id=email_payload.gmail_message_id)
                session.add(record)

            record.thread_id = email_payload.thread_id
            record.subject = email_payload.subject
            record.sender = email_payload.sender
            record.recipients = email_payload.recipients
            record.sent_at = email_payload.sent_at
            record.snippet = email_payload.snippet
            record.body_text = email_payload.body_text
            record.attachment_names = json.dumps(email_payload.attachment_names)
            record.raw_payload = email_payload.raw_payload
            session.commit()
            session.refresh(record)
            return self._to_response(record)

    def list_emails(self, limit: int):
        with self.session_factory() as session:
            records = (
                session.query(EmailRecord)
                .order_by(EmailRecord.created_at.desc(), EmailRecord.id.desc())
                .limit(limit)
                .all()
            )
            return [self._to_response(record) for record in records]

    def get_emails_for_indexing(self, email_ids: list[int] | None = None):
        with self.session_factory() as session:
            query = session.query(EmailRecord).order_by(EmailRecord.id.desc())
            if email_ids:
                query = query.filter(EmailRecord.id.in_(email_ids))
            records = query.all()
            return [self._to_response(record) for record in records]

    def mark_indexed(self, email_id: int, indexed_at: datetime):
        with self.session_factory() as session:
            record = session.query(EmailRecord).filter(EmailRecord.id == email_id).one()
            record.indexed_at = indexed_at
            session.commit()

    def keyword_search(self, query: str, limit: int = 8):
        terms = self._terms(query)
        if not terms:
            return []

        records = self.get_emails_for_indexing()
        scored = []
        for record in records:
            haystack = " ".join(
                [
                    record.subject or "",
                    record.sender or "",
                    record.recipients or "",
                    record.snippet or "",
                    record.body_text or "",
                    " ".join(record.attachment_names),
                ]
            ).lower()
            matches = sum(1 for term in terms if term in haystack)
            if matches:
                scored.append((matches / len(terms), record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"score": score, "record": record}
            for score, record in scored[:limit]
        ]

    def _to_response(self, record: EmailRecord):
        return EmailRecordResponse(
            id=record.id,
            gmail_message_id=record.gmail_message_id,
            subject=record.subject,
            sender=record.sender,
            recipients=record.recipients,
            sent_at=record.sent_at,
            snippet=record.snippet,
            body_text=record.body_text,
            attachment_names=self._parse_attachment_names(record.attachment_names),
        )

    def _parse_attachment_names(self, attachment_names: str | None):
        if not attachment_names:
            return []
        try:
            return json.loads(attachment_names)
        except json.JSONDecodeError:
            return []

    def _terms(self, query: str):
        return [term for term in re.findall(r"[a-zA-Z0-9_]+", query.lower()) if len(term) > 1]
