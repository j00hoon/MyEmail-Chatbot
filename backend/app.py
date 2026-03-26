from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agents.chat_agent import ChatAgent
from agents.indexing_agent import IndexingAgent
from agents.ingestion_agent import IngestionAgent
from config import settings
from db import init_db
from schemas import ChatRequest, ChatResponse, EmailRecordResponse, SyncRequest, SyncResponse
from tools.metadata_store import MetadataStore
from tools.vector_store import VectorStore


metadata_store = MetadataStore(settings.database_url)
vector_store = VectorStore(settings.vector_store_path)
ingestion_agent = IngestionAgent(metadata_store=metadata_store)
indexing_agent = IndexingAgent(metadata_store=metadata_store, vector_store=vector_store)
chat_agent = ChatAgent(metadata_store=metadata_store, vector_store=vector_store)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(settings.database_url)
    yield


app = FastAPI(
    title="myEmail Chatbot API",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "app_env": settings.app_env,
        "openai_configured": bool(settings.openai_api_key),
        "gmail_credentials_present": settings.credentials_path.exists(),
        "database_url": settings.database_url,
        "vector_store_path": str(settings.vector_store_path),
    }


@app.post("/api/sync", response_model=SyncResponse)
def sync_gmail(payload: SyncRequest):
    try:
        emails = ingestion_agent.run(max_results=payload.count)
        indexing_result = indexing_agent.run(email_ids=[email.id for email in emails])
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SyncResponse(
        fetched_count=len(emails),
        indexed_count=indexing_result.indexed_count,
        saved_count=indexing_result.saved_count,
        message="Gmail sync and indexing completed.",
    )


@app.get("/api/emails", response_model=list[EmailRecordResponse])
def list_emails(limit: int = Query(default=20, ge=1, le=50)):
    return metadata_store.list_emails(limit=limit)


@app.post("/api/chat", response_model=ChatResponse)
def chat_with_mailbox(payload: ChatRequest):
    try:
        result = chat_agent.run(question=payload.question, top_k=payload.top_k)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
