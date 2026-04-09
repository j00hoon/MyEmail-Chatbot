from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from retrieval.mailbox_query import GmailQueryBuilder, QueryAnalyzer, QueryExecutionPlanner
from retrieval.reranker import CandidateReranker
from retrieval.retrievers import LexicalRetriever, MetadataRetriever, SemanticRetriever
from schemas import ChatResponse, EmailSearchIntent, SourceReference
from skills.answer_generation import AnswerGenerationSkill
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
    metadata_retriever: MetadataRetriever = field(init=False)
    lexical_retriever: LexicalRetriever = field(default_factory=LexicalRetriever)
    semantic_retriever: SemanticRetriever = field(init=False)
    reranker: CandidateReranker = field(default_factory=CandidateReranker)

    def __post_init__(self):
        self.execution_planner = QueryExecutionPlanner(gmail_query_builder=self.gmail_query_builder)
        self.metadata_retriever = MetadataRetriever(metadata_store=self.metadata_store)
        self.semantic_retriever = SemanticRetriever(vector_store=self.vector_store)

    def run(self, question: str, top_k: int = 4, category_filters: list[str] | None = None, search_filters: dict | None = None, account_id: str | None = None):
        if not question.strip():
            raise ValueError("question must not be empty")

        mailbox_id = account_id or self.mailbox_id
        category_filters = sorted(set(category_filters or []))
        normalized_filters = self._normalize_search_filters(search_filters)
        reference_date = self._reference_date()
        structured_intent = self.query_analyzer.analyze(question=question, reference_date=reference_date)
        execution_plan = self.execution_planner.build(
            account_id=mailbox_id,
            question=question,
            structured_intent=structured_intent,
            reference_date=reference_date,
            category_filters=category_filters,
            search_filters=normalized_filters,
        )

        sources = self._retrieve_sources(execution_plan=execution_plan, top_k=top_k)
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
                mailbox_id=mailbox_id,
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
                mailbox_id=mailbox_id,
                cache_signature=cache_signature,
                response=response,
            )

        return response

    def _retrieve_sources(self, *, execution_plan, top_k: int):
        metadata_candidates = self.metadata_retriever.retrieve(execution_plan)
        lexical_candidates = self.lexical_retriever.retrieve(execution_plan, metadata_candidates)

        semantic_candidates = []
        if execution_plan.strategy in {"hybrid", "semantic"}:
            semantic_candidates = self.semantic_retriever.retrieve(execution_plan)

        ranked_candidates = self.reranker.rerank(
            execution_plan=execution_plan,
            candidates=[*metadata_candidates, *lexical_candidates, *semantic_candidates],
        )

        if execution_plan.selection_policy == "all":
            selected = self.reranker.select(execution_plan=execution_plan, candidates=ranked_candidates)
        elif execution_plan.selection_policy == "best_match":
            selected = ranked_candidates[:1]
        else:
            selected = self.reranker.select(
                execution_plan=execution_plan,
                candidates=ranked_candidates[: max(execution_plan.result_limit, top_k)],
            )

        return [candidate.to_source() for candidate in selected]

    def _answer_mode_for_intent(self, *, structured_intent: EmailSearchIntent, source_count: int, top_k: int):
        if structured_intent.output_mode in {"bullet_points", "table", "raw_list"}:
            return "multi_email"
        if structured_intent.intent in {"SUMMARIZE_THREADS", "FIND_CONTACT"}:
            return "multi_email"
        if structured_intent.result_scope == "all":
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

    def _reference_date(self):
        return datetime.now(timezone.utc).date()

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
                "strategy": execution_plan.strategy,
                "selection_policy": execution_plan.selection_policy,
                "result_limit": execution_plan.result_limit,
                "candidate_limit": execution_plan.candidate_limit,
                "gmail_query": execution_plan.gmail_query,
                "metadata_filters": execution_plan.metadata_filters,
                "keyword_terms": execution_plan.keyword_terms,
                "semantic_query_text": execution_plan.semantic_query_text,
                "source_count": source_count,
            }
            _debug_logger.info(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return
