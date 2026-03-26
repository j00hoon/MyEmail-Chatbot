from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    count: int = Field(default=10, ge=1, le=50)


class SyncResponse(BaseModel):
    fetched_count: int
    indexed_count: int
    saved_count: int
    message: str


class EmailRecordResponse(BaseModel):
    id: int
    gmail_message_id: str
    subject: str
    sender: str | None = None
    recipients: str | None = None
    sent_at: str | None = None
    snippet: str | None = None
    body_text: str | None = None
    attachment_names: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)


class SourceReference(BaseModel):
    gmail_message_id: str
    subject: str
    sender: str | None = None
    sent_at: str | None = None
    snippet: str | None = None
    attachment_names: list[str] = Field(default_factory=list)
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
