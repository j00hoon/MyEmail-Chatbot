import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from config import settings
from retrieval.mailbox_query import CandidateSelector, QueryAnalyzer, RetrievalPlanner
from retrieval.runtime_retriever import build_runtime_retriever
from schemas import ChatResponse, SourceReference
from skills.answer_generation import AnswerGenerationSkill
from skills.embedding_generation import EmbeddingGenerationSkill
from skills.vector_search import VectorSearchSkill
from tools.cache_store import CacheStore
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


@dataclass
class QuestionIntent:
    kind: str
    normalized_question: str
    sender_query: str = ""
    requested_count: int = 1
    window_days: int | None = None


@dataclass
class ChatAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore
    cache_store: CacheStore | None = None
    mailbox_id: str = "local_default"
    _runtime_retriever = None
    _runtime_retriever_signature: tuple[int, int] | None = None
    _query_analyzer: QueryAnalyzer = QueryAnalyzer()
    _retrieval_planner: RetrievalPlanner = RetrievalPlanner()
    _candidate_selector: CandidateSelector = CandidateSelector()

    def run(self, question: str, top_k: int = 4):
        if not question.strip():
            raise ValueError("question must not be empty")

        intent = self._classify_question(question=question, top_k=top_k)
        sources = self._retrieve_sources(question=question, intent=intent, top_k=top_k)
        cache_signature = self._build_cache_signature(intent=intent, top_k=top_k, sources=sources)

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
            answer_mode=("multi_email" if intent.kind in {"top_recent_important", "recent_email_list"} else "single_email"),
        )

        response = ChatResponse(
            answer=answer,
            sources=[
                SourceReference(
                    gmail_message_id=source["gmail_message_id"],
                    subject=source["subject"],
                    sender=source["sender"],
                    sent_at=source["sent_at"],
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

    def _classify_question(self, question: str, top_k: int):
        analysis = self._query_analyzer.analyze(question=question, default_count=top_k)
        plan = self._retrieval_planner.build(analysis)
        return QuestionIntent(
            kind=plan.kind,
            normalized_question=plan.normalized_question,
            sender_query=plan.sender_query,
            requested_count=plan.requested_count,
            window_days=plan.window_days,
        )

    def _retrieve_sources(self, question: str, intent: QuestionIntent, top_k: int):
        if intent.kind == "recent_email_list":
            return self._retrieve_recent_email_list(intent=intent)

        langchain_sources = self._retrieve_with_langchain(question=question, intent=intent, top_k=top_k)
        if langchain_sources:
            return langchain_sources

        if intent.kind in {"latest_from", "sender_lookup"}:
            return self._retrieve_sender_sources(question=question, intent=intent, top_k=top_k)
        if intent.kind == "date_lookup":
            return self._retrieve_date_sources(question=question, intent=intent, top_k=top_k)
        if intent.kind == "top_recent_important":
            return self._retrieve_top_recent_important(intent=intent)
        return self._retrieve_hybrid_sources(question=question, intent=intent, top_k=top_k)

    def _retrieve_recent_email_list(self, intent: QuestionIntent):
        records = self.metadata_store.get_emails_for_indexing()
        selected = self._candidate_selector.select_recent_emails(
            records=records,
            requested_count=intent.requested_count,
            window_days=intent.window_days,
        )
        return [
            self._source_from_record(record, score=1.0)
            for record in selected
        ]

    def _retrieve_with_langchain(self, question: str, intent: QuestionIntent, top_k: int):
        if intent.kind != "general":
            return []

        runtime = self._get_runtime_retriever()
        if runtime is None:
            return []

        try:
            documents = runtime.retrieve(question, mode="multi_query")
        except Exception:
            return []

        sources = self._sources_from_documents(documents)
        if not sources:
            return []

        if intent.kind in {"latest_from", "sender_lookup"}:
            sources = self._filter_sources_by_sender(sources, intent.sender_query)
        if intent.kind == "date_lookup":
            sources = self._rerank_date_lookup_sources(question, sources)
        if intent.kind == "top_recent_important":
            sources = sorted(sources, key=self._importance_sort_key, reverse=True)
        if self._is_latest_question(question):
            sources = sorted(sources, key=lambda source: self._parse_sent_at(source.get("sent_at")), reverse=True)

        deduped = []
        seen = set()
        for source in sources:
            key = source.get("gmail_message_id", "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(source)

        return deduped[: max(1, top_k)]

    def _get_runtime_retriever(self):
        if not settings.langchain_retrieval_enabled:
            return None

        vector_records = self.vector_store.export_records()
        signature = (len(vector_records), hash(tuple(record.get("id", "") for record in vector_records[:25])))

        if self._runtime_retriever is None or self._runtime_retriever_signature != signature:
            self._runtime_retriever = build_runtime_retriever(vector_records)
            self._runtime_retriever_signature = signature

        return self._runtime_retriever

    def _retrieve_sender_sources(self, question: str, intent: QuestionIntent, top_k: int):
        limit = max(top_k * 3, 12)
        keyword_results = self.metadata_store.keyword_search(
            query=question,
            limit=limit,
            scan_limit=(settings.keyword_search_scan_limit if settings.keyword_search_scan_limit > 0 else None),
        )
        sources = self._merge_sources([], keyword_results, limit)
        sources = self._filter_sources_by_sender(sources, intent.sender_query)

        if not sources:
            sources = self._lookup_sender_candidates(intent.sender_query)

        if self._is_latest_question(question):
            sources = sorted(sources, key=lambda source: self._parse_sent_at(source.get("sent_at")), reverse=True)

        return sources[: max(1, min(top_k, 4))]

    def _retrieve_date_sources(self, question: str, intent: QuestionIntent, top_k: int):
        limit = max(top_k * 3, 10)
        keyword_results = self.metadata_store.keyword_search(
            query=question,
            limit=limit,
            scan_limit=(settings.keyword_search_scan_limit if settings.keyword_search_scan_limit > 0 else None),
        )
        sources = self._merge_sources([], keyword_results, limit)
        sources = self._refine_sources_for_question(question, sources, limit)
        sources = self._rerank_date_lookup_sources(question, sources)
        return sources[: max(1, min(top_k, 4))]

    def _retrieve_top_recent_important(self, intent: QuestionIntent):
        cutoff = datetime.now(timezone.utc) - timedelta(days=intent.window_days or 7)
        candidates = []
        for record in self.metadata_store.get_emails_for_indexing():
            sent_at = self._parse_sent_at(record.sent_at)
            if sent_at < cutoff:
                continue

            source = self._source_from_record(record, score=0.0)
            source["score"] = self._importance_score(source)
            candidates.append(source)

        candidates.sort(
            key=lambda source: (source["score"], self._parse_sent_at(source.get("sent_at"))),
            reverse=True,
        )
        return candidates[: intent.requested_count]

    def _retrieve_hybrid_sources(self, question: str, intent: QuestionIntent, top_k: int):
        keyword_results = self.metadata_store.keyword_search(
            query=question,
            limit=max(top_k * 2, 6),
            scan_limit=(settings.keyword_search_scan_limit if settings.keyword_search_scan_limit > 0 else None),
        )

        search_results = []
        if not self._should_skip_vector_search(question, keyword_results, top_k):
            embedder = EmbeddingGenerationSkill()
            query_embedding = embedder.execute(question)
            search_results = VectorSearchSkill(vector_store=self.vector_store).execute(
                query_embedding=query_embedding,
                query_text=question,
                top_k=max(top_k * 3, 8),
            )

        merged_sources = self._merge_sources(search_results, keyword_results, max(top_k * 2, 8))
        return self._refine_sources_for_question(question, merged_sources, top_k)

    def _build_cache_signature(self, intent: QuestionIntent, top_k: int, sources: list[dict]):
        payload = {
            "kind": intent.kind,
            "normalized_question": intent.normalized_question,
            "sender_query": intent.sender_query,
            "requested_count": intent.requested_count,
            "window_days": intent.window_days,
            "top_k": top_k,
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

    def _should_skip_vector_search(self, question: str, keyword_results: list[dict], top_k: int):
        if not keyword_results:
            return False

        top_keyword_score = keyword_results[0]["score"]
        keyword_hit_count = len(keyword_results)
        has_numeric_anchor = bool(re.search(r"\d", question))

        if top_keyword_score >= 8.0:
            return True

        if has_numeric_anchor and top_keyword_score >= 5.0:
            return True

        if keyword_hit_count >= max(2, min(top_k, 3)) and top_keyword_score >= 6.0:
            return True

        return False

    def _refine_sources_for_question(self, question: str, sources: list[dict], top_k: int):
        sender_query = self._extract_sender_query(question)
        if sender_query:
            sender_matches = self._filter_sources_by_sender(sources, sender_query)
            if sender_matches:
                sources = sender_matches

        if self._is_latest_question(question):
            sources = sorted(
                sources,
                key=lambda source: self._parse_sent_at(source.get("sent_at")),
                reverse=True,
            )

        return sources[:top_k]

    def _lookup_sender_candidates(self, sender_query: str):
        matches = []
        for record in self.metadata_store.get_emails_for_indexing():
            if sender_query in self._normalize_question(record.sender or ""):
                matches.append(self._source_from_record(record, score=10.0))
        matches.sort(key=lambda source: self._parse_sent_at(source.get("sent_at")), reverse=True)
        return matches

    def _filter_sources_by_sender(self, sources: list[dict], sender_query: str):
        normalized_query = self._normalize_question(sender_query)
        return [
            source
            for source in sources
            if normalized_query and normalized_query in self._normalize_question(source.get("sender") or "")
        ]

    def _importance_score(self, source: dict):
        subject = (source.get("subject") or "").lower()
        sender = (source.get("sender") or "").lower()
        snippet = (source.get("snippet") or "").lower()
        content = f"{subject} {sender} {snippet}"

        score = 0.0

        important_terms = {
            "interview": 5.0,
            "insurance": 4.0,
            "record": 3.5,
            "invoice": 4.0,
            "receipt": 4.0,
            "statement": 3.5,
            "action required": 4.5,
            "urgent": 4.0,
            "application": 3.0,
            "approval": 3.5,
            "state farm": 4.0,
            "holy name": 4.0,
            "re:": 1.5,
        }
        promotional_terms = {
            "sale": -5.0,
            "off": -2.0,
            "deal": -3.0,
            "love": -2.5,
            "new arrivals": -3.0,
            "vip": -2.5,
            "newsletter": -3.0,
            "shop": -2.0,
            "discount": -2.0,
        }

        for term, weight in important_terms.items():
            if term in content:
                score += weight
        for term, weight in promotional_terms.items():
            if term in content:
                score += weight

        if source.get("attachment_names"):
            score += 1.5

        if "noreply" in sender or "no-reply" in sender:
            score -= 1.0

        if "@gmail.com" not in sender:
            score += 0.6

        sent_at = self._parse_sent_at(source.get("sent_at"))
        age_hours = max((datetime.now(timezone.utc) - sent_at).total_seconds() / 3600, 0.0)
        score += max(0.0, 2.5 - min(age_hours / 24.0, 2.5))

        return score

    def _importance_sort_key(self, source: dict):
        return (self._importance_score(source), self._parse_sent_at(source.get("sent_at")))

    def _rerank_date_lookup_sources(self, question: str, sources: list[dict]):
        lowered = question.lower()
        if "receive" not in lowered and "received" not in lowered:
            return sources

        def rank(source: dict):
            sender = (source.get("sender") or "").lower()
            subject = (source.get("subject") or "").lower()
            score = float(source.get("score", 0.0))

            if "@gmail.com" not in sender:
                score += 2.5
            if subject.startswith("re:"):
                score -= 0.4
            if "inquiry" in subject:
                score -= 1.0

            return (score, self._parse_sent_at(source.get("sent_at")))

        return sorted(sources, key=rank, reverse=True)

    def _extract_sender_query(self, question: str):
        lowered = question.lower().strip()
        match = re.search(r"\bfrom\s+(.+?)(?:\?|$)", lowered)
        if not match:
            return ""

        candidate = re.sub(r"[^a-z0-9@\.\s_-]", " ", match.group(1))
        tokens = [
            token
            for token in candidate.split()
            if token not in {"the", "a", "an", "latest", "recent", "newest", "last", "email", "emails"}
        ]
        sender_query = " ".join(tokens).strip()
        if not sender_query:
            return ""
        if not re.search(r"[a-z@]", sender_query):
            return ""
        return sender_query

    def _normalize_question(self, text: str):
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return " ".join(tokens)

    def _is_latest_question(self, question: str):
        lowered = question.lower()
        return any(term in lowered for term in ("latest", "recent", "newest", "last"))

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

    def _source_from_record(self, record, score: float):
        return {
            "subject": record.subject or "No Subject",
            "sender": record.sender,
            "sent_at": record.sent_at,
            "snippet": record.snippet,
            "attachment_names": record.attachment_names,
            "document": record.body_text or record.snippet or "",
            "gmail_message_id": record.gmail_message_id,
            "score": score,
        }

    def _sources_from_documents(self, documents):
        sources = []
        for document in documents or []:
            metadata = getattr(document, "metadata", {}) or {}
            page_content = getattr(document, "page_content", "") or ""
            sources.append(
                {
                    "subject": metadata.get("subject") or "No Subject",
                    "sender": metadata.get("sender"),
                    "sent_at": metadata.get("date") or metadata.get("sent_at"),
                    "snippet": page_content[:240],
                    "attachment_names": metadata.get("attachment_names", []),
                    "document": page_content,
                    "gmail_message_id": metadata.get("gmail_message_id", ""),
                    "score": 1.0,
                }
            )
        return sources

    def _merge_sources(self, vector_results: list[dict], keyword_results: list[dict], top_k: int):
        merged = {}

        for result in vector_results:
            metadata = result["metadata"]
            key = metadata.get("gmail_message_id", "")
            if key not in merged:
                merged[key] = {
                    "subject": metadata.get("subject") or "No Subject",
                    "sender": metadata.get("sender"),
                    "sent_at": metadata.get("sent_at"),
                    "snippet": metadata.get("snippet"),
                    "attachment_names": metadata.get("attachment_names", []),
                    "document": metadata.get("document", ""),
                    "gmail_message_id": key,
                    "score": result["score"],
                }
            else:
                merged[key]["score"] = max(merged[key]["score"], result["score"])
                if len(metadata.get("document", "")) > len(merged[key]["document"]):
                    merged[key]["document"] = metadata.get("document", "")

        for item in keyword_results:
            record = item["record"]
            key = record.gmail_message_id
            keyword_boost = 0.35 + (item["score"] * 0.65)
            if key not in merged:
                merged[key] = self._source_from_record(record, score=keyword_boost)
            else:
                merged[key]["score"] = max(merged[key]["score"], keyword_boost)

        ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]
