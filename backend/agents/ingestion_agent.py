from dataclasses import dataclass

from skills.gmail_fetch import GmailFetchSkill
from tools.metadata_store import MetadataStore


@dataclass
class IngestionAgent:
    metadata_store: MetadataStore

    def run(self, max_results: int, progress_callback=None):
        if progress_callback is not None:
            progress_callback(
                stage="Connecting to Gmail",
                progress=10,
                detail="Authenticating with Gmail and requesting message list.",
            )
        fetched_emails = GmailFetchSkill().execute(max_results=max_results)
        if progress_callback is not None:
            progress_callback(
                stage="Pulling recent messages",
                progress=25,
                detail=f"Fetched {len(fetched_emails)} emails from Gmail.",
                fetched_count=len(fetched_emails),
            )
        saved_emails = []
        total = max(len(fetched_emails), 1)
        for index, email in enumerate(fetched_emails, start=1):
            saved_emails.append(self.metadata_store.upsert_email(email))
            if progress_callback is not None:
                progress_callback(
                    stage="Normalizing email content",
                    progress=25 + int((index / total) * 25),
                    detail=f"Saved and normalized {index} of {len(fetched_emails)} emails locally.",
                    fetched_count=len(fetched_emails),
                    saved_count=index,
                )
        return saved_emails
