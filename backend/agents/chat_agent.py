from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from retrieval.mailbox_query import GmailQueryBuilder, QueryAnalyzer, QueryExecutionPlanner
from schemas import ChatResponse, EmailSearchIntent, SourceReference
from skills.answer_generation import AnswerGenerationSkill
from skills.embedding_generation import EmbeddingGenerationSkill
from skills.vector_search import VectorSearchSkill
from tools.cache_store import CacheStore
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "data" / "query_debug.log"
DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_debug_logger = logging.getLogger("query_debug")
if not _debug_logger.handlers:
    handler = logging.FileHandler(DEBUG_LOG_PATH, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _debug_logger.addHandler(handler)
    _debug_logger.setLevel(logging.INFO)
    _debug_logger.propagate = False


@dataclass
class ChatAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore
    cache_store: CacheStore | None = None
    mailbox_id: str = "local_default"
    query_analyzer: QueryAnalyzer = field(default_factory=QueryAnalyzer)
    gmail_query_builder: GmailQueryBuilder = field(default_factory=GmailQueryBuilder)
    execution_planner: QueryExecutionPlanner = field(init=False)

    def __post_init__(self):
        self.execution_planner = QueryExecutionPlanner(gmail_query_builder=self.gmail_query_builder)

    def run(self, question: str, top_k: int = 4, category_filters: list[str] | None = None, search_filters: dict | None = None):
        if not question.strip():
            raise ValueError("question must not be empty")

        category_filters = sorted(set(category_filters or []))
        normalized_filters = self._normalize_search_filters(search_filters)
        reference_date = self._reference_date()
        structured_intent = self.query_analyzer.analyze(question=question, reference_date=reference_date)
        execution_plan = self.execution_planner.build(
            question=question,
            structured_intent=structured_intent,
            reference_date=reference_date,
            category_filters=category_filters,
            search_filters=normalized_filters,
        )

        sources = self._retrieve_sources(execution_plan=execution_plan, top_k=top_k, category_filters=category_filters)
        self._log_query_debug(
            question=question,
            structured_intent=structured_intent,
            execution_plan=execution_plan,
            top_k=top_k,
            category_filters=category_filters,
            search_filters=normalized_filters,
            source_count=len(sources),
        )

        cache_signature = self._build_cache_signature(
            structured_intent=structured_intent,
            top_k=top_k,
            category_filters=category_filters,
            search_filters=normalized_filters,
            sources=sources,
        )

        if self.cache_store is not None:
            cached_response = self.cache_store.get_chat_response(
                mailbox_id=self.mailbox_id,
                cache_signature=cache_signature,
            )
            if cached_response is not None:
                return cached_response

        answer = AnswerGenerationSkill().execute(
            question=question,
            sources=sources,
            answer_mode=self._answer_mode_for_intent(structured_intent=structured_intent, source_count=len(sources), top_k=top_k),
            output_mode=structured_intent.output_mode,
            gmail_query=execution_plan.gmail_query,
        )

        response = ChatResponse(
            answer=answer,
            sources=[
                SourceReference(
                    gmail_message_id=source["gmail_message_id"],
                    subject=source["subject"],
                    sender=source["sender"],
                    sent_at=source["sent_at"],
                    gmail_category=source.get("gmail_category"),
                    snippet=source["snippet"],
                    attachment_names=source["attachment_names"],
                    score=source["score"],
                )
                for source in sources
            ],
        )

        if self.cache_store is not None:
            self.cache_store.set_chat_response(
                mailbox_id=self.mailbox_id,
                cache_signature=cache_signature,
                response=response,
            )

        return response

    def _retrieve_sources(self, *, execution_plan, top_k: int, category_filters: list[str]):
        candidate_records = self.metadata_store.get_emails_for_indexing(
            category_filters=category_filters,
            search_filters=execution_plan.metadata_filters,
        )
        lexical_sources = self._sources_from_keyword_groups(
            records=candidate_records,
            keyword_groups=execution_plan.keyword_groups,
        )
        semantic_sources = self._sources_from_vector_search(
            semantic_query_text=execution_plan.semantic_query_text,
            top_k=max(top_k * 6, 18),
            category_filters=category_filters,
            metadata_filters=execution_plan.metadata_filters,
        )

        merged: dict[str, dict] = {}

        for source in semantic_sources:
            merged[source["gmail_message_id"]] = source

        for source in lexical_sources:
            key = source["gmail_message_id"]
            existing = merged.get(key)
            if existing is None:
                merged[key] = source
                continue

            existing["score"] = max(existing["score"], source["score"])
            if len(source.get("document", "")) > len(existing.get("document", "")):
                existing["document"] = source["document"]
            if not existing.get("snippet"):
                existing["snippet"] = source.get("snippet")

        ranked = sorted(
            merged.values(),
            key=lambda source: (
                float(source.get("score", 0.0)),
                self._parse_sent_at(source.get("sent_at")),
            ),
            reverse=True,
        )

        return ranked[: max(1, top_k)]

    def _sources_from_keyword_groups(self, *, records, keyword_groups: list[list[str]]):
        if not keyword_groups:
            return [self._source_from_record(record, score=0.15) for record in records[:25]]

        matched_sources = []
        total_groups = len(keyword_groups)

        for record in records:
            haystack = " ".join(
                value.lower()
                for value in (
                    record.subject or "",
                    record.sender or "",
                    record.recipients or "",
                    record.snippet or "",
                    record.body_text or "",
                )
            )
            matched_groups = 0
            for group in keyword_groups:
                normalized_terms = [term.lower() for term in group if term]
                if normalized_terms and any(term in haystack for term in normalized_terms):
                    matched_groups += 1

            if matched_groups == 0:
                continue

            coverage = matched_groups / max(total_groups, 1)
            matched_sources.append(self._source_from_record(record, score=coverage))

        return matched_sources

    def _sources_from_vector_search(self, *, semantic_query_text: str, top_k: int, category_filters: list[str], metadata_filters: dict):
        query_text = semantic_query_text.strip()
        if not query_text:
            return []

        query_embedding = EmbeddingGenerationSkill().execute(query_text)
        vector_results = VectorSearchSkill(vector_store=self.vector_store).execute(
            query_embedding=query_embedding,
            query_text=query_text,
            top_k=top_k,
        )

        filtered_sources = []
        for result in vector_results:
            metadata = result.get("metadata", {})
            source = {
                "subject": metadata.get("subject") or "No Subject",
                "sender": metadata.get("sender"),
                "sent_at": metadata.get("sent_at"),
                "gmail_category": metadata.get("gmail_category"),
                "snippet": metadata.get("snippet"),
                "attachment_names": metadata.get("attachment_names", []),
                "document": metadata.get("document", ""),
                "gmail_message_id": metadata.get("gmail_message_id", ""),
                "score": float(result.get("score", 0.0)),
            }
            if not self._matches_category_filters(source, category_filters):
                continue
            if not self._matches_metadata_filters(source, metadata_filters):
                continue
            filtered_sources.append(source)

        return filtered_sources

    def _source_from_record(self, record, score: float):
        return {
            "subject": record.subject or "No Subject",
            "sender": record.sender,
            "sent_at": record.sent_at,
            "gmail_category": getattr(record, "gmail_category", None),
            "snippet": record.snippet,
            "attachment_names": record.attachment_names,
            "document": record.body_text or record.snippet or "",
            "gmail_message_id": record.gmail_message_id,
            "score": float(score),
        }

    def _matches_category_filters(self, source: dict, category_filters: list[str]):
        if not category_filters:
            return True
        return (source.get("gmail_category") or "uncategorized") in set(category_filters)

    def _matches_metadata_filters(self, source: dict, metadata_filters: dict):
        sender_filter = self._normalize_text(metadata_filters.get("sender") or "")
        subject_filter = self._normalize_text(metadata_filters.get("subject") or "")
        if sender_filter and sender_filter not in self._normalize_text(source.get("sender") or ""):
            return False
        if subject_filter and subject_filter not in self._normalize_text(source.get("subject") or ""):
            return False

        sent_at = self._parse_sent_at(source.get("sent_at"))
        date_from = self._parse_filter_date(metadata_filters.get("date_from"))
        date_to = self._parse_filter_date(metadata_filters.get("date_to"), end_of_day=True)

        if date_from is not None and sent_at < date_from:
            return False
        if date_to is not None and sent_at > date_to:
            return False
        return True

    def _answer_mode_for_intent(self, *, structured_intent: EmailSearchIntent, source_count: int, top_k: int):
        if structured_intent.output_mode in {"bullet_points", "table", "raw_list"}:
            return "multi_email"
        if structured_intent.intent in {"SUMMARIZE_THREADS", "FIND_CONTACT"}:
            return "multi_email"
        if source_count > 1 and top_k > 1:
            return "multi_email"
        return "single_email"

    def _build_cache_signature(self, *, structured_intent: EmailSearchIntent, top_k: int, category_filters: list[str], search_filters: dict, sources: list[dict]):
        payload = {
            "intent": structured_intent.model_dump(mode="json"),
            "top_k": top_k,
            "category_filters": category_filters,
            "search_filters": search_filters,
            "sources": [
                {
                    "id": source.get("gmail_message_id", ""),
                    "sent_at": source.get("sent_at", ""),
                    "score": round(float(source.get("score", 0.0)), 4),
                }
                for source in sources
            ],
        }
        return json.dumps(payload, sort_keys=True)

    def _normalize_search_filters(self, search_filters: dict | None):
        payload = dict(search_filters or {})
        return {
            "sender": (payload.get("sender") or "").strip(),
            "subject": (payload.get("subject") or "").strip(),
            "date_from": payload.get("date_from") or None,
            "date_to": payload.get("date_to") or None,
        }

    def _normalize_text(self, text: str):
        return " ".join("".join(character if character.isalnum() else " " for character in text.lower()).split())

    def _reference_date(self):
        return datetime.now(timezone.utc).date()

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

    def _parse_sent_at(self, sent_at: str | None):
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

    def _log_query_debug(
        self,
        *,
        question: str,
        structured_intent: EmailSearchIntent,
        execution_plan,
        top_k: int,
        category_filters: list[str],
        search_filters: dict,
        source_count: int,
    ):
        try:
            payload = {
                "question": question,
                "top_k": top_k,
                "category_filters": category_filters,
                "search_filters": search_filters,
                "intent": structured_intent.model_dump(mode="json"),
                "gmail_query": execution_plan.gmail_query,
                "metadata_filters": execution_plan.metadata_filters,
                "keyword_groups": execution_plan.keyword_groups,
                "semantic_query_text": execution_plan.semantic_query_text,
                "source_count": source_count,
            }
            _debug_logger.info(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return
