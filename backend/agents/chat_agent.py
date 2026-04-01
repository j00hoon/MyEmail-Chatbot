from dataclasses import dataclass
import re
from datetime import datetime, timezone

from schemas import ChatResponse, SourceReference
from config import settings
from skills.answer_generation import AnswerGenerationSkill
from skills.embedding_generation import EmbeddingGenerationSkill
from skills.vector_search import VectorSearchSkill
from tools.cache_store import CacheStore
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


@dataclass
class ChatAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore
    cache_store: CacheStore | None = None
    mailbox_id: str = "local_default"

    def run(self, question: str, top_k: int = 4):
        if not question.strip():
            raise ValueError("question must not be empty")

        use_cache = not self._should_bypass_cache(question)

        if self.cache_store is not None and use_cache:
            cached_response = self.cache_store.get_chat_response(
                mailbox_id=self.mailbox_id,
                question=question,
                top_k=top_k,
            )
            if cached_response is not None:
                return cached_response

        keyword_results = self.metadata_store.keyword_search(
            query=question,
            limit=max(top_k * 2, 6),
            scan_limit=(
                settings.keyword_search_scan_limit
                if settings.keyword_search_scan_limit > 0
                else None
            ),
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

        merged_sources = self._merge_sources(search_results, keyword_results, top_k)
        merged_sources = self._refine_sources_for_question(question, merged_sources, top_k)

        answer = AnswerGenerationSkill().execute(question=question, sources=merged_sources)

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
                for source in merged_sources
            ],
        )
        if self.cache_store is not None and use_cache:
            self.cache_store.set_chat_response(
                mailbox_id=self.mailbox_id,
                question=question,
                top_k=top_k,
                response=response,
            )
        return response

    def _should_bypass_cache(self, question: str):
        lowered = question.lower()
        return self._is_latest_question(question) or "from " in lowered

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
            sender_matches = [
                source for source in sources
                if sender_query in (source.get("sender") or "").lower()
            ]
            if sender_matches:
                sources = sender_matches

        if self._is_latest_question(question):
            sources = sorted(
                sources,
                key=lambda source: self._parse_sent_at(source.get("sent_at")),
                reverse=True,
            )

        return sources[:top_k]

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
        return " ".join(tokens).strip()

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
                from email.utils import parsedate_to_datetime
                parsed = parsedate_to_datetime(sent_at)
            except (TypeError, ValueError, IndexError):
                return datetime.min.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

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
                merged[key] = {
                    "subject": record.subject or "No Subject",
                    "sender": record.sender,
                    "sent_at": record.sent_at,
                    "snippet": record.snippet,
                    "attachment_names": record.attachment_names,
                    "document": record.body_text or record.snippet or "",
                    "gmail_message_id": key,
                    "score": keyword_boost,
                }
            else:
                merged[key]["score"] = max(merged[key]["score"], keyword_boost)

        ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
        return ranked[:top_k]
