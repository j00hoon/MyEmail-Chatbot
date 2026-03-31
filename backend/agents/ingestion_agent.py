from dataclasses import dataclass

from skills.gmail_fetch import GmailFetchSkill
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore
from tools.gmail_client import GmailClient, HistoryIdExpiredError


@dataclass
class IngestionResult:
    mode: str
    saved_emails: list
    fetched_count: int
    deleted_count: int
    history_id: str


@dataclass
class IngestionAgent:
    metadata_store: MetadataStore
    vector_store: VectorStore

    def run(self, max_results: int, progress_callback=None):
        history_id = self.metadata_store.get_sync_value("historyId")
        pending_history_id = self.metadata_store.get_sync_value("pendingHistoryId")

        if history_id:
            try:
                return self._run_incremental_sync(history_id=history_id, progress_callback=progress_callback)
            except HistoryIdExpiredError:
                if progress_callback is not None:
                    progress_callback(
                        stage="Connecting to Gmail",
                        progress=8,
                        detail="Stored Gmail history expired. Falling back to full mailbox sync.",
                    )

        if pending_history_id and self.metadata_store.count_emails() > 0:
            return self._resume_full_sync(
                history_id=pending_history_id,
                progress_callback=progress_callback,
            )

        if (
            not history_id
            and not pending_history_id
            and self.metadata_store.count_emails() > 0
            and self.metadata_store.count_unindexed_emails() > 0
        ):
            resumed_history_id = GmailClient().get_current_history_id()
            self.metadata_store.set_sync_value("pendingHistoryId", resumed_history_id)
            return self._resume_full_sync(
                history_id=resumed_history_id,
                progress_callback=progress_callback,
            )

        return self._run_full_sync(progress_callback=progress_callback)

    def _run_full_sync(self, progress_callback=None):
        if progress_callback is not None:
            progress_callback(
                stage="Connecting to Gmail",
                progress=10,
                detail="Authenticating with Gmail and preparing full mailbox sync.",
            )
        self.metadata_store.clear_all_emails()
        self.metadata_store.delete_sync_value("historyId")
        self.vector_store.clear()

        if progress_callback is not None:
            progress_callback(
                stage="Pulling mailbox messages",
                progress=15,
                detail="Cleared local metadata and vector store. Fetching the full mailbox from Gmail.",
            )

        def on_fetch_progress(*, page_count: int, fetched_count: int):
            if progress_callback is None:
                return
            progress_callback(
                stage="Pulling mailbox messages",
                progress=min(45, 15 + page_count),
                detail=f"Fetched {fetched_count} emails across {page_count} Gmail pages.",
                fetched_count=fetched_count,
            )

        full_sync = GmailFetchSkill().execute_full_sync(progress_callback=on_fetch_progress)
        fetched_emails = full_sync.emails
        saved_emails = []
        total = max(len(fetched_emails), 1)
        for index, email in enumerate(fetched_emails, start=1):
            saved_emails.append(self.metadata_store.upsert_email(email))
            if progress_callback is not None:
                progress_callback(
                    stage="Normalizing email content",
                    progress=45 + int((index / total) * 15),
                    detail=f"Saved and normalized {index} of {len(fetched_emails)} emails locally.",
                    fetched_count=len(fetched_emails),
                    saved_count=index,
                )
        self.metadata_store.set_sync_value("pendingHistoryId", full_sync.history_id)
        return IngestionResult(
            mode="full",
            saved_emails=saved_emails,
            fetched_count=len(fetched_emails),
            deleted_count=0,
            history_id=full_sync.history_id,
        )

    def _resume_full_sync(self, history_id: str, progress_callback=None):
        total_emails = self.metadata_store.count_emails()
        remaining_emails = self.metadata_store.count_unindexed_emails()
        if progress_callback is not None:
            progress_callback(
                stage="Refreshing vector index",
                progress=55,
                detail=(
                    f"Resuming failed full sync. {remaining_emails} of {total_emails} emails still need indexing."
                ),
                fetched_count=total_emails,
                saved_count=total_emails,
                indexed_count=max(total_emails - remaining_emails, 0),
            )

        return IngestionResult(
            mode="resume_full",
            saved_emails=[],
            fetched_count=total_emails,
            deleted_count=0,
            history_id=history_id,
        )

    def _run_incremental_sync(self, history_id: str, progress_callback=None):
        if progress_callback is not None:
            progress_callback(
                stage="Connecting to Gmail",
                progress=10,
                detail="Authenticating with Gmail and checking mailbox history changes.",
            )

        def on_history_progress(
            *,
            processed_history_records: int,
            changed_count: int,
            deleted_count: int,
        ):
            if progress_callback is None:
                return
            progress_callback(
                stage="Pulling mailbox changes",
                progress=min(40, 15 + processed_history_records),
                detail=(
                    f"Scanned {processed_history_records} Gmail history records. "
                    f"Detected {changed_count} changed emails and {deleted_count} deletions."
                ),
                fetched_count=changed_count,
            )

        delta = GmailFetchSkill().execute_incremental_sync(
            history_id=history_id,
            progress_callback=on_history_progress,
        )

        deleted_email_ids = self.metadata_store.delete_emails_by_gmail_message_ids(
            delta.deleted_message_ids,
        )
        self.vector_store.delete_by_email_ids(deleted_email_ids)

        if progress_callback is not None:
            progress_callback(
                stage="Normalizing email content",
                progress=45,
                detail=(
                    f"Applying {len(delta.emails)} changed emails and "
                    f"{len(delta.deleted_message_ids)} deletions locally."
                ),
                fetched_count=len(delta.emails),
                saved_count=0,
            )

        saved_emails = []
        total = max(len(delta.emails), 1)
        for index, email in enumerate(delta.emails, start=1):
            saved_emails.append(self.metadata_store.upsert_email(email))
            if progress_callback is not None:
                progress_callback(
                    stage="Normalizing email content",
                    progress=45 + int((index / total) * 15),
                    detail=f"Saved and normalized {index} of {len(delta.emails)} changed emails locally.",
                    fetched_count=len(delta.emails),
                    saved_count=index,
                )

        return IngestionResult(
            mode="incremental",
            saved_emails=saved_emails,
            fetched_count=len(delta.emails),
            deleted_count=len(delta.deleted_message_ids),
            history_id=delta.history_id,
        )
