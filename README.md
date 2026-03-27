# myEmail-chatbot

Local-first Gmail RAG chatbot for personal email search, sync, and AI chat.

This project is evolving toward a smarter Gmail search experience that can eventually outperform the default Gmail search UI for personal workflows.

## Snapshot

- Gmail sync with OAuth
- Local metadata storage with SQLite
- Local vector storage for retrieval
- FastAPI backend
- React frontend
- Agent / skill / tool architecture
- Purple AI workspace UI

## Architecture

```text
[Gmail API]
    ↓
[Ingestion Agent]
    ↓
[SQLite Metadata Store]
[Local JSON Vector Store]
    ↓
[Hybrid Retrieval + Chat Agent]
    ↓
[FastAPI Backend]
    ↓
[React Frontend]
```

## Current Tech Stack

- Backend: Python + FastAPI
- Frontend: React + Vite
- Metadata DB: SQLite
- Vector Store: local JSON vector store
- AI Integration: OpenAI API
- Gmail Integration: Gmail API + OAuth
- Retrieval: vector similarity + keyword matching
- Cache: Redis chat response cache with sync-based invalidation

## What It Can Do Right Now

- Sync recent Gmail messages from `1` to `50`
- Store subject, sender, body, snippet, and attachment names locally
- Build embeddings and retrieval index
- Ask natural-language questions over synced emails
- Return source-backed answers in a web UI

## Important Note About Storage

You do **not** need to install PostgreSQL or any external database to run this version.

This project currently stores data locally in:

- `backend/data/metadata.db` for SQLite metadata
- `backend/data/vector_store.json` for vector search data

This makes the app easy to run locally for demos and portfolio use.

## Quick Start

### 1. Clone the repository

```powershell
git clone https://github.com/j00hoon/MyEmail-Chatbot.git
cd MyEmail-Chatbot
```

### 2. Create the Python virtual environment

```powershell
python -m venv backend\venv
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 3. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

### 4. Add Gmail OAuth credentials

Create a Google OAuth desktop app client in Google Cloud and place the downloaded file here:

```text
backend/credentials.json
```

When you sync Gmail for the first time, the app will open a browser login flow and generate:

```text
backend/token.json
```

### 5. Configure environment variables

Use this file as a reference:

```text
backend/.env.example
```

Create your local runtime file here:

```text
backend/.env
```

Minimum recommended values:

```text
APP_ENV=local
OPENAI_API_KEY=your_key_here
OPENAI_CHAT_MODEL=gpt-5-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
DATABASE_URL=sqlite:///./data/metadata.db
VECTOR_STORE_PATH=./data/vector_store.json
GMAIL_CREDENTIALS_PATH=./credentials.json
GMAIL_TOKEN_PATH=./token.json
REDIS_ENABLED=false
REDIS_URL=redis://localhost:6379/0
REDIS_CACHE_TTL_SECONDS=300
REDIS_KEY_PREFIX=myemail
DEFAULT_MAILBOX_ID=local_default
CORS_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
```

If `OPENAI_API_KEY` is missing, the app still works in fallback local retrieval mode, but answer quality may be lower.

Redis caching is optional for local development. When enabled, chat responses are cached by mailbox version so a completed Gmail sync automatically invalidates older cached answers.

### 6. Start the app

```powershell
.\start-all.ps1
```

Local URLs:

- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

### 7. Stop the app

```powershell
.\stop-all.ps1
```

## First Run Flow

1. Start the app with `.\start-all.ps1`
2. Open the frontend in the browser
3. Click `Sync latest emails`
4. Complete the Gmail OAuth login if prompted
5. Wait for sync + indexing to finish
6. Start asking questions in the chat UI

## Main API Endpoints

- `GET /api/health`
- `POST /api/sync`
- `GET /api/emails?limit=20`
- `POST /api/chat`

## Project Structure

```text
backend/
  agents/
  skills/
  tools/
  data/
  app.py
  config.py
  db.py
  models.py
  schemas.py
frontend/
  src/
PROJECT_STATUS.md
README.md
```

## Agent / Skill / Tool Mapping

### Agents

- `IngestionAgent`: fetches Gmail messages and saves raw metadata
- `IndexingAgent`: parses messages, chunks content, creates embeddings, stores retrieval data
- `ChatAgent`: retrieves relevant emails and generates final answers

### Skills

- Gmail fetch
- text parsing
- text chunking
- embedding generation
- vector search
- answer generation

### Tools

- Gmail API client
- metadata store
- vector store
- local filesystem persistence

## Current Limitations

- Full mailbox sync is not implemented yet
- Incremental sync via Gmail History API is not implemented yet
- Browser extension is not implemented yet
- Local JSON vector store is fine for MVP, but not ideal for large-scale indexing
- Redis is optional but recommended if you want faster repeated chat responses

## Recommended Next Upgrades

- Add full mailbox sync
- Add Gmail incremental sync with `historyId`
- Upgrade storage to PostgreSQL + pgvector or Qdrant
- Build a Gmail browser extension sidebar

## Portfolio Positioning

This project already demonstrates:

- OAuth-based Gmail ingestion
- local-first AI architecture
- RAG over personal data
- React + FastAPI full-stack implementation
- agent / skill / tool based backend structure
- retrieval quality improvements beyond naive semantic search

## Session Continuity

If you want to continue the project later without losing context, read:

- [PROJECT_STATUS.md](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/PROJECT_STATUS.md)

Suggested resume prompt:

```text
Read PROJECT_STATUS.md and continue from the current architecture.
```
