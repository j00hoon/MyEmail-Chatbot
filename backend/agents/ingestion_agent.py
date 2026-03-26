from dataclasses import dataclass

from skills.gmail_fetch import GmailFetchSkill
from tools.metadata_store import MetadataStore


@dataclass
class IngestionAgent:
    metadata_store: MetadataStore

    def run(self, max_results: int):
        fetched_emails = GmailFetchSkill().execute(max_results=max_results)
        saved_emails = []
        for email in fetched_emails:
            saved_emails.append(self.metadata_store.upsert_email(email))
        return saved_emails
