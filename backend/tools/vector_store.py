import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass
class VectorStore:
    path: Path

    def __post_init__(self):
        self._records_cache: list[dict] | None = None
        self._search_records_cache: list[dict] | None = None
        self._cache_lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def upsert(self, item_id: str, embedding: list[float], metadata: dict):
        records = self._load()
        records = [record for record in records if record["id"] != item_id]
        records.append({"id": item_id, "embedding": embedding, "metadata": metadata})
        self._save(records)

    def replace_for_email_ids(self, email_ids: list[int], new_records: list[dict]):
        records = self._load()
        if email_ids:
            target_ids = {str(email_id) for email_id in email_ids}
            records = [
                record
                for record in records
                if str(record.get("metadata", {}).get("email_id")) not in target_ids
            ]
        records.extend(new_records)
        self._save(records)

    def clear(self):
        self._save([])

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
        records = self._load_search_records()
        query_norm = self._vector_norm(query_embedding)
        query_terms = self._tokenize(query_text)
        scored = []
        for record in records:
            vector_score = self._cosine_similarity(
                query_embedding,
                record["embedding"],
                left_norm=query_norm,
                right_norm=record["embedding_norm"],
            )
            keyword_score = self._keyword_score(query_terms, record["search_text"])
            recency_score = self._recency_score(record["sent_at"])
            score = (vector_score * 0.68) + (keyword_score * 0.24) + (recency_score * 0.08)
            scored.append(
                {
                    "id": record["id"],
                    "metadata": record["metadata"],
                    "score": score,
                    "vector_score": vector_score,
                    "keyword_score": keyword_score,
                    "recency_score": recency_score,
                }
            )
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:top_k]

    def export_records(self):
        return list(self._load())

    def _load(self):
        with self._cache_lock:
            if self._records_cache is None:
                self._records_cache = json.loads(self.path.read_text(encoding="utf-8"))
            return self._records_cache

    def _load_search_records(self):
        with self._cache_lock:
            if self._search_records_cache is None:
                if self._records_cache is None:
                    self._records_cache = json.loads(self.path.read_text(encoding="utf-8"))
                self._search_records_cache = [
                    {
                        "id": record["id"],
                        "embedding": record["embedding"],
                        "embedding_norm": self._vector_norm(record["embedding"]),
                        "metadata": record["metadata"],
                        "search_text": self._build_search_text(record["metadata"]),
                        "sent_at": record.get("metadata", {}).get("sent_at"),
                    }
                    for record in self._records_cache
                ]
            return self._search_records_cache

    def _save(self, records: list[dict]):
        serialized = json.dumps(records, ensure_ascii=False, indent=2)
        self.path.write_text(serialized, encoding="utf-8")
        with self._cache_lock:
            self._records_cache = list(records)
            self._search_records_cache = None

    def _cosine_similarity(
        self,
        left: list[float],
        right: list[float],
        *,
        left_norm: float | None = None,
        right_norm: float | None = None,
    ):
        if not left or not right:
            return 0.0
        length = min(len(left), len(right))
        dot = sum(left[index] * right[index] for index in range(length))
        left_norm = left_norm if left_norm is not None else self._vector_norm(left)
        right_norm = right_norm if right_norm is not None else self._vector_norm(right)
        if not left_norm or not right_norm:
            return 0.0
        return dot / (left_norm * right_norm)

    def _vector_norm(self, values: list[float]):
        return math.sqrt(sum(value * value for value in values))

    def _keyword_score(self, query_terms: set[str], search_text: str):
        if not query_terms:
            return 0.0

        score = 0.0
        for term in query_terms:
            if term in search_text:
                score += 1.0

        max_score = max(float(len(query_terms)), 1.0)
        return min(score / max_score, 1.0)

    def _build_search_text(self, metadata: dict):
        attachment_names = metadata.get("attachment_names", [])
        if not isinstance(attachment_names, list):
            attachment_names = []
        return " \n".join(
            [
                str(metadata.get("subject", "")).lower(),
                str(metadata.get("sender", "")).lower(),
                str(metadata.get("snippet", "")).lower(),
                " ".join(str(name).lower() for name in attachment_names),
                str(metadata.get("document", "")).lower(),
            ]
        )

    def _tokenize(self, text: str):
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
        tokens = []
        for token in re.findall(r"[a-zA-Z0-9_]+", text.lower()):
            if len(token) <= 1 or token in stopwords:
                continue
            if token.endswith("s") and len(token) > 4:
                token = token[:-1]
            tokens.append(token)
        return set(tokens)

    def _recency_score(self, raw_sent_at):
        if not raw_sent_at:
            return 0.0
        if isinstance(raw_sent_at, str):
            try:
                sent_at = datetime.fromisoformat(raw_sent_at.replace("Z", "+00:00"))
            except ValueError:
                return 0.0
        else:
            sent_at = raw_sent_at
        if sent_at.tzinfo is None:
            sent_at = sent_at.replace(tzinfo=timezone.utc)
        age = max((datetime.now(timezone.utc) - sent_at).days, 0)
        if age <= 7:
            return 1.0
        if age <= 30:
            return 0.6
        if age <= 90:
            return 0.3
        return 0.0
