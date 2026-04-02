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
- Full Gmail mailbox sync implemented with `messages.list` pagination
- Incremental sync implemented using stored Gmail `historyId`
- Automatic fallback to full sync when Gmail history expires
- `sync_meta` table added in SQLite for sync state persistence
- Gmail OAuth refresh-token revoke/expiry recovery added
- Last successful sync timestamp is now persisted and exposed through `/api/sync-status`
- Chat retrieval refined for sender-focused and latest-email questions
- Redis cache bypass added for latest/sender-specific questions to avoid stale wrong answers
- Chat cache key version bumped after retrieval logic changes
- Keyword normalization improved for variants like `vaccine` / `vaccination`
- Answer format updated to structured fields:
  - `Answer`
  - `From`
  - `Date`
  - `Subject`
  - `Summary`
  - `Attachment`
- Vector search path optimized to reduce repeated per-record work
- High-confidence keyword matches can skip vector search for faster responses
- Added question-intent classification for:
  - `latest_from`
  - `sender_lookup`
  - `date_lookup`
  - `top_recent_important`
  - `general`
- Deterministic retrieval path added for sender/date/latest questions
- Result-aware chat cache signatures added so cached answers depend on selected source emails
- Optional LangChain runtime retriever path added for general questions
- General questions can now use:
  - MultiQueryRetriever
  - EnsembleRetriever
  - optional Cohere rerank compression when `COHERE_API_KEY` is configured
- Runtime retriever reuses stored local embeddings instead of rebuilding vectors from scratch
- Retrieval logic is now moving toward a 4-step separation:
  - QueryAnalyzer
  - RetrievalPlanner
  - CandidateSelector
  - AnswerFormatter
- `QueryAnalyzer`, `RetrievalPlanner`, and `CandidateSelector` are now added as concrete runtime modules for query routing
- Recent multi-email requests such as "latest 10 emails" now use deterministic recent-email selection instead of generic retrieval
- Multi-email answer generation now uses a larger context budget so more selected emails can actually reach the LLM
- Chat cache key version bumped again after retrieval-contract changes
- LangChain retrieval is wired into the live chat path for general questions when enabled
- General-question runtime path now uses precomputed embeddings with FAISS instead of re-embedding each chunk at runtime
- LangChain packages were installed into the backend virtual environment and wired through config flags
- Gmail category metadata is now persisted per email via `gmail_category`
- Existing synced emails can backfill category values from stored Gmail `labelIds`
- Cross-category hinting added when the selected tab has no match but other tabs do
- Sender parsing improved for phrases like `from <name> regarding ...` and `from <name> within a week`
- Sender lookup now supports window-aware multi-email retrieval for prompts like `emails from X within a week`
- SQLite FTS5 search replaced the old Python full-scan keyword search path
- Vector storage migrated from local JSON file persistence to SQLite table storage with legacy JSON import
- Structured search filters are now first-class chat inputs:
  - sender
  - subject
  - date range
  - tab/category
- Structured filters now bypass unnecessary vector search and can directly select matching source emails

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
- Gmail 전체 메일박스 full sync 구현 완료
- 저장된 Gmail `historyId` 기반 incremental sync 구현 완료
- Gmail history 만료 시 full sync fallback 구현 완료
- SQLite `sync_meta` 테이블로 sync 상태 저장 구현 완료
- Gmail OAuth refresh token 만료/취소 시 재인증 복구 로직 추가
- 마지막 성공 sync 시각을 저장하고 `/api/sync-status`로 내려주도록 변경
- sender 중심 질문과 최신 메일 질문에 대한 chat retrieval 보정 추가
- 오래된 오답 재사용 방지를 위해 latest/sender 질문은 Redis cache 우회 처리 추가
- retrieval 로직 변경 이후 chat cache key version 갱신
- `vaccine` / `vaccination` 같은 형태 차이를 줄이도록 키워드 정규화 강화
- 답변 포맷을 구조화된 필드 형태로 변경:
  - `Answer`
  - `From`
  - `Date`
  - `Subject`
  - `Summary`
  - `Attachment`
- vector search에서 반복 계산을 줄이는 최적화 추가
- 키워드 매칭 신뢰도가 높은 경우 vector search를 생략해 응답 속도 개선
- 다음 질문 유형에 대한 question intent 분류 추가:
  - `latest_from`
  - `sender_lookup`
  - `date_lookup`
  - `top_recent_important`
  - `general`
- sender/date/latest 질문을 위한 deterministic retrieval 경로 추가
- 선택된 source email 결과를 반영하는 result-aware chat cache signature 추가
- 일반 질문용 optional LangChain runtime retriever 경로 추가
- 일반 질문은 다음 구성 사용 가능:
  - MultiQueryRetriever
  - EnsembleRetriever
  - `COHERE_API_KEY` 설정 시 optional Cohere rerank compression
- runtime retriever가 기존 로컬 embedding을 재사용하도록 구성하여 재인덱싱 비용 방지
- retrieval 로직을 다음 4단계로 분리하는 방향으로 리팩터링 진행:
  - QueryAnalyzer
  - RetrievalPlanner
  - CandidateSelector
  - AnswerFormatter
- `QueryAnalyzer`, `RetrievalPlanner`, `CandidateSelector`를 실제 runtime 모듈로 추가하여 질문 라우팅에 사용하기 시작함
- "latest 10 emails" 같은 최근 다중 메일 요청은 generic retrieval 대신 deterministic recent-email selection 경로를 타도록 변경
- multi-email 답변 생성 시 더 많은 선택 메일이 실제 LLM 컨텍스트에 들어가도록 context budget 확대
- retrieval contract 변경에 맞춰 chat cache key version을 다시 갱신
- 일반 질문은 옵션 활성화 시 LangChain retrieval이 실제 chat 경로에 연결됨
- 일반 질문 runtime 경로는 chunk를 다시 임베딩하지 않고 precomputed embedding + FAISS를 사용
- LangChain 관련 패키지를 backend 가상환경에 설치하고 config 플래그로 연결함
- 각 이메일에 Gmail category 메타데이터를 `gmail_category`로 저장하도록 변경
- 기존 sync 데이터도 저장된 Gmail `labelIds`를 읽어 category를 백필할 수 있도록 구성
- 선택한 탭에 결과가 없지만 다른 탭에 있으면 cross-category hint를 주도록 개선
- `from <name> regarding ...`, `from <name> within a week` 같은 문구에서 sender 파싱 정확도 개선
- `emails from X within a week` 스타일 질문에 대해 기간 조건을 반영한 multi-email sender lookup 지원
- Python 전체 스캔 기반 keyword search를 SQLite FTS5 검색으로 교체
- 로컬 JSON 파일 vector store를 SQLite 테이블 기반 저장으로 마이그레이션
- 구조화된 검색 필터를 chat 입력의 1급 요소로 추가:
  - sender
  - subject
  - date range
  - tab/category
- 구조 필터가 있는 경우 불필요한 vector search를 건너뛰고 직접 source email을 선택하도록 개선

### Storage

- Metadata is stored in local SQLite
- Vector data is stored in SQLite table storage
- Redis is used as an optional chat response cache layer
- No external DB server is currently required
- SQLite FTS5 is now used for local full-text email retrieval

- 메타데이터는 로컬 SQLite에 저장됨
- 벡터 데이터는 SQLite 테이블에 저장됨
- Redis는 선택적으로 사용할 수 있는 chat response cache 계층으로 추가됨
- 현재는 외부 DB 서버 설치가 필요 없음
- 로컬 full-text email retrieval에는 SQLite FTS5를 사용함

### Frontend

- React UI upgraded from simple email list viewer to a styled Gmail AI workspace
- Purple visual theme applied
- Hero section rewritten
- Sync / Chat / Stored Emails sections redesigned
- User and assistant message colors are visually more distinct
- Sync progress panel now shows live backend-driven stage/progress/count updates
- Mailbox card now shows last successful sync timestamp
- Mailbox card now includes recent question history (last 3 user questions)
- Source cards below answers are now labeled `Sources`
- Source cards were visually compacted to feel less like primary answers
- Mailbox card action layout updated so the sync button sits directly under `MAILBOX`
- Ask Inbox waiting state now shows a visible spinner in the button and a live assistant thinking bubble in the chat area
- Vite frontend proxy fixed to target backend port `8000`
- Assistant answer rendering now supports inline `Answer: ...` / `From: ...` field formatting for cleaner cards
- Mailbox tab filters added in chat UI:
  - Primary
  - Promotions
  - Social
  - Updates
- Structured search filters added to the chat UI:
  - Sender
  - Subject
  - Date From
  - Date To
- Main chat card order updated to:
  - filters
  - chat history
  - question input
- Extra spacing added between filter controls and chat history for readability
- Initial last-sync label now shows loading state instead of briefly flashing `not yet run`

- React UI를 단순 이메일 리스트 뷰어에서 Gmail AI 워크스페이스 형태로 업그레이드함
- 보라색 중심 테마 적용
- 상단 Hero 문구 수정
- Sync / Chat / Stored Emails 섹션 리디자인 완료
- user / assistant 메시지 색상 구분 강화
- Sync 진행 중 실제 backend 상태 기반 단계/진행률/건수 표시 추가
- Mailbox 카드에 마지막 성공 sync 시각 표시 추가
- Mailbox 카드에 최근 질문 히스토리(최근 3개) 추가
- 답변 아래 source 카드 라벨을 `Sources`로 변경
- source 카드를 더 컴팩트하게 줄여 주 답변처럼 보이지 않도록 조정
- Mailbox 카드에서 sync 버튼을 `MAILBOX` 바로 아래로 재배치
- Ask Inbox 대기 상태에서 버튼 spinner와 채팅창 assistant thinking bubble이 보이도록 UI 강화
- Vite 프록시가 backend `8000` 포트를 바라보도록 수정
- assistant 답변 렌더링이 `Answer: ...` / `From: ...` 같은 inline field 형식도 파싱해서 카드형으로 보여주도록 개선
- 채팅 UI에 Mailbox tab 필터 추가:
  - Primary
  - Promotions
  - Social
  - Updates
- 채팅 UI에 구조화 검색 필터 추가:
  - Sender
  - Subject
  - Date From
  - Date To
- 메인 chat 카드의 순서를 다음과 같이 재배치:
  - 필터
  - 대화 내역
  - 질문 입력
- 필터 영역과 대화 내역 사이 간격을 늘려 가독성 개선
- 초기 last sync 라벨이 잠깐 `not yet run`으로 보이던 문제를 loading state로 수정

### Search Quality Improvements

- Added text chunking instead of indexing one email as a single block
- Added hybrid retrieval:
  - vector similarity
  - keyword matching
- Added HTML cleanup during parsing
- Improved answer prompting so company/topic lookups explicitly list matching emails
- Added stronger sender matching and sender-prioritized ranking for person-name queries
- Added latest-email source refinement so newest matching messages rank first
- Added sender filtering before answer generation for `from <name>` style questions
- Added email-body cleaning before embedding:
  - signature stripping
  - mobile footer stripping
  - reply-chain removal
- Added heuristic reranking for received-date questions so actual incoming emails beat self-sent drafts
- Added recent-important-email scoring for "top N important emails in the last week" style prompts
- Added LangChain retrieval building blocks:
  - BM25 + FAISS ensemble
  - MultiQueryRetriever
  - SelfQueryRetriever helper
  - ContextualCompressionRetriever with Cohere rerank helper
- Added runtime email-body cleaning before indexing to reduce signature/footer/reply-chain noise
- Added a live runtime retriever layer that can reuse stored vector records directly
- Added config-driven fallback so deterministic retrieval remains active for sender/date/latest questions
- Added deterministic recent-email-list retrieval for latest multi-email summary requests
- Fixed a parser bug where phrases like `from the latest 10 emails` could be misread as a sender filter
- Added Gmail-category-aware retrieval filtering and source display
- Added structured filter-aware retrieval so exact sender/subject/date searches no longer depend only on natural-language parsing
- Replaced Python mailbox scans with FTS5-backed keyword retrieval for much faster exact-match searches
- Added SQLite-backed vector persistence to remove JSON-file scanning bottlenecks

- 이메일 1개를 통째로 인덱싱하던 방식 대신 chunking 추가
- 하이브리드 검색 추가:
  - 벡터 유사도
  - 키워드 매칭
- 파싱 단계에서 HTML 정리 강화
- 회사명/키워드 질의 시 관련 메일을 명시적으로 나열하도록 답변 프롬프트 개선
- 사람 이름 질문에서 sender 매칭을 더 강하게 반영하도록 ranking 보강
- 최신 메일 질문에서 최신 matching message가 먼저 오도록 source 정렬 보정
- `from <name>` 형태 질문에서 답변 생성 전에 sender 필터링 추가
- embedding 전 email body cleaning 추가:
  - signature 제거
  - 모바일 footer 제거
  - reply chain 제거
- 수신 날짜 질문에서 self-sent 메일보다 실제 수신 메일을 우선하도록 heuristic reranking 추가
- "최근 1주일 중요 메일 top N" 스타일 질문을 위한 importance scoring 추가
- LangChain retrieval 구성 요소 추가:
  - BM25 + FAISS ensemble
  - MultiQueryRetriever
  - SelfQueryRetriever helper
  - Cohere rerank 기반 ContextualCompressionRetriever helper
- 인덱싱 전 email body cleaning을 실제 runtime path에 연결하여 signature/footer/reply-chain 노이즈 감소
- 저장된 vector record를 직접 재사용하는 live runtime retriever 레이어 추가
- sender/date/latest 질문은 deterministic retrieval을 유지하고 일반 질문만 LangChain 경로를 타도록 config-driven fallback 추가
- latest 다중 이메일 요약 요청을 위한 deterministic recent-email-list retrieval 추가
- `from the latest 10 emails` 같은 문구가 sender filter로 잘못 해석되던 파서 버그 수정
- Gmail category 기반 retrieval filtering과 source 표시 추가
- sender/subject/date 구조 필터를 retrieval에 직접 반영하여 자연어 파싱 실패 의존도를 낮춤
- Python mailbox scan 대신 FTS5 기반 keyword retrieval로 exact-match 검색 속도 개선
- JSON 파일 병목을 줄이기 위해 SQLite 기반 vector persistence 추가

## Current Architecture | 현재 아키텍처

```text
[Gmail API]
    ↓
[Ingestion Agent]
    ↓
[SQLite Metadata Store]
[SQLite FTS5 Search]
[SQLite Vector Store]
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
- [start-all.ps1](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/start-all.ps1)
- [stop-all.ps1](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/stop-all.ps1)
- [backend/app.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/app.py)
- [backend/config.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/config.py)
- [backend/agents/indexing_agent.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/agents/indexing_agent.py)
- [backend/agents/chat_agent.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/agents/chat_agent.py)
- [backend/retrieval/langchain_email_retrievers.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/retrieval/langchain_email_retrievers.py)
- [backend/retrieval/runtime_retriever.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/retrieval/runtime_retriever.py)
- [backend/retrieval/email_cleaning.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/retrieval/email_cleaning.py)
- [backend/scripts/run_multi_query_retriever.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/scripts/run_multi_query_retriever.py)
- [backend/skills/text_parsing.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/skills/text_parsing.py)
- [backend/tools/metadata_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/metadata_store.py)
- [backend/tools/vector_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/vector_store.py)
- [backend/tools/cache_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/cache_store.py)
- [backend/tools/gmail_client.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/gmail_client.py)
- [backend/tools/sync_progress_store.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/tools/sync_progress_store.py)
- [backend/skills/answer_generation.py](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/backend/skills/answer_generation.py)
- [frontend/src/App.jsx](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/frontend/src/App.jsx)
- [frontend/src/App.css](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/frontend/src/App.css)
- [frontend/vite.config.js](/c:/Users/j00ho/OneDrive/Desktop/Baik/Career/myEmail-chatbot/frontend/vite.config.js)

## Current Runtime State | 현재 실행 상태

- Backend runs locally on `http://127.0.0.1:8000`
- Frontend runs locally on `http://127.0.0.1:5173`
- Gmail OAuth credentials are present
- OpenAI API key is configured in local `.env`
- Redis-backed chat cache is configured in local `.env`
- LangChain retrieval packages are installed in the backend virtual environment
- Optional LangChain runtime retrieval can be enabled through local `.env`
- `LANGCHAIN_RETRIEVAL_ENABLED=true` is now used in local runtime for general-question retrieval
- Local search now uses SQLite FTS5 instead of Python mailbox scanning
- Local vector persistence now uses SQLite `email_vectors`
- Structured search filters are live in the chat UI and backend request contract

- 백엔드는 로컬 `http://127.0.0.1:8000` 에서 실행됨
- 프론트엔드는 로컬 `http://127.0.0.1:5173` 에서 실행됨
- Gmail OAuth credentials 파일이 존재함
- OpenAI API 키가 로컬 `.env`에 설정되어 있음
- Redis 기반 chat cache 설정이 로컬 `.env`에 추가됨
- LangChain retrieval 패키지가 backend 가상환경에 설치됨
- optional LangChain runtime retrieval은 로컬 `.env` 플래그로 활성화 가능
- 로컬 실행에서는 `LANGCHAIN_RETRIEVAL_ENABLED=true`로 일반 질문 retrieval에 적용 중
- 로컬 검색은 이제 Python mailbox scan 대신 SQLite FTS5를 사용함
- 로컬 vector persistence는 이제 SQLite `email_vectors` 테이블을 사용함
- 구조화 검색 필터가 chat UI와 backend request contract에 실제 연결됨

## What Is Not Done Yet | 아직 안 된 것

- Browser extension is not implemented yet
- PostgreSQL / pgvector migration is not implemented yet
- Gmail-search-replacement level ranking is not fully implemented yet

- 브라우저 extension은 아직 미구현
- PostgreSQL / pgvector 전환은 아직 미구현
- Gmail 검색 대체 수준의 정교한 ranking은 아직 미구현

## Known Issues / Observations | 현재 한계 / 관찰사항

- Search accuracy improved, but it can still pull partially related emails
- Some messages may still contain noisy newsletter/email-markup remnants
- Current vector search still computes cosine similarity in Python after loading SQLite-backed vectors into memory
- SQLite is now good enough for local demo search, but vector retrieval would still benefit from a dedicated ANN/vector index later
- Redis cache is versioned by mailbox and invalidated after sync/index refresh
- Sync progress UI currently uses polling against `/api/sync-status`
- `latest` / sender-specific question handling is improved, but still partly heuristic
- JSON vector-store bottleneck is removed, but SQLite-backed vectors still load into memory and use Python cosine scoring
- Source cards still show retrieval evidence separately from the main answer, which may need further UX tuning
- LangChain runtime path is only partially active:
  - general questions use LangChain retrieval
  - sender/date/latest questions still rely on deterministic local logic
- SelfQueryRetriever helper exists, but FAISS-backed runtime wiring is not yet used in production flow
- Cohere compression is optional and only active when `COHERE_API_KEY` is configured
- Multi-email summary/list questions are still not fully modeled by the new planner structure and need explicit retrieval-contract handling
- Current chat path still mixes legacy heuristics with the new planner-oriented direction, so the refactor is in progress rather than fully complete
- Recent-email list requests are now covered, but broader list/filter combinations still need to be folded into the planner consistently

- 검색 정확도는 좋아졌지만, 일부 부분적으로 관련 있는 메일까지 함께 끌어올 수 있음
- 일부 메일은 뉴스레터/이메일 마크업 찌꺼기가 아직 남을 수 있음
- 현재 vector search는 SQLite에 저장된 벡터를 메모리로 올린 뒤 Python cosine scoring을 수행하므로 추가 최적화 여지가 있음
- 현재 SQLite 구조는 로컬 데모 검색에는 충분하지만, vector retrieval은 이후 전용 ANN/vector index로 더 좋아질 수 있음
- Redis cache는 mailbox version 기준으로 관리되며 sync/index refresh 후 무효화됨
- Sync progress UI는 현재 `/api/sync-status` polling 방식으로 동작함
- `latest` / sender 중심 질문 처리는 좋아졌지만 아직 일부 heuristic 기반임
- JSON vector store 병목은 제거됐지만, SQLite 기반 벡터도 현재는 메모리 로드 + Python cosine scoring 구조라 추가 개선 여지가 있음
- source 카드는 본문 답변과 별도로 표시되며 UX 측면에서 추가 조정 여지가 있음
- LangChain runtime 경로는 현재 부분 적용 상태:
  - 일반 질문은 LangChain retrieval 사용
  - sender/date/latest 질문은 deterministic local logic 유지
- SelfQueryRetriever helper는 존재하지만 FAISS 기반 runtime production flow에는 아직 미연결
- Cohere compression은 optional이며 `COHERE_API_KEY`가 있을 때만 활성화됨
- 현재 chat path는 legacy heuristic과 planner 지향 구조가 혼재된 상태라, 리팩터링이 진행 중인 단계임
- recent-email list 요청은 반영됐지만, 더 다양한 list/filter 조합은 planner 구조로 계속 편입이 필요함

## Recommended Next Steps | 추천 다음 단계

### Priority 1

- Harden Gmail sync for very large mailboxes and partial failures
- Add clearer UI state for deletions / fallback-to-full-sync cases
- Improve recovery and resumability around sync interruptions

- 대용량 메일박스와 부분 실패 상황에 대한 Gmail sync 안정화
- 삭제 / full sync fallback 상황을 UI에 더 명확히 표시
- sync 중단 후 복구 / 재개 흐름 개선

### Priority 2

- Upgrade SQLite-backed vector search to a dedicated ANN/vector index such as pgvector, Qdrant, or sqlite-vec
- Fully productionize LangChain retrieval routing:
  - SelfQueryRetriever on a metadata-filter-friendly vector store
  - Cohere rerank evaluation
  - retrieval quality A/B comparison
- Add stronger ranking:
  - sender boosting
  - recency boosting
  - exact subject match
  - attachment and thread-aware ranking
- Expand structured search UX:
  - quick presets for last 7 days / last 30 days
  - optional attachment-only filter
  - visible active-filter chips above results

- 로컬 JSON vector store를 PostgreSQL + pgvector 또는 Qdrant로 업그레이드
- LangChain retrieval routing을 production 수준으로 마무리:
  - metadata filter 친화적 vector store 위의 SelfQueryRetriever
  - Cohere rerank 평가
  - retrieval quality A/B 비교
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

Build a strong local-first Gmail AI search assistant for portfolio demos with reliable structured search.

포트폴리오 데모용으로 구조화 검색까지 안정적인 local-first Gmail AI 검색 도구를 먼저 만든다.

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
Next, harden the Gmail sync flow for large mailboxes and improve structured search UX plus retrieval ranking.
```

또는:

```text
PROJECT_STATUS.md 읽고 이어서 해줘.
다음 단계로 Gmail sync 안정화와 structured search UX / retrieval ranking 개선 작업을 진행하자.
```

## Security Note | 보안 메모

The OpenAI API key was pasted into chat during development. It is recommended to rotate/regenerate that key later for safety.

개발 중 OpenAI API 키가 채팅에 노출되었으므로, 안전을 위해 나중에 해당 키를 회전/재발급하는 것을 권장합니다.
