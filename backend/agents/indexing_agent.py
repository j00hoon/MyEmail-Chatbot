from dataclasses import dataclass
from datetime import datetime, timezone

from skills.embedding_generation import EmbeddingGenerationSkill
from skills.text_chunking import TextChunkingSkill
from skills.text_parsing import TextParsingSkill
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


@dataclass
class IndexingResult:
    indexed_count: int
    saved_count: int


@dataclass
class IndexingAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore

    def run(self, email_ids: list[int] | None = None, progress_callback=None, only_unindexed: bool = False):
        if email_ids is not None and not email_ids:
            if progress_callback is not None:
                progress_callback(
                    stage="Refreshing vector index",
                    progress=90,
                    detail="No new or updated email content required reindexing.",
                    indexed_count=0,
                )
            return IndexingResult(indexed_count=0, saved_count=0)

        if only_unindexed:
            emails = self.metadata_store.get_unindexed_emails_for_indexing()
        else:
            emails = self.metadata_store.get_emails_for_indexing(email_ids=email_ids)
        parser = TextParsingSkill()
        chunker = TextChunkingSkill()
        embedder = EmbeddingGenerationSkill()
        indexed_count = 0
        total = max(len(emails), 1)
        batch_size = 25

        if progress_callback is not None:
            progress_callback(
                stage="Refreshing vector index",
                progress=60,
                detail=f"Rebuilding retrieval index for {len(emails)} emails.",
                indexed_count=0,
            )

        for offset in range(0, len(emails), batch_size):
            email_batch = emails[offset : offset + batch_size]
            batch_ids = [email.id for email in email_batch]
            chunk_payloads: list[dict] = []
            chunk_texts: list[str] = []

            for email in email_batch:
                document = parser.execute(email)
                chunks = chunker.execute(document) or [document]
                for index, chunk in enumerate(chunks):
                    chunk_texts.append(chunk)
                    chunk_payloads.append(
                        {
                            "id": f"{email.id}:{index}",
                            "metadata": {
                                "email_id": email.id,
                                "gmail_message_id": email.gmail_message_id,
                                "subject": email.subject,
                                "sender": email.sender,
                                "sent_at": email.sent_at,
                                "snippet": email.snippet,
                                "attachment_names": email.attachment_names,
                                "document": chunk,
                                "chunk_index": index,
                            },
                        }
                    )

            embeddings = embedder.execute_many(chunk_texts)
            vector_records = []
            for payload, embedding in zip(chunk_payloads, embeddings):
                vector_records.append(
                    {
                        "id": payload["id"],
                        "embedding": embedding,
                        "metadata": payload["metadata"],
                    }
                )

            self.vector_store.replace_for_email_ids(batch_ids, vector_records)
            self.metadata_store.mark_indexed_batch(
                batch_ids,
                indexed_at=datetime.now(timezone.utc),
            )
            indexed_count += len(email_batch)
            if progress_callback is not None:
                progress_callback(
                    stage="Refreshing vector index",
                    progress=60 + int((indexed_count / total) * 30),
                    detail=f"Indexed {indexed_count} of {len(emails)} emails for search.",
                    indexed_count=indexed_count,
                )

        return IndexingResult(indexed_count=indexed_count, saved_count=len(emails))
