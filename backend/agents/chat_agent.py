from dataclasses import dataclass

from schemas import ChatResponse, SourceReference
from skills.answer_generation import AnswerGenerationSkill
from skills.embedding_generation import EmbeddingGenerationSkill
from skills.vector_search import VectorSearchSkill
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


@dataclass
class ChatAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore

    def run(self, question: str, top_k: int = 4):
        if not question.strip():
            raise ValueError("question must not be empty")

        embedder = EmbeddingGenerationSkill()
        query_embedding = embedder.execute(question)
        search_results = VectorSearchSkill(vector_store=self.vector_store).execute(
            query_embedding=query_embedding,
            query_text=question,
            top_k=max(top_k * 3, 8),
        )
        keyword_results = self.metadata_store.keyword_search(
            query=question,
            limit=max(top_k * 2, 6),
        )

        merged_sources = self._merge_sources(search_results, keyword_results, top_k)

        answer = AnswerGenerationSkill().execute(question=question, sources=merged_sources)

        return ChatResponse(
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
