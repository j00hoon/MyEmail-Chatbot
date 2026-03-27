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

    def run(self, email_ids: list[int] | None = None, progress_callback=None):
        emails = self.metadata_store.get_emails_for_indexing(email_ids=email_ids)
        parser = TextParsingSkill()
        chunker = TextChunkingSkill()
        embedder = EmbeddingGenerationSkill()
        indexed_count = 0
        target_ids = [email.id for email in emails]
        self.vector_store.delete_by_email_ids(target_ids)
        total = max(len(emails), 1)

        if progress_callback is not None:
            progress_callback(
                stage="Refreshing vector index",
                progress=60,
                detail=f"Rebuilding retrieval index for {len(emails)} emails.",
                indexed_count=0,
            )

        for position, email in enumerate(emails, start=1):
            document = parser.execute(email)
            chunks = chunker.execute(document) or [document]
            for index, chunk in enumerate(chunks):
                embedding = embedder.execute(chunk)
                self.vector_store.upsert(
                    item_id=f"{email.id}:{index}",
                    embedding=embedding,
                    metadata={
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
                )
            self.metadata_store.mark_indexed(
                email.id,
                indexed_at=datetime.now(timezone.utc),
            )
            indexed_count += 1
            if progress_callback is not None:
                progress_callback(
                    stage="Refreshing vector index",
                    progress=60 + int((position / total) * 30),
                    detail=f"Indexed {indexed_count} of {len(emails)} emails for search.",
                    indexed_count=indexed_count,
                )

        return IndexingResult(indexed_count=indexed_count, saved_count=len(emails))
