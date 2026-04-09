from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)
    account_id: str | None = None


class SyncResponse(BaseModel):
    fetched_count: int
    indexed_count: int
    saved_count: int
    message: str


class SyncStatusResponse(BaseModel):
    state: str
    stage: str
    progress: int = Field(ge=0, le=100)
    detail: str
    fetched_count: int = 0
    saved_count: int = 0
    indexed_count: int = 0
    last_completed_at: str | None = None


class EmailRecordResponse(BaseModel):
    id: int
    gmail_message_id: str
    subject: str
    sender: str | None = None
    recipients: str | None = None
    sent_at: str | None = None
    gmail_category: str | None = None
    snippet: str | None = None
    body_text: str | None = None
    attachment_names: list[str] = Field(default_factory=list)


class SearchFilters(BaseModel):
    sender: str = ""
    subject: str = ""
    date_from: str | None = None
    date_to: str | None = None


class EmailSearchFilters(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    semantic_expansions: list[str] = Field(default_factory=list)
    sender: str | None = None
    subject: str | None = None
    is_important: bool = False

    def ordered_terms(self):
        terms: list[str] = []
        seen: set[str] = set()

        for keyword in self.keywords:
            normalized = keyword.strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                terms.append(normalized)

        for synonym in self.semantic_expansions:
            normalized_synonym = synonym.strip()
            if normalized_synonym and normalized_synonym not in seen:
                seen.add(normalized_synonym)
                terms.append(normalized_synonym)

        return terms

    def grouped_terms(self):
        terms = self.ordered_terms()
        return [terms] if terms else []


class DateRange(BaseModel):
    start_date: date | None = None
    end_date: date | None = None


class EmailSearchIntent(BaseModel):
    intent: Literal[
        "SEARCH_EMAILS",
        "SUMMARIZE_THREADS",
        "FIND_CONTACT",
        "UNSUBSCRIBE_ASSIST",
    ] = "SEARCH_EMAILS"
    search_filters: EmailSearchFilters = Field(default_factory=EmailSearchFilters)
    date_range: DateRange = Field(default_factory=DateRange)
    result_scope: Literal["all", "top_n", "best_match"] = "top_n"
    aggregation_mode: Literal["emails", "threads", "senders"] = "emails"
    retrieval_mode_hint: Literal["exact", "hybrid", "semantic"] = "hybrid"
    requested_count: int | None = Field(default=None, ge=1, le=50)
    output_mode: Literal[
        "concise_summary",
        "bullet_points",
        "table",
        "raw_list",
    ] = "concise_summary"


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)
    category_filters: list[str] = Field(default_factory=list)
    search_filters: SearchFilters = Field(default_factory=SearchFilters)
    account_id: str | None = None


class GmailAccountResponse(BaseModel):
    account_id: str
    email_address: str | None = None
    display_name: str | None = None
    token_path: str
    is_active: bool


class ConnectAccountRequest(BaseModel):
    account_id: str | None = Field(default=None, min_length=1)
    make_active: bool = True


class SourceReference(BaseModel):
    gmail_message_id: str
    subject: str
    sender: str | None = None
    sent_at: str | None = None
    gmail_category: str | None = None
    snippet: str | None = None
    attachment_names: list[str] = Field(default_factory=list)
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
