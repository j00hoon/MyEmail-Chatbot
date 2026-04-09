from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re

from retrieval.execution_plans import QueryExecutionPlan
from schemas import EmailRecordResponse
from skills.embedding_generation import EmbeddingGenerationSkill
from skills.vector_search import VectorSearchSkill
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


@dataclass
class CandidateEmail:
    gmail_message_id: str
    subject: str
    sender: str | None
    sent_at: str | None
    gmail_category: str | None
    snippet: str | None
    attachment_names: list[str]
    document: str
    record_id: int | None = None
    metadata_score: float = 0.0
    lexical_score: float = 0.0
    semantic_score: float = 0.0
    final_score: float = 0.0
    matched_terms: list[str] = field(default_factory=list)
    provenance: set[str] = field(default_factory=set)

    def to_source(self):
        return {
            "gmail_message_id": self.gmail_message_id,
            "subject": self.subject or "No Subject",
            "sender": self.sender,
            "sent_at": self.sent_at,
            "gmail_category": self.gmail_category,
            "snippet": self.snippet,
            "attachment_names": self.attachment_names,
            "document": self.document,
            "score": float(self.final_score),
            "matched_terms": list(self.matched_terms),
            "provenance": sorted(self.provenance),
        }


class MetadataRetriever:
    def __init__(self, metadata_store: MetadataStore):
        self.metadata_store = metadata_store

    def retrieve(self, execution_plan: QueryExecutionPlan):
        records = self.metadata_store.get_emails_for_indexing(
            account_id=execution_plan.account_id,
            category_filters=execution_plan.category_filters,
            search_filters=execution_plan.metadata_filters,
        )
        sorted_records = sorted(records, key=lambda record: _parse_sent_at(record.sent_at), reverse=True)
        limited_records = sorted_records[: execution_plan.candidate_limit]
        candidates = []
        for record in limited_records:
            candidates.append(
                CandidateEmail(
                    gmail_message_id=record.gmail_message_id,
                    subject=record.subject or "No Subject",
                    sender=record.sender,
                    sent_at=record.sent_at,
                    gmail_category=record.gmail_category,
                    snippet=record.snippet,
                    attachment_names=record.attachment_names,
                    document=record.body_text or record.snippet or "",
                    record_id=record.id,
                    metadata_score=_metadata_match_score(record=record, execution_plan=execution_plan),
                    provenance={"metadata"},
                )
            )
        return candidates


class LexicalRetriever:
    def retrieve(self, execution_plan: QueryExecutionPlan, records: list[CandidateEmail]):
        if not execution_plan.keyword_terms:
            return []

        lexical_candidates: list[CandidateEmail] = []
        normalized_terms = [self._normalize_phrase(term) for term in execution_plan.keyword_terms if term.strip()]
        for record in records:
            subject_text = self._normalize_phrase(record.subject or "")
            sender_text = self._normalize_phrase(record.sender or "")
            snippet_text = self._normalize_phrase(record.snippet or "")
            document_text = self._normalize_phrase(record.document or "")

            matched_terms: list[str] = []
            score = 0.0
            for raw_term, normalized_term in zip(execution_plan.keyword_terms, normalized_terms):
                if not normalized_term:
                    continue
                term_hit = 0.0
                if normalized_term in subject_text:
                    term_hit = max(term_hit, 1.0)
                if normalized_term in sender_text:
                    term_hit = max(term_hit, 0.95)
                if normalized_term in snippet_text:
                    term_hit = max(term_hit, 0.8)
                if normalized_term in document_text:
                    term_hit = max(term_hit, 0.65)
                if term_hit > 0:
                    matched_terms.append(raw_term)
                    score += term_hit

            if score <= 0:
                continue

            normalized_score = min(score / max(len(normalized_terms), 1), 1.0)
            lexical_candidates.append(
                CandidateEmail(
                    gmail_message_id=record.gmail_message_id,
                    subject=record.subject,
                    sender=record.sender,
                    sent_at=record.sent_at,
                    gmail_category=record.gmail_category,
                    snippet=record.snippet,
                    attachment_names=list(record.attachment_names),
                    document=record.document,
                    record_id=record.record_id,
                    metadata_score=record.metadata_score,
                    lexical_score=normalized_score,
                    matched_terms=matched_terms,
                    provenance={"lexical"},
                )
            )

        lexical_candidates.sort(
            key=lambda candidate: (
                candidate.lexical_score,
                _parse_sent_at(candidate.sent_at),
            ),
            reverse=True,
        )
        return lexical_candidates[: execution_plan.candidate_limit]

    def _normalize_phrase(self, text: str):
        return " ".join(re.findall(r"[a-zA-Z0-9_]+", text.lower()))


class SemanticRetriever:
    def __init__(self, vector_store: VectorStore):
        self.embedding_skill = EmbeddingGenerationSkill()
        self.vector_search_skill = VectorSearchSkill(vector_store=vector_store)

    def retrieve(self, execution_plan: QueryExecutionPlan):
        query_text = execution_plan.semantic_query_text.strip()
        if not query_text:
            return []

        query_embedding = self.embedding_skill.execute(query_text)
        vector_results = self.vector_search_skill.execute(
            query_embedding=query_embedding,
            query_text=" ".join(execution_plan.keyword_terms) or query_text,
            top_k=execution_plan.candidate_limit,
            account_id=execution_plan.account_id,
        )

        semantic_candidates: list[CandidateEmail] = []
        for result in vector_results:
            metadata = result.get("metadata", {})
            candidate = CandidateEmail(
                gmail_message_id=metadata.get("gmail_message_id", ""),
                subject=metadata.get("subject") or "No Subject",
                sender=metadata.get("sender"),
                sent_at=metadata.get("sent_at"),
                gmail_category=metadata.get("gmail_category"),
                snippet=metadata.get("snippet"),
                attachment_names=list(metadata.get("attachment_names", [])),
                document=metadata.get("document", ""),
                record_id=metadata.get("email_id"),
                semantic_score=float(result.get("score", 0.0)),
                provenance={"semantic"},
            )
            if not _matches_category_filters(candidate, execution_plan.category_filters):
                continue
            if not _matches_metadata_filters(candidate, execution_plan.metadata_filters):
                continue
            semantic_candidates.append(candidate)

        return semantic_candidates


def _metadata_match_score(*, record: EmailRecordResponse, execution_plan: QueryExecutionPlan):
    checks: list[float] = []
    sender_filter = (execution_plan.metadata_filters.get("sender") or "").strip().lower()
    subject_filter = (execution_plan.metadata_filters.get("subject") or "").strip().lower()
    if sender_filter:
        checks.append(1.0 if sender_filter in (record.sender or "").lower() else 0.0)
    if subject_filter:
        checks.append(1.0 if subject_filter in (record.subject or "").lower() else 0.0)
    if execution_plan.metadata_filters.get("date_from") or execution_plan.metadata_filters.get("date_to"):
        checks.append(1.0 if _matches_metadata_filters(_candidate_from_record(record), execution_plan.metadata_filters) else 0.0)
    if execution_plan.category_filters:
        checks.append(1.0 if (record.gmail_category or "uncategorized") in set(execution_plan.category_filters) else 0.0)
    if not checks:
        return 0.6
    return sum(checks) / len(checks)


def _candidate_from_record(record: EmailRecordResponse):
    return CandidateEmail(
        gmail_message_id=record.gmail_message_id,
        subject=record.subject or "No Subject",
        sender=record.sender,
        sent_at=record.sent_at,
        gmail_category=record.gmail_category,
        snippet=record.snippet,
        attachment_names=record.attachment_names,
        document=record.body_text or record.snippet or "",
        record_id=record.id,
    )


def _matches_category_filters(candidate: CandidateEmail, category_filters: list[str]):
    if not category_filters:
        return True
    return (candidate.gmail_category or "uncategorized") in set(category_filters)


def _matches_metadata_filters(candidate: CandidateEmail, metadata_filters: dict[str, str | None]):
    sender_filter = (metadata_filters.get("sender") or "").strip().lower()
    subject_filter = (metadata_filters.get("subject") or "").strip().lower()

    if sender_filter and sender_filter not in (candidate.sender or "").lower():
        return False
    if subject_filter and subject_filter not in (candidate.subject or "").lower():
        return False

    sent_at = _parse_sent_at(candidate.sent_at)
    date_from = _parse_filter_date(metadata_filters.get("date_from"))
    date_to = _parse_filter_date(metadata_filters.get("date_to"), end_of_day=True)

    if date_from is not None and sent_at < date_from:
        return False
    if date_to is not None and sent_at > date_to:
        return False
    return True


def _parse_filter_date(raw_value: str | None, *, end_of_day: bool = False):
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


def _parse_sent_at(sent_at: str | None):
    if not sent_at:
        return datetime.min.replace(tzinfo=timezone.utc)
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
