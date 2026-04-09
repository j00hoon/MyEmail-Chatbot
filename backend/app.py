from contextlib import asynccontextmanager
from datetime import datetime, timezone
import re

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from agents.chat_agent import ChatAgent
from agents.indexing_agent import IndexingAgent
from agents.ingestion_agent import IngestionAgent
from config import settings
from db import init_db
from schemas import (
    ChatRequest,
    ChatResponse,
    ConnectAccountRequest,
    EmailRecordResponse,
    GmailAccountResponse,
    SyncRequest,
    SyncResponse,
    SyncStatusResponse,
)
from tools.cache_store import CacheStore
from tools.gmail_client import GmailClient
from tools.metadata_store import MetadataStore
from tools.sync_progress_store import SyncProgressStore
from tools.vector_store import VectorStore


metadata_store = MetadataStore(settings.database_url)
vector_store = VectorStore(
    database_url=settings.database_url,
    legacy_path=settings.vector_store_path,
)
sync_progress_store = SyncProgressStore()
cache_store = CacheStore(
    redis_url=settings.redis_url,
    ttl_seconds=settings.redis_cache_ttl_seconds,
    key_prefix=settings.redis_key_prefix,
    enabled=settings.redis_enabled,
)
ingestion_agent = IngestionAgent(metadata_store=metadata_store, vector_store=vector_store)
indexing_agent = IndexingAgent(metadata_store=metadata_store, vector_store=vector_store)
chat_agent = ChatAgent(
    metadata_store=metadata_store,
    vector_store=vector_store,
    cache_store=cache_store,
    mailbox_id=settings.default_mailbox_id,
)


LAST_SUCCESSFUL_SYNC_KEY = "lastSuccessfulSyncAt"


def _ensure_account_profile(account_id: str):
    account = metadata_store.get_account(account_id)
    if account is not None and account.email_address:
        return account

    try:
        client = GmailClient(account_id=account_id)
        if not client.token_path.exists():
            return account

        profile = client.get_profile()
        return metadata_store.upsert_account(
            account_id=account_id,
            token_path=str(client.token_path),
            email_address=profile.get("emailAddress"),
            display_name=profile.get("emailAddress"),
            make_active=bool(account.is_active) if account is not None else False,
        )
    except Exception:
        return account


def _migrate_legacy_default_account(target_account_id: str):
    if not target_account_id or target_account_id == settings.default_mailbox_id:
        return False

    legacy_account = metadata_store.get_account(settings.default_mailbox_id)
    if legacy_account is None:
        return False
    if legacy_account.email_address:
        return False

    metadata_migrated = metadata_store.migrate_account_id(
        from_account_id=settings.default_mailbox_id,
        to_account_id=target_account_id,
    )
    vector_store.migrate_account_id(
        from_account_id=settings.default_mailbox_id,
        to_account_id=target_account_id,
    )
    return metadata_migrated


def _resolve_account_id(requested_account_id: str | None = None):
    if requested_account_id:
        return requested_account_id
    active_account = metadata_store.get_active_account()
    if active_account is not None:
        return active_account.account_id
    return settings.default_mailbox_id


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db(settings.database_url)
    vector_store.delete_trashed()
    _ensure_account_profile(settings.default_mailbox_id)
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
        "active_account_id": _resolve_account_id(),
    }


@app.post("/api/sync", response_model=SyncResponse)
def sync_gmail(payload: SyncRequest):
    account_id = _resolve_account_id(payload.account_id)
    run_id = sync_progress_store.start(payload.count)
    if run_id is None:
        raise HTTPException(
            status_code=409,
            detail="A Gmail sync is already running. Wait for it to finish before starting another one.",
        )

    def progress_callback(**kwargs):
        sync_progress_store.update(run_id, **kwargs)

    try:
        ingestion_result = ingestion_agent.run(
            max_results=payload.count,
            progress_callback=progress_callback,
            account_id=account_id,
        )
        indexing_result = indexing_agent.run(
            email_ids=(
                [email.id for email in ingestion_result.saved_emails]
                if ingestion_result.mode != "resume_full"
                else None
            ),
            progress_callback=progress_callback,
            only_unindexed=ingestion_result.mode == "resume_full",
            account_id=account_id,
        )
        metadata_store.set_sync_value("historyId", ingestion_result.history_id, account_id=account_id)
        metadata_store.delete_sync_value("pendingHistoryId", account_id=account_id)
        metadata_store.set_sync_value(
            LAST_SUCCESSFUL_SYNC_KEY,
            datetime.now(timezone.utc).isoformat(),
            account_id=account_id,
        )
        cache_store.bump_mailbox_version(account_id)
        sync_progress_store.update(
            run_id,
            stage="Finalizing local cache",
            progress=95,
            detail=(
                "Refreshing cached responses after sync and index rebuild."
                if ingestion_result.mode in {"full", "resume_full"}
                else "Refreshing cached responses after incremental sync."
            ),
            fetched_count=ingestion_result.fetched_count,
            saved_count=(
                indexing_result.saved_count
                if ingestion_result.mode != "resume_full"
                else ingestion_result.fetched_count
            ),
            indexed_count=indexing_result.indexed_count,
        )
        sync_progress_store.finish(
            run_id,
            fetched_count=ingestion_result.fetched_count,
            saved_count=(
                indexing_result.saved_count
                if ingestion_result.mode != "resume_full"
                else ingestion_result.fetched_count
            ),
            indexed_count=indexing_result.indexed_count,
        )
    except FileNotFoundError as exc:
        sync_progress_store.fail(run_id, str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        sync_progress_store.fail(run_id, str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SyncResponse(
        fetched_count=ingestion_result.fetched_count,
        indexed_count=indexing_result.indexed_count,
        saved_count=(
            indexing_result.saved_count
            if ingestion_result.mode != "resume_full"
            else ingestion_result.fetched_count
        ),
        message=(
            "Full Gmail sync and indexing completed."
            if ingestion_result.mode in {"full", "resume_full"}
            else "Incremental Gmail sync and indexing completed."
        ),
    )


@app.get("/api/sync-status", response_model=SyncStatusResponse)
def get_sync_status():
    snapshot = sync_progress_store.snapshot()
    snapshot.last_completed_at = metadata_store.get_sync_value(LAST_SUCCESSFUL_SYNC_KEY, account_id=_resolve_account_id())
    return snapshot


@app.get("/api/emails", response_model=list[EmailRecordResponse])
def list_emails(limit: int = Query(default=20, ge=1, le=50), account_id: str | None = None):
    return metadata_store.list_emails(limit=limit, account_id=_resolve_account_id(account_id))


@app.get("/api/accounts", response_model=list[GmailAccountResponse])
def list_accounts():
    _ensure_account_profile(settings.default_mailbox_id)
    accounts = metadata_store.list_accounts()
    real_accounts = [account for account in accounts if account.account_id != settings.default_mailbox_id]
    if real_accounts:
        preferred_account = next((account for account in real_accounts if account.is_active), real_accounts[0])
        _migrate_legacy_default_account(preferred_account.account_id)
        accounts = metadata_store.list_accounts()
    return accounts


@app.post("/api/accounts/connect", response_model=GmailAccountResponse)
def connect_account(payload: ConnectAccountRequest):
    requested_account_id = (payload.account_id or "").strip() or f"oauth_pending_{int(datetime.now(timezone.utc).timestamp())}"
    client = GmailClient(account_id=requested_account_id)
    profile = client.get_profile()
    email_address = (profile.get("emailAddress") or "").strip().lower()
    resolved_account_id = payload.account_id or email_address or requested_account_id
    resolved_account_id = re.sub(r"\s+", "", resolved_account_id)
    token_path = client.migrate_token_to_account(resolved_account_id)
    account = metadata_store.upsert_account(
        account_id=resolved_account_id,
        token_path=str(token_path),
        email_address=profile.get("emailAddress"),
        display_name=profile.get("emailAddress"),
        make_active=payload.make_active,
    )
    _migrate_legacy_default_account(resolved_account_id)
    return metadata_store.get_account(resolved_account_id) or account


@app.post("/api/accounts/select", response_model=GmailAccountResponse)
def select_account(payload: ConnectAccountRequest):
    account = metadata_store.set_active_account(payload.account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    return account


@app.post("/api/chat", response_model=ChatResponse)
def chat_with_mailbox(payload: ChatRequest):
    try:
        result = chat_agent.run(
            question=payload.question,
            top_k=payload.top_k,
            category_filters=payload.category_filters,
            search_filters=payload.search_filters.model_dump(),
            account_id=_resolve_account_id(payload.account_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
