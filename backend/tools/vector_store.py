import json
import math
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock


@dataclass
class VectorStore:
    database_url: str
    legacy_path: Path | None = None

    def __post_init__(self):
        self._records_cache: dict[str, list[dict]] | None = None
        self._search_records_cache: dict[str, list[dict]] | None = None
        self._cache_lock = Lock()
        self.db_path = self._resolve_sqlite_path(self.database_url)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()
        self._migrate_legacy_file_if_needed()

    def upsert(self, item_id: str, embedding: list[float], metadata: dict):
        account_id = str(metadata.get("account_id") or "local_default")
        self.replace_for_email_ids(
            account_id=account_id,
            email_ids=[int(metadata["email_id"])] if metadata.get("email_id") is not None else [],
            new_records=[{"id": item_id, "embedding": embedding, "metadata": metadata}],
        )

    def replace_for_email_ids(self, account_id: str, email_ids: list[int], new_records: list[dict]):
        with self._connect() as connection:
            if email_ids:
                placeholders = ",".join("?" for _ in email_ids)
                connection.execute(
                    f"DELETE FROM email_vectors WHERE account_id = ? AND email_id IN ({placeholders})",
                    [account_id, *[int(email_id) for email_id in email_ids]],
                )

            payloads = [
                (
                    record["id"],
                    str(record.get("metadata", {}).get("account_id") or account_id),
                    int(record.get("metadata", {}).get("email_id") or 0),
                    record.get("metadata", {}).get("gmail_message_id", ""),
                    record.get("metadata", {}).get("sent_at"),
                    json.dumps(record["embedding"], ensure_ascii=False),
                    json.dumps(record["metadata"], ensure_ascii=False),
                )
                for record in new_records
            ]
            if payloads:
                connection.executemany(
                    """
                    INSERT OR REPLACE INTO email_vectors (
                        chunk_id,
                        account_id,
                        email_id,
                        gmail_message_id,
                        sent_at,
                        embedding_json,
                        metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    payloads,
                )
            connection.commit()
        self._invalidate_cache()

    def clear(self, account_id: str | None = None):
        with self._connect() as connection:
            if account_id is None:
                connection.execute("DELETE FROM email_vectors")
            else:
                connection.execute("DELETE FROM email_vectors WHERE account_id = ?", [account_id])
            connection.commit()
        self._invalidate_cache()

    def delete_by_email_ids(self, email_ids: list[int], account_id: str):
        if not email_ids:
            return
        with self._connect() as connection:
            placeholders = ",".join("?" for _ in email_ids)
            connection.execute(
                f"DELETE FROM email_vectors WHERE account_id = ? AND email_id IN ({placeholders})",
                [account_id, *[int(email_id) for email_id in email_ids]],
            )
            connection.commit()
        self._invalidate_cache()

    def delete_trashed(self, account_id: str | None = None):
        with self._connect() as connection:
            if account_id is None:
                connection.execute(
                    """
                    DELETE FROM email_vectors
                    WHERE EXISTS (
                        SELECT 1
                        FROM emails
                        WHERE emails.id = email_vectors.email_id
                          AND emails.account_id = email_vectors.account_id
                          AND emails.raw_payload LIKE '%"TRASH"%'
                    )
                    """
                )
            else:
                connection.execute(
                    """
                    DELETE FROM email_vectors
                    WHERE account_id = ?
                      AND EXISTS (
                        SELECT 1
                        FROM emails
                        WHERE emails.id = email_vectors.email_id
                          AND emails.account_id = email_vectors.account_id
                          AND emails.raw_payload LIKE '%"TRASH"%'
                    )
                    """,
                    [account_id],
                )
            connection.commit()
        self._invalidate_cache()

    def migrate_account_id(self, from_account_id: str, to_account_id: str):
        if not from_account_id or not to_account_id or from_account_id == to_account_id:
            return False

        with self._connect() as connection:
            target_count = connection.execute(
                "SELECT COUNT(*) FROM email_vectors WHERE account_id = ?",
                [to_account_id],
            ).fetchone()[0]
            if target_count:
                return False

            rows = connection.execute(
                """
                SELECT chunk_id, metadata_json
                FROM email_vectors
                WHERE account_id = ?
                """,
                [from_account_id],
            ).fetchall()
            if not rows:
                return False

            for row in rows:
                metadata = json.loads(row["metadata_json"])
                metadata["account_id"] = to_account_id
                connection.execute(
                    """
                    UPDATE email_vectors
                    SET account_id = ?, metadata_json = ?
                    WHERE chunk_id = ?
                    """,
                    [
                        to_account_id,
                        json.dumps(metadata, ensure_ascii=False),
                        row["chunk_id"],
                    ],
                )
            connection.commit()
        self._invalidate_cache()
        return True

    def search(self, query_embedding: list[float], query_text: str, top_k: int, account_id: str | None = None):
        records = self._load_search_records(account_id=account_id)
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

    def export_records(self, account_id: str | None = None):
        return list(self._load(account_id=account_id))

    def _load(self, account_id: str | None = None):
        with self._cache_lock:
            cache_key = account_id or "__all__"
            if self._records_cache is None:
                self._records_cache = {}
            if cache_key not in self._records_cache:
                with self._connect() as connection:
                    if account_id is None:
                        rows = connection.execute(
                            """
                            SELECT chunk_id, embedding_json, metadata_json
                            FROM email_vectors
                            ORDER BY rowid
                            """
                        ).fetchall()
                    else:
                        rows = connection.execute(
                            """
                            SELECT chunk_id, embedding_json, metadata_json
                            FROM email_vectors
                            WHERE account_id = ?
                            ORDER BY rowid
                            """,
                            [account_id],
                        ).fetchall()
                self._records_cache[cache_key] = [
                    {
                        "id": row["chunk_id"],
                        "embedding": json.loads(row["embedding_json"]),
                        "metadata": json.loads(row["metadata_json"]),
                    }
                    for row in rows
                ]
            return self._records_cache[cache_key]

    def _load_search_records(self, account_id: str | None = None):
        with self._cache_lock:
            cache_key = account_id or "__all__"
            if self._search_records_cache is None:
                self._search_records_cache = {}
            if cache_key not in self._search_records_cache:
                records = self._load(account_id=account_id)
                self._search_records_cache[cache_key] = [
                    {
                        "id": record["id"],
                        "embedding": record["embedding"],
                        "embedding_norm": self._vector_norm(record["embedding"]),
                        "metadata": record["metadata"],
                        "search_text": self._build_search_text(record["metadata"]),
                        "sent_at": record.get("metadata", {}).get("sent_at"),
                    }
                    for record in records
                ]
            return self._search_records_cache[cache_key]

    def _ensure_schema(self):
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS email_vectors (
                    chunk_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL DEFAULT 'local_default',
                    email_id INTEGER NOT NULL,
                    gmail_message_id TEXT,
                    sent_at TEXT,
                    embedding_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            try:
                connection.execute("ALTER TABLE email_vectors ADD COLUMN account_id TEXT NOT NULL DEFAULT 'local_default'")
            except sqlite3.OperationalError:
                pass
            connection.execute("CREATE INDEX IF NOT EXISTS idx_email_vectors_account_id ON email_vectors (account_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_email_vectors_email_id ON email_vectors (email_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_email_vectors_gmail_message_id ON email_vectors (gmail_message_id)")
            connection.commit()

    def _migrate_legacy_file_if_needed(self):
        if self.legacy_path is None or not self.legacy_path.exists():
            return

        with self._connect() as connection:
            existing_count = connection.execute("SELECT COUNT(*) FROM email_vectors").fetchone()[0]
            if existing_count:
                return

        try:
            records = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        payloads = []
        for record in records:
            metadata = record.get("metadata", {})
            email_id = int(metadata.get("email_id") or 0)
            if not email_id:
                continue
            payloads.append(
                (
                    record.get("id", ""),
                    str(metadata.get("account_id") or "local_default"),
                    email_id,
                    metadata.get("gmail_message_id", ""),
                    metadata.get("sent_at"),
                    json.dumps(record.get("embedding", []), ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                )
            )

        if not payloads:
            return

        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO email_vectors (
                    chunk_id,
                    account_id,
                    email_id,
                    gmail_message_id,
                    sent_at,
                    embedding_json,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                payloads,
            )
            connection.commit()
        self._invalidate_cache()

    def _connect(self):
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL;")
        connection.execute("PRAGMA synchronous=NORMAL;")
        connection.execute("PRAGMA busy_timeout=30000;")
        return connection

    def _invalidate_cache(self):
        with self._cache_lock:
            self._records_cache = None
            self._search_records_cache = None

    def _resolve_sqlite_path(self, database_url: str):
        if not database_url.startswith("sqlite:///"):
            raise ValueError("VectorStore requires a sqlite:/// database URL.")
        return Path(database_url.replace("sqlite:///", "", 1))

    def _cosine_similarity(self, left: list[float], right: list[float], *, left_norm: float | None = None, right_norm: float | None = None):
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
            "a", "about", "an", "and", "any", "are", "can", "do", "emails", "find", "for",
            "from", "have", "how", "i", "in", "is", "it", "mail", "me", "my", "of", "on",
            "or", "related", "show", "tell", "that", "the", "this", "to", "we", "what",
            "which", "with", "you",
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
            normalized = raw_sent_at.strip()
            if " (" in normalized:
                normalized = normalized.split(" (", 1)[0]
            try:
                sent_at = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
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
