import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from db import create_session_factory
from models import EmailRecord, SyncMeta
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

    def clear_all_emails(self):
        with self.session_factory() as session:
            session.query(EmailRecord).delete()
            session.commit()

    def count_emails(self):
        with self.session_factory() as session:
            return session.query(EmailRecord).count()

    def count_unindexed_emails(self):
        with self.session_factory() as session:
            return session.query(EmailRecord).filter(EmailRecord.indexed_at.is_(None)).count()

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
            if email_ids is not None:
                query = query.filter(EmailRecord.id.in_(email_ids))
            records = query.all()
            return [self._to_response(record) for record in records]

    def get_unindexed_emails_for_indexing(self):
        with self.session_factory() as session:
            records = (
                session.query(EmailRecord)
                .filter(EmailRecord.indexed_at.is_(None))
                .order_by(EmailRecord.id.desc())
                .all()
            )
            return [self._to_response(record) for record in records]

    def mark_indexed(self, email_id: int, indexed_at: datetime):
        with self.session_factory() as session:
            record = (
                session.query(EmailRecord)
                .filter(EmailRecord.id == email_id)
                .one_or_none()
            )
            if record is None:
                return
            record.indexed_at = indexed_at
            session.commit()

    def mark_indexed_batch(self, email_ids: list[int], indexed_at: datetime):
        if not email_ids:
            return
        with self.session_factory() as session:
            (
                session.query(EmailRecord)
                .filter(EmailRecord.id.in_(email_ids))
                .update({"indexed_at": indexed_at}, synchronize_session=False)
            )
            session.commit()

    def delete_emails_by_gmail_message_ids(self, gmail_message_ids: list[str]):
        if not gmail_message_ids:
            return []

        with self.session_factory() as session:
            records = (
                session.query(EmailRecord)
                .filter(EmailRecord.gmail_message_id.in_(gmail_message_ids))
                .all()
            )
            email_ids = [record.id for record in records]
            for record in records:
                session.delete(record)
            session.commit()
            return email_ids

    def get_sync_value(self, key: str):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.key == key).one_or_none()
            if record is None:
                return None
            return record.value

    def set_sync_value(self, key: str, value: str | None):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.key == key).one_or_none()
            if record is None:
                record = SyncMeta(key=key)
                session.add(record)
            record.value = value
            record.last_synced_at = datetime.now(timezone.utc)
            session.commit()

    def delete_sync_value(self, key: str):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.key == key).one_or_none()
            if record is None:
                return
            session.delete(record)
            session.commit()

    def keyword_search(self, query: str, limit: int = 8, scan_limit: int | None = None):
        terms = self._terms(query)
        if not terms:
            return []

        records = self.get_emails_for_indexing()
        if scan_limit is not None and scan_limit > 0:
            records = records[:scan_limit]
        scored = []
        for record in records:
            subject = (record.subject or "").lower()
            sender = (record.sender or "").lower()
            recipients = (record.recipients or "").lower()
            snippet = (record.snippet or "").lower()
            body_text = (record.body_text or "").lower()
            attachments = " ".join(record.attachment_names).lower()

            score = 0.0
            for term in terms:
                if term in subject:
                    score += 3.0
                if term in sender or term in recipients:
                    score += 1.5
                if term in snippet:
                    score += 2.0
                if term in attachments:
                    score += 1.5
                if term in body_text:
                    score += 1.0

            if not score:
                continue

            exact_query = " ".join(terms)
            if exact_query and exact_query in subject:
                score += 2.5
            elif exact_query and exact_query in snippet:
                score += 1.5
            elif exact_query and exact_query in body_text:
                score += 1.0

            score += self._recency_bonus(record.sent_at)
            scored.append((score, record))

        scored.sort(
            key=lambda item: (
                item[0],
                item[1].sent_at or datetime.min.replace(tzinfo=timezone.utc),
            ),
            reverse=True,
        )
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
        stopwords = {
            "a",
            "about",
            "an",
            "and",
            "any",
            "are",
            "can",
            "do",
            "emails",
            "find",
            "for",
            "from",
            "have",
            "how",
            "i",
            "in",
            "is",
            "it",
            "mail",
            "me",
            "my",
            "of",
            "on",
            "or",
            "related",
            "show",
            "tell",
            "that",
            "the",
            "this",
            "to",
            "we",
            "what",
            "which",
            "with",
            "you",
        }
        raw_terms = re.findall(r"[a-zA-Z0-9_]+", query.lower())
        normalized = []
        for term in raw_terms:
            if len(term) <= 1 or term in stopwords:
                continue
            if term.endswith("s") and len(term) > 4:
                term = term[:-1]
            normalized.append(term)
        return list(dict.fromkeys(normalized))

    def _recency_bonus(self, sent_at):
        if sent_at is None:
            return 0.0
        if isinstance(sent_at, str):
            try:
                sent_at = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
            except ValueError:
                return 0.0
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        age = max((datetime.now(timezone.utc) - sent_at).days, 0)
        if age <= 7:
            return 2.0
        if age <= 30:
            return 1.2
        if age <= 90:
            return 0.6
        return 0.0
