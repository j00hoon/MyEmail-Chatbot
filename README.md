# myEmail-chatbot

Local-first Gmail RAG chatbot built for portfolio demos and future deployment.

## What This Project Is Now

This project has been upgraded from a simple Gmail viewer into an MVP architecture for a personal Gmail chatbot:

```text
[Gmail API]
    ↓
[Ingestion Agent]
    ↓
[Metadata Store + Vector Store]
    ↓
[Chat Agent (RAG)]
    ↓
[FastAPI Backend]
    ↓
[React Frontend]
```

## Tech Stack

- Backend: Python + FastAPI
- Frontend: React + Vite
- Metadata DB: SQLite for local MVP, designed so PostgreSQL can replace it later
- Vector Store: local JSON vector index with OpenAI embeddings or local fallback embeddings
- AI Layer: agent / skill / tool split inspired by modern agentic architecture
- Gmail Integration: Gmail API + OAuth
- LLM: OpenAI GPT-5 family via environment variables

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
```

## Agent / Skill / MCP Mapping

- Sub Agents
  - `IngestionAgent`: Gmail fetch + raw email persistence
  - `IndexingAgent`: document building + embedding generation + vector indexing
  - `ChatAgent`: retrieval + answer generation
- Skills
  - Gmail fetch
  - text parsing
  - embedding generation
  - vector search
  - answer generation
- MCP-style tool layer
  - Gmail API connector
  - metadata database connector
  - vector store connector
  - local filesystem persistence

This is implemented as a practical tool layer for local development, while keeping the structure easy to migrate to more formal MCP servers later.

## MVP Features

1. Sync recent Gmail messages from 1 to 50 emails
2. Store subject, body, snippet, attachment names, and raw payload locally
3. Generate embeddings and index emails for retrieval
4. Ask questions in the web UI and get mailbox-grounded answers

## Local Run

### 1. Install backend dependencies

```powershell
python -m venv backend\venv
.\backend\venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 2. Install frontend dependencies

```powershell
cd frontend
npm install
cd ..
```

### 3. Add Gmail OAuth credentials

Put your Google OAuth desktop app client file here:

```text
backend/credentials.json
```

On first Gmail sync, a browser login flow creates:

```text
backend/token.json
```

### 4. Optional: add OpenAI API key

Use `backend/.env.example` as your local environment reference.

Important variables:

```text
OPENAI_API_KEY=your_key_here
OPENAI_CHAT_MODEL=gpt-5-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

If no OpenAI key is set, the app still works in fallback local retrieval mode.

### 5. Start everything

```powershell
.\start-all.ps1
```

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

## API Endpoints

- `GET /api/health`
- `POST /api/sync`
- `GET /api/emails?limit=20`
- `POST /api/chat`

## Portfolio Story

This project is now shaped to demo:

- OAuth-based Gmail ingestion
- agentic backend design
- RAG over personal data
- local-first AI app architecture
- React + FastAPI full-stack delivery
- a clean path from local MVP to cloud deployment

## Deployment Path Later

For production or interview demos on a live server, the natural upgrades are:

- SQLite to PostgreSQL
- local JSON vector store to Chroma or pgvector
- local FastAPI server to Docker or cloud deployment
- local `.env` secrets to hosted secret management
- single-user OAuth flow to managed auth and multi-user isolation
