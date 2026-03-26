import json
import math
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VectorStore:
    path: Path

    def __post_init__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def upsert(self, item_id: str, embedding: list[float], metadata: dict):
        records = self._load()
        records = [record for record in records if record["id"] != item_id]
        records.append({"id": item_id, "embedding": embedding, "metadata": metadata})
        self._save(records)

    def delete_by_email_ids(self, email_ids: list[int]):
        if not email_ids:
            return
        allowed = {str(email_id) for email_id in email_ids}
        records = self._load()
        records = [
            record
            for record in records
            if str(record.get("metadata", {}).get("email_id")) not in allowed
        ]
        self._save(records)

    def search(self, query_embedding: list[float], query_text: str, top_k: int):
        records = self._load()
        query_terms = self._tokenize(query_text)
        scored = []
        for record in records:
            vector_score = self._cosine_similarity(query_embedding, record["embedding"])
            keyword_score = self._keyword_score(query_terms, record["metadata"])
            score = (vector_score * 0.7) + (keyword_score * 0.3)
            scored.append(
                {
                    "id": record["id"],
                    "metadata": record["metadata"],
                    "score": score,
                    "vector_score": vector_score,
                    "keyword_score": keyword_score,
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def _load(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, records: list[dict]):
        self.path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    def _cosine_similarity(self, left: list[float], right: list[float]):
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        dot = sum(left[index] * right[index] for index in range(length))
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _keyword_score(self, query_terms: set[str], metadata: dict):
        if not query_terms:
            return 0.0
        haystack = " ".join(
            [
                metadata.get("subject", ""),
                metadata.get("sender", ""),
                metadata.get("snippet", ""),
                metadata.get("document", ""),
                " ".join(metadata.get("attachment_names", [])),
            ]
        ).lower()
        if not haystack.strip():
            return 0.0

        matched = sum(1 for term in query_terms if term in haystack)
        return matched / max(len(query_terms), 1)

    def _tokenize(self, text: str):
        return {token for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()) if len(token) > 1}
