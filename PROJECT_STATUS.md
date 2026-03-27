# PROJECT STATUS

## Overview | 개요

This file is a bilingual checkpoint so the project can be resumed later without losing context.

이 파일은 나중에 다시 작업할 때 맥락을 잃지 않고 이어가기 위한 한글/영문 체크포인트 문서입니다.

## Current Goal | 현재 목표

Build a personal Gmail AI search and chat application that can eventually outperform or replace the default Gmail search experience.

기본 Gmail 검색보다 더 강력한 개인용 Gmail AI 검색/챗 애플리케이션을 만드는 것이 목표입니다.

Long term direction:

장기 방향:

- Local-first Gmail chatbot for portfolio demos
- Gmail-connected search assistant over the user's full mailbox
- Later extension into browser extension / hosted product

- 포트폴리오용 로컬 우선 Gmail 챗봇
- 사용자 전체 Gmail 메일박스를 대상으로 하는 AI 검색 도구
- 이후 브라우저 확장 / 호스팅 서비스로 확장

## What Has Been Built | 현재까지 구현된 것

### Backend

- Migrated backend from Flask to FastAPI
- Added agent-oriented structure:
  - `IngestionAgent`
  - `IndexingAgent`
  - `ChatAgent`
- Added skill layer:
  - Gmail fetch
  - text parsing
  - text chunking
  - embedding generation
  - vector search
  - answer generation
- Added tool layer:
  - Gmail client
  - metadata store
  - vector store
  - Redis cache store
  - sync progress store
- Gmail sync endpoint implemented
- Chat endpoint implemented
- Sync status endpoint implemented
- Redis chat caching implemented
- Cache invalidation after sync/index refresh implemented

- 백엔드를 Flask에서 FastAPI로 변경함
- Agent 구조 추가:
  - `IngestionAgent`
  - `IndexingAgent`
  - `ChatAgent`
- Skill 레이어 추가:
  - Gmail fetch
  - text parsing
  - text chunking
  - embedding generation
  - vector search
  - answer generation
- Tool 레이어 추가:
  - Gmail client
  - metadata store
  - vector store
  - Redis cache store
  - sync progress store
- Gmail sync API 구현 완료
- Chat API 구현 완료
- Sync status API 구현 완료
- Redis chat cache 구현 완료
- sync/index refresh 후 cache invalidation 구현 완료

### Storage

- Metadata is stored in local SQLite
- Vector data is stored in local JSON vector store
- Redis is used as an optional chat response cache layer
- No external DB server is currently required

- 메타데이터는 로컬 SQLite에 저장됨
- 벡터 데이터는 로컬 JSON vector store에 저장됨
- Redis는 선택적으로 사용할 수 있는 chat response cache 계층으로 추가됨
- 현재는 외부 DB 서버 설치가 필요 없음

### Frontend

- React UI upgraded from simple email list viewer to a styled Gmail AI workspace
- Purple visual theme applied
- Hero section rewritten
- Sync / Chat / Stored Emails sections redesigned
- User and assistant message colors are visually more distinct
- Sync progress panel now shows live backend-driven stage/progress/count updates

- React UI를 단순 이메일 리스트 뷰어에서 Gmail AI 워크스페이스 형태로 업그레이드함
- 보라색 중심 테마 적용
- 상단 Hero 문구 수정
- Sync / Chat / Stored Emails 섹션 리디자인 완료
- user / assistant 메시지 색상 구분 강화
- Sync 진행 중 실제 backend 상태 기반 단계/진행률/건수 표시 추가

### Search Quality Improvements

- Added text chunking instead of indexing one email as a single block
- Added hybrid retrieval:
  - vector similarity
  - keyword matching
- Added HTML cleanup during parsing
- Improved answer prompting so company/topic lookups explicitly list matching emails

- 이메일 1개를 통째로 인덱싱하던 방식 대신 chunking 추가
- 하이브리드 검색 추가:
  - 벡터 유사도
  - 키워드 매칭
- 파싱 단계에서 HTML 정리 강화
- 회사명/키워드 질의 시 관련 메일을 명시적으로 나열하도록 답변 프롬프트 개선

## Current Architecture | 현재 아키텍처

```text
[Gmail API]
    ↓
[Ingestion Agent]
    ↓
[SQLite Metadata Store]
[Local JSON Vector Store]
 [Redis Chat Cache]
 [Sync Progress Store]
    ↓
[Hybrid Retrieval + Chat Agent]
    ↓
[FastAPI Backend]
    ↓
[React Frontend]
```

## Important Files | 중요한 파일

- [README.md](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/README.md)
- [backend/app.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/app.py)
- [backend/config.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/config.py)
- [backend/agents/indexing_agent.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/agents/indexing_agent.py)
- [backend/agents/chat_agent.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/agents/chat_agent.py)
- [backend/tools/metadata_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/metadata_store.py)
- [backend/tools/vector_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/vector_store.py)
- [backend/tools/cache_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/cache_store.py)
- [backend/tools/sync_progress_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/sync_progress_store.py)
- [frontend/src/App.jsx](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/frontend/src/App.jsx)
- [frontend/src/App.css](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/frontend/src/App.css)

## Current Runtime State | 현재 실행 상태

- Backend runs locally on `http://127.0.0.1:8000`
- Frontend runs locally on `http://127.0.0.1:5173`
- Gmail OAuth credentials are present
- OpenAI API key is configured in local `.env`
- Redis-backed chat cache is configured in local `.env`

- 백엔드는 로컬 `http://127.0.0.1:8000` 에서 실행됨
- 프론트엔드는 로컬 `http://127.0.0.1:5173` 에서 실행됨
- Gmail OAuth credentials 파일이 존재함
- OpenAI API 키가 로컬 `.env`에 설정되어 있음
- Redis 기반 chat cache 설정이 로컬 `.env`에 추가됨

## What Is Not Done Yet | 아직 안 된 것

- Full mailbox sync is not implemented yet
- Incremental sync via Gmail history API is not implemented yet
- Browser extension is not implemented yet
- PostgreSQL / pgvector migration is not implemented yet
- Gmail-search-replacement level ranking is not fully implemented yet

- Gmail 전체 메일박스 full sync는 아직 미구현
- Gmail history API 기반 incremental sync는 아직 미구현
- 브라우저 extension은 아직 미구현
- PostgreSQL / pgvector 전환은 아직 미구현
- Gmail 검색 대체 수준의 정교한 ranking은 아직 미구현

## Known Issues / Observations | 현재 한계 / 관찰사항

- Search accuracy improved, but it can still pull partially related emails
- Some messages may still contain noisy newsletter/email-markup remnants
- Current vector store is okay for MVP but not ideal for large mailbox scale
- SQLite + JSON store is fine for local demo, but not ideal for full production scale
- Redis cache is versioned by mailbox and invalidated after sync/index refresh
- Sync progress UI currently uses polling against `/api/sync-status`

- 검색 정확도는 좋아졌지만, 일부 부분적으로 관련 있는 메일까지 함께 끌어올 수 있음
- 일부 메일은 뉴스레터/이메일 마크업 찌꺼기가 아직 남을 수 있음
- 현재 vector store는 MVP용으로는 괜찮지만 대용량 메일박스에는 적합하지 않음
- SQLite + JSON 구조는 로컬 데모용으로는 괜찮지만 본격 운영용으로는 한계가 있음
- Redis cache는 mailbox version 기준으로 관리되며 sync/index refresh 후 무효화됨
- Sync progress UI는 현재 `/api/sync-status` polling 방식으로 동작함

## Recommended Next Steps | 추천 다음 단계

### Priority 1

- Implement full Gmail sync across the entire mailbox
- Store and reuse Gmail `historyId`
- Add incremental sync using Gmail History API

- Gmail 전체 메일박스 full sync 구현
- Gmail `historyId` 저장 및 재사용
- Gmail History API 기반 incremental sync 추가

### Priority 2

- Upgrade storage from local JSON vector store to PostgreSQL + pgvector or Qdrant
- Add stronger ranking:
  - sender boosting
  - recency boosting
  - exact subject match
  - attachment and thread-aware ranking

- 로컬 JSON vector store를 PostgreSQL + pgvector 또는 Qdrant로 업그레이드
- 더 강한 ranking 추가:
  - sender boosting
  - recency boosting
  - exact subject match
  - attachment / thread-aware ranking

### Priority 3

- Build a browser extension UI for Gmail sidebar integration
- Connect extension UI to local backend first
- Later consider hosted multi-user deployment

- Gmail 사이드바 연동 브라우저 extension UI 구현
- 우선 local backend와 연결
- 이후 hosted multi-user 배포 확장 고려

## Suggested Product Direction | 추천 제품 방향

### Short Term

Build a strong local-first Gmail AI search assistant for portfolio demos.

포트폴리오 데모용으로 완성도 높은 local-first Gmail AI 검색 도구를 먼저 만든다.

### Mid Term

Turn it into a Gmail-connected browser extension with sidebar chat/search.

Gmail과 연결되는 브라우저 extension + 사이드바 챗/검색 도구로 확장한다.

### Long Term

Turn it into a hosted product with per-user OAuth, server-side indexing, and multi-user isolation.

사용자별 OAuth, 서버 인덱싱, 멀티유저 분리를 지원하는 hosted 제품으로 확장한다.

## Notes For Next Session | 다음 세션용 메모

When resuming, a good prompt would be:

다음에 이어서 작업할 때는 아래처럼 말하면 좋습니다:

```text
Read PROJECT_STATUS.md and continue from the current architecture.
Next, implement full Gmail sync + incremental sync using historyId.
```

또는:

```text
PROJECT_STATUS.md 읽고 이어서 해줘.
다음 단계로 Gmail full sync + incremental sync 구현하자.
```

## Security Note | 보안 메모

The OpenAI API key was pasted into chat during development. It is recommended to rotate/regenerate that key later for safety.

개발 중 OpenAI API 키가 채팅에 노출되었으므로, 안전을 위해 나중에 해당 키를 회전/재발급하는 것을 권장합니다.
