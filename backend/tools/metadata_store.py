import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import or_, text

from db import create_session_factory
from models import EmailRecord, GmailAccount, SyncMeta
from schemas import EmailRecordResponse, GmailAccountResponse


@dataclass
class MetadataStore:
    database_url: str

    def __post_init__(self):
        self.engine, self.session_factory = create_session_factory(self.database_url)

    def list_accounts(self):
        with self.session_factory() as session:
            records = session.query(GmailAccount).order_by(GmailAccount.created_at.asc(), GmailAccount.id.asc()).all()
            return [self._account_to_response(record) for record in records]

    def get_account(self, account_id: str):
        with self.session_factory() as session:
            record = session.query(GmailAccount).filter(GmailAccount.account_id == account_id).one_or_none()
            if record is None:
                return None
            return self._account_to_response(record)

    def get_active_account(self):
        with self.session_factory() as session:
            record = session.query(GmailAccount).filter(GmailAccount.is_active.is_(True)).order_by(GmailAccount.id.asc()).one_or_none()
            if record is None:
                return None
            return self._account_to_response(record)

    def upsert_account(self, account_id: str, token_path: str, email_address: str | None = None, display_name: str | None = None, make_active: bool = False):
        with self.session_factory() as session:
            record = session.query(GmailAccount).filter(GmailAccount.account_id == account_id).one_or_none()
            if record is None:
                record = GmailAccount(account_id=account_id)
                session.add(record)
            record.token_path = token_path
            record.email_address = email_address
            record.display_name = display_name
            if make_active:
                session.query(GmailAccount).update({"is_active": False}, synchronize_session=False)
                record.is_active = True
            elif record.is_active is None:
                record.is_active = False
            session.commit()
            session.refresh(record)
            return self._account_to_response(record)

    def set_active_account(self, account_id: str):
        with self.session_factory() as session:
            record = session.query(GmailAccount).filter(GmailAccount.account_id == account_id).one_or_none()
            if record is None:
                return None
            session.query(GmailAccount).update({"is_active": False}, synchronize_session=False)
            record.is_active = True
            session.commit()
            session.refresh(record)
            return self._account_to_response(record)

    def migrate_account_id(self, from_account_id: str, to_account_id: str):
        if not from_account_id or not to_account_id or from_account_id == to_account_id:
            return False

        with self.session_factory() as session:
            source = session.query(GmailAccount).filter(GmailAccount.account_id == from_account_id).one_or_none()
            target = session.query(GmailAccount).filter(GmailAccount.account_id == to_account_id).one_or_none()
            if source is None or target is None:
                return False

            target_email_count = session.query(EmailRecord).filter(EmailRecord.account_id == to_account_id).count()
            target_sync_count = session.query(SyncMeta).filter(SyncMeta.account_id == to_account_id).count()
            if target_email_count or target_sync_count:
                return False

            session.query(EmailRecord).filter(EmailRecord.account_id == from_account_id).update(
                {"account_id": to_account_id},
                synchronize_session=False,
            )
            session.query(SyncMeta).filter(SyncMeta.account_id == from_account_id).update(
                {"account_id": to_account_id},
                synchronize_session=False,
            )

            if not target.email_address and source.email_address:
                target.email_address = source.email_address
            if not target.display_name and source.display_name:
                target.display_name = source.display_name
            if source.is_active:
                session.query(GmailAccount).update({"is_active": False}, synchronize_session=False)
                target.is_active = True

            session.delete(source)
            session.commit()
            session.refresh(target)
            return True

    def upsert_email(self, email_payload, account_id: str):
        with self.session_factory() as session:
            record = (
                session.query(EmailRecord)
                .filter(EmailRecord.account_id == account_id, EmailRecord.gmail_message_id == email_payload.gmail_message_id)
                .one_or_none()
            )
            if record is None:
                record = EmailRecord(account_id=account_id, gmail_message_id=email_payload.gmail_message_id)
                session.add(record)

            record.account_id = account_id
            record.thread_id = email_payload.thread_id
            record.subject = email_payload.subject
            record.sender = email_payload.sender
            record.recipients = email_payload.recipients
            record.sent_at = email_payload.sent_at
            record.gmail_category = email_payload.gmail_category
            record.snippet = email_payload.snippet
            record.body_text = email_payload.body_text
            record.attachment_names = json.dumps(email_payload.attachment_names)
            record.raw_payload = email_payload.raw_payload
            session.commit()
            session.refresh(record)
            return self._to_response(record)

    def clear_all_emails(self, account_id: str):
        with self.session_factory() as session:
            session.query(EmailRecord).filter(EmailRecord.account_id == account_id).delete()
            session.commit()

    def count_emails(self, account_id: str):
        with self.session_factory() as session:
            query = session.query(EmailRecord).filter(EmailRecord.account_id == account_id)
            return self._exclude_trashed_query(query).count()

    def count_unindexed_emails(self, account_id: str):
        with self.session_factory() as session:
            query = session.query(EmailRecord).filter(
                EmailRecord.account_id == account_id,
                EmailRecord.indexed_at.is_(None),
            )
            return self._exclude_trashed_query(query).count()

    def list_emails(self, limit: int, account_id: str, category_filters: list[str] | None = None, search_filters: dict | None = None):
        with self.session_factory() as session:
            query = session.query(EmailRecord).filter(EmailRecord.account_id == account_id)
            query = self._exclude_trashed_query(query)
            if category_filters:
                query = query.filter(EmailRecord.gmail_category.in_(category_filters))
            if search_filters and search_filters.get("sender"):
                query = query.filter(EmailRecord.sender.ilike(f"%{search_filters['sender']}%"))
            if search_filters and search_filters.get("subject"):
                query = query.filter(EmailRecord.subject.ilike(f"%{search_filters['subject']}%"))
            records = query.order_by(EmailRecord.created_at.desc(), EmailRecord.id.desc()).limit(max(limit * 3, 20)).all()
            records = self._apply_date_filters(
                [self._to_response(record) for record in records],
                search_filters,
            )[:limit]
            return records

    def get_emails_for_indexing(self, account_id: str, email_ids: list[int] | None = None, category_filters: list[str] | None = None, search_filters: dict | None = None):
        with self.session_factory() as session:
            query = session.query(EmailRecord).filter(EmailRecord.account_id == account_id).order_by(EmailRecord.id.desc())
            query = self._exclude_trashed_query(query)
            if email_ids is not None:
                query = query.filter(EmailRecord.id.in_(email_ids))
            if category_filters:
                query = query.filter(EmailRecord.gmail_category.in_(category_filters))
            if search_filters and search_filters.get("sender"):
                query = query.filter(EmailRecord.sender.ilike(f"%{search_filters['sender']}%"))
            if search_filters and search_filters.get("subject"):
                query = query.filter(EmailRecord.subject.ilike(f"%{search_filters['subject']}%"))
            records = query.all()
            return self._apply_date_filters([self._to_response(record) for record in records], search_filters)

    def get_unindexed_emails_for_indexing(self, account_id: str):
        with self.session_factory() as session:
            records = (
                self._exclude_trashed_query(session.query(EmailRecord))
                .filter(EmailRecord.account_id == account_id, EmailRecord.indexed_at.is_(None))
                .order_by(EmailRecord.id.desc())
                .all()
            )
            return [self._to_response(record) for record in records]

    def mark_indexed(self, email_id: int, indexed_at: datetime, account_id: str):
        with self.session_factory() as session:
            record = (
                session.query(EmailRecord)
                .filter(EmailRecord.account_id == account_id, EmailRecord.id == email_id)
                .one_or_none()
            )
            if record is None:
                return
            record.indexed_at = indexed_at
            session.commit()

    def mark_indexed_batch(self, email_ids: list[int], indexed_at: datetime, account_id: str):
        if not email_ids:
            return
        with self.session_factory() as session:
            (
                session.query(EmailRecord)
                .filter(EmailRecord.account_id == account_id, EmailRecord.id.in_(email_ids))
                .update({"indexed_at": indexed_at}, synchronize_session=False)
            )
            session.commit()

    def delete_emails_by_gmail_message_ids(self, gmail_message_ids: list[str], account_id: str):
        if not gmail_message_ids:
            return []

        with self.session_factory() as session:
            records = (
                session.query(EmailRecord)
                .filter(EmailRecord.account_id == account_id, EmailRecord.gmail_message_id.in_(gmail_message_ids))
                .all()
            )
            email_ids = [record.id for record in records]
            for record in records:
                session.delete(record)
            session.commit()
            return email_ids

    def get_sync_value(self, key: str, account_id: str):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.account_id == account_id, SyncMeta.key == key).one_or_none()
            if record is None:
                return None
            return record.value

    def set_sync_value(self, key: str, value: str | None, account_id: str):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.account_id == account_id, SyncMeta.key == key).one_or_none()
            if record is None:
                record = SyncMeta(account_id=account_id, key=key)
                session.add(record)
            record.account_id = account_id
            record.value = value
            record.last_synced_at = datetime.now(timezone.utc)
            session.commit()

    def delete_sync_value(self, key: str, account_id: str):
        with self.session_factory() as session:
            record = session.query(SyncMeta).filter(SyncMeta.account_id == account_id, SyncMeta.key == key).one_or_none()
            if record is None:
                return
            session.delete(record)
            session.commit()

    def keyword_search(self, query: str, account_id: str, limit: int = 8, scan_limit: int | None = None, category_filters: list[str] | None = None, search_filters: dict | None = None):
        terms = self._terms(query)
        if not terms:
            return []
        normalized_query = self._normalized_query_phrase(query)
        fts_query = self._fts_query(terms)
        if not fts_query:
            return []

        with self.session_factory() as session:
            sql = """
                SELECT e.id, bm25(emails_fts, 8.0, 5.0, 2.5, 2.0, 1.0, 1.0) AS rank
                FROM emails_fts
                JOIN emails e ON e.id = emails_fts.rowid
                WHERE emails_fts MATCH :fts_query
            """
            params: dict[str, object] = {
                "fts_query": fts_query,
                "limit": max(limit * 4, 20),
                "account_id": account_id,
                "trash_pattern": '%"TRASH"%',
            }
            sql += " AND e.account_id = :account_id"
            sql += " AND (e.raw_payload IS NULL OR e.raw_payload NOT LIKE :trash_pattern)"
            if category_filters:
                placeholders = []
                for index, category in enumerate(category_filters):
                    key = f"category_{index}"
                    placeholders.append(f":{key}")
                    params[key] = category
                sql += f" AND e.gmail_category IN ({', '.join(placeholders)})"
            if search_filters and search_filters.get("sender"):
                sql += " AND lower(coalesce(e.sender, '')) LIKE :sender_like"
                params["sender_like"] = f"%{search_filters['sender'].lower()}%"
            if search_filters and search_filters.get("subject"):
                sql += " AND lower(coalesce(e.subject, '')) LIKE :subject_like"
                params["subject_like"] = f"%{search_filters['subject'].lower()}%"

            sql += " ORDER BY rank LIMIT :limit"
            rows = session.execute(text(sql), params).fetchall()
            if not rows:
                return []

            record_ids = [int(row.id) for row in rows]
            records = (
                session.query(EmailRecord)
                .filter(EmailRecord.id.in_(record_ids))
                .all()
            )
            record_map = {record.id: self._to_response(record) for record in records}

        scored = []
        for position, row in enumerate(rows):
            record = record_map.get(int(row.id))
            if record is None:
                continue

            subject = self._normalize_text(record.subject or "")
            sender = self._normalize_text(record.sender or "")
            recipients = self._normalize_text(record.recipients or "")
            snippet = self._normalize_text(record.snippet or "")
            body_text = self._normalize_text(record.body_text or "")

            score = max(0.0, 14.0 - position)
            if normalized_query and normalized_query in sender:
                score += 8.0
            if normalized_query and normalized_query in recipients:
                score += 5.0
            if normalized_query and normalized_query in subject:
                score += 4.0
            elif normalized_query and normalized_query in snippet:
                score += 2.0
            elif normalized_query and normalized_query in body_text:
                score += 1.5

            score += self._recency_bonus(record.sent_at)
            scored.append((score, record))

        filtered_records = self._apply_date_filters(
            [record for _, record in scored],
            search_filters,
        )
        allowed_ids = {record.id for record in filtered_records}
        scored = [(score, record) for score, record in scored if record.id in allowed_ids]
        scored.sort(
            key=lambda item: (
                item[0],
                self._sort_key_for_sent_at(item[1].sent_at),
            ),
            reverse=True,
        )
        return [{"score": score, "record": record} for score, record in scored[:limit]]

    def _to_response(self, record: EmailRecord):
        return EmailRecordResponse(
            id=record.id,
            gmail_message_id=record.gmail_message_id,
            subject=record.subject,
            sender=record.sender,
            recipients=record.recipients,
            sent_at=record.sent_at,
            gmail_category=record.gmail_category,
            snippet=record.snippet,
            body_text=record.body_text,
            attachment_names=self._parse_attachment_names(record.attachment_names),
        )

    def _account_to_response(self, record: GmailAccount):
        return GmailAccountResponse(
            account_id=record.account_id,
            email_address=record.email_address,
            display_name=record.display_name,
            token_path=record.token_path,
            is_active=bool(record.is_active),
        )

    def _parse_attachment_names(self, attachment_names: str | None):
        if not attachment_names:
            return []
        try:
            return json.loads(attachment_names)
        except json.JSONDecodeError:
            return []

    def _terms(self, query: str):
        raw_stopwords = {
            "a",
            "about",
            "an",
            "and",
            "any",
            "are",
            "can",
            "do",
            "did",
            "email",
            "emails",
            "find",
            "for",
            "from",
            "give",
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
            "receive",
            "received",
            "read",
            "related",
            "regarding",
            "latest",
            "recent",
            "show",
            "summaries",
            "summarize",
            "summary",
            "tell",
            "that",
            "the",
            "this",
            "to",
            "we",
            "what",
            "when",
            "which",
            "with",
            "you",
        }
        stopwords = {self._normalize_term(word) for word in raw_stopwords}
        raw_terms = re.findall(r"[a-zA-Z0-9_]+", query.lower())
        normalized = []
        for term in raw_terms:
            normalized_term = self._normalize_term(term)
            if len(normalized_term) <= 1 or normalized_term in stopwords:
                continue
            normalized.append(normalized_term)
        return list(dict.fromkeys(normalized))

    def _normalized_query_phrase(self, query: str):
        terms = self._terms(query)
        if not terms:
            return ""
        return " ".join(terms)

    def _fts_query(self, terms: list[str]):
        safe_terms = []
        for term in terms:
            cleaned = re.sub(r'[^a-zA-Z0-9_]+', "", term).strip()
            if not cleaned:
                continue
            safe_terms.append(f'{cleaned}*')
        return " AND ".join(safe_terms)

    def _normalize_text(self, text: str):
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return " ".join(
            normalized
            for normalized in (self._normalize_term(token) for token in tokens)
            if normalized
        )

    def _normalize_term(self, term: str):
        normalized = term.lower().strip()
        for suffix in (
            "ations",
            "ation",
            "ments",
            "ment",
            "tions",
            "tion",
            "ings",
            "ing",
            "ized",
            "izes",
            "ize",
            "ies",
            "ied",
            "ers",
            "er",
            "es",
            "ed",
            "s",
        ):
            if normalized.endswith(suffix) and len(normalized) > len(suffix) + 2:
                normalized = normalized[: -len(suffix)]
                break
        if normalized.endswith("e") and len(normalized) > 5:
            normalized = normalized[:-1]
        return normalized

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

    def _sort_key_for_sent_at(self, sent_at):
        if sent_at is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if isinstance(sent_at, str):
            normalized = sent_at.strip()
            if " (" in normalized:
                normalized = normalized.split(" (", 1)[0]
            try:
                parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            except ValueError:
                try:
                    parsed = parsedate_to_datetime(sent_at)
                except (TypeError, ValueError, IndexError):
                    return datetime.min.replace(tzinfo=timezone.utc)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        return sent_at

    def _apply_date_filters(self, records: list[EmailRecordResponse], search_filters: dict | None):
        if not search_filters:
            return records

        date_from = self._parse_filter_date(search_filters.get("date_from"))
        date_to = self._parse_filter_date(search_filters.get("date_to"), end_of_day=True)
        if date_from is None and date_to is None:
            return records

        filtered = []
        for record in records:
            sent_at = self._sort_key_for_sent_at(record.sent_at)
            if date_from is not None and sent_at < date_from:
                continue
            if date_to is not None and sent_at > date_to:
                continue
            filtered.append(record)
        return filtered

    def _parse_filter_date(self, raw_value: str | None, end_of_day: bool = False):
        if not raw_value:
            return None
        try:
            parsed = datetime.fromisoformat(raw_value)
        except ValueError:
            return None
        if end_of_day:
            parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    def _exclude_trashed_query(self, query):
        return query.filter(
            or_(
                EmailRecord.raw_payload.is_(None),
                ~EmailRecord.raw_payload.like('%"TRASH"%'),
            )
        )
