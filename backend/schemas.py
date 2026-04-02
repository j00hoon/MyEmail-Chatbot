from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)


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


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)
    category_filters: list[str] = Field(default_factory=list)
    search_filters: SearchFilters = Field(default_factory=SearchFilters)


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
