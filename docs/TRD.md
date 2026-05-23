# Technical Requirements Document — STEP 006

## 런타임 스택

| 항목 | 버전 | 비고 |
|---|---|---|
| Python | 3.11.x | `py -3.11` / uv venv |
| FastAPI | 0.115.14 | `requirements/serve.txt` |
| uvicorn | 0.35.0 | ASGI 서버 |
| pydantic | 2.11.7 | schema / settings |
| pydantic-settings | 2.7.1 | `.env` 로드 |
| SQLAlchemy | 2.0.36 | ORM + async core (`requirements/serve.txt`) |
| asyncpg | 0.30.0 | FastAPI async PG driver |
| alembic | 1.14.0 | DB migration |
| greenlet | 3.1.1 | SQLAlchemy async 의존 |
| psycopg[binary] | 3.2.3 | alembic sync 실행용 driver |
| redis | 5.0.0 | Stream I/O (`requirements/worker.txt`) |
| pymilvus | 2.4.4 | Vector store client (`requirements/vector.txt`) |
| langgraph | 0.2.76 | Event processing graph (`requirements/ai.txt`) |
| langchain-core | 0.2.43 | LangGraph 의존 |
| openai | 1.108.1 | LLM 호출 + Embedding opt-in (`requirements/ai.txt`) |
| tenacity | 8.5.0 | OpenAI retry (`requirements/base.txt`) |
| httpx | 0.28.1 | agent-worker → backend HTTP 호출 |

## STEP 006 신규 컴포넌트

| 컴포넌트 | 경로 | 역할 |
|---|---|---|
| EmbeddingClient | `backend/app/services/embedding_client.py` | Mock/OpenAI 임베딩 client (LLMClient 미러) |
| vector_index_service | `backend/app/services/vector_index_service.py` | upsert_card 후 embed + Milvus insert orchestrator |
| `/api/internal/search-similar` | `backend/app/api/internal.py` | query_text embed → Milvus search → Postgres lookup |
| vector.py schema | `backend/app/schemas/vector.py` | SimilarEventQuery / SimilarEventHit / SimilarEventResponse |
| vector_search tool | `agents/tools/vector_search.py` | retrieve_past_context용 httpx thin wrapper |

## STEP 006 환경 변수 추가

| 키 | 기본값 | 비고 |
|---|---|---|
| EMBEDDING_PROVIDER | "mock" | "mock" \| "openai" |
| EMBEDDING_MODEL | "text-embedding-3-small" | OpenAI 모델명 |
| EMBEDDING_DIM | 1536 | vector 차원 (고정) |
| EMBEDDING_TIMEOUT_SEC | 30.0 | OpenAI 호출 timeout |
| MILVUS_COLLECTION | "event_embeddings" | Milvus collection명 |
| BACKEND_INTERNAL_URL | "http://backend:8000" | agent-worker → backend 내부 URL |

## 인프라

| 항목 | 버전 | 비고 |
|---|---|---|
| Redis | 7.4-alpine | Stream broker, in-memory KV |
| PostgreSQL | 17-alpine | 영속 스토리지 (event_cards, comments) |
| Milvus | v2.4.10 | Vector store (STEP 006: 실호출 활성화) |
| Docker Compose | v2 | `event-intelligence-dev` project |

## 환경 변수 (`.env` + compose override)

| 키 | 기본값 | 비고 |
|---|---|---|
| LANGSMITH_TRACING | "" | 비어있으면 WARNING |
| LANGSMITH_ENDPOINT | "" | |
| LANGSMITH_API_KEY | "" | 길이만 로그 |
| LANGSMITH_PROJECT | "" | |
| OPENAI_API_KEY | "" | mock provider에서는 미사용. openai provider 선택 시 필수 |
| MILVUS_HOST | localhost | compose: `milvus-standalone` |
| MILVUS_PORT | 19530 | |
| REDIS_URL | redis://localhost:6379/0 | compose: `redis://redis:6379/0` |
| DATABASE_URL | postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel | compose: host=`postgres` |
| LLM_PROVIDER | mock | `mock` 또는 `openai`. agent-worker 환경변수로 명시 |
| LLM_MODEL | gpt-4o-mini | openai provider 사용 시 모델명 |
| LLM_TIMEOUT_SEC | 30.0 | OpenAI API 요청 타임아웃 (초) |
| LLM_MAX_TOKENS | 1024 | 최대 응답 토큰 수 |
| LLM_TEMPERATURE | 0.2 | 생성 온도 (0.0~1.0) |

## Stream 구성

| Stream | Group | Consumer | 방향 |
|---|---|---|---|
| stream:raw_events | group:ingest | worker-1 | producer → worker |
| stream:to_agent | group:agent | agent-worker-1 | worker → agent-worker |

## DB 구성

| 테이블 | 역할 |
|---|---|
| event_cards | FinalEventCard 영속 저장 |
| comments | 사용자 댓글 |

Migration: `alembic upgrade head` (backend/entrypoint.sh에서 자동 실행).

## LLM 구성 (STEP 005)

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| BaseLLMClient | `backend/app/services/llm_client.py` | 공통 인터페이스 (ABC) |
| MockLLMClient | 동일 | 결정론적 mock 응답, 테스트용 |
| OpenAILLMClient | 동일 | openai SDK 동기 호출, tenacity retry 2회 |
| get_llm_client() | 동일 | lazy singleton (노드별 재생성 없음) |
| agents/tools/llm.py | `agents/tools/llm.py` | 노드-LLM 사이 thin wrapper (4개 헬퍼) |
| agents/prompts/*.md | `agents/prompts/` | 교체 가능한 프롬프트 템플릿 |

## 비기능 요구사항 (STEP 005 범위)

- LLM_PROVIDER=mock 기본 — 기존 e2e/smoke 회귀 0건
- OpenAI 실호출은 `RUN_OPENAI_SMOKE=1` opt-in 시에만
- backend Dockerfile에 ai.txt 미설치 (불필요한 의존성 비대화 방지)
- agent-worker Dockerfile에만 ai.txt (openai 패키지) 포함
- `.env` 실값 로그 금지 (`OPENAI_API_KEY` 부분 마스킹도 금지, 길이만 logger.debug)
- Pydantic 검증 실패 시 fallback 반환, pipeline 전체 차단 없음
- `restart: on-failure`로 비정상 종료 시 자동 재시작

## STEP 007 신규 컴포넌트

| 컴포넌트 | 경로 | 역할 |
|---|---|---|
| RawEventORM | `backend/app/models/raw_event.py` | raw_events 테이블 ORM |
| RawEventCreate/Record | `backend/app/schemas/raw_events.py` | 입력/DB row/응답 스키마 |
| raw_event_service | `backend/app/services/raw_event_service.py` | idempotent insert + XADD |
| POST /api/admin/raw-events | `backend/app/api/admin.py` | collector write boundary |
| POST /api/admin/collect-rss-once | `backend/app/api/admin.py` | in-process RSS 트리거 |
| rss_collector | `workers/collectors/rss_collector.py` | feedparser one-shot run() |
| sources | `workers/collectors/sources.py` | DEFAULT_SOURCES + get_sources() |
| 0002_raw_events | `backend/alembic/versions/0002_raw_events.py` | raw_events migration |

## STEP 007 환경변수

| 키 | 기본값 | 비고 |
|---|---|---|
| `RSS_COLLECTOR_FETCH_TIMEOUT_SEC` | `15` | feedparser socket timeout |
| `RSS_SOURCES_CONFIG_PATH` | `""` | stub. 비어있으면 DEFAULT_SOURCES 사용 |
| `RSS_COLLECTOR_USER_AGENT` | `"event-intelligence/0.7 (+ei)"` | HTTP User-Agent |
| `RUN_RSS_LIVE_SMOKE` | `""` | `"1"` 이면 live smoke 실행 |

## STEP 007 DB 구성

| 테이블 | 인덱스/제약 | 비고 |
|---|---|---|
| `raw_events` | PK(id), UNIQUE(content_hash), partial UNIQUE(source_type, external_id), ix_collected_at, ix_status, ix_source_type, ix_published_at, GIN(raw_metadata) | Alembic revision b2c3d4e5f6a7 |

## STEP 007 인프라 변경

- `requirements/collector.txt` 신규: `feedparser==6.0.11`
- `workers/Dockerfile`: `collector.txt` 설치 추가
- `backend/Dockerfile`: `collector.txt` + `workers/` COPY 추가 (`/collect-rss-once` 지원)

## STEP 008A 신규 컴포넌트

| 컴포넌트 | 경로 | 역할 |
|---|---|---|
| observability | `backend/app/core/observability.py` | LangSmith tracing wiring (startup 1회) |
| update_status | `backend/app/services/raw_event_service.py` | raw_event status lifecycle 단일 진입점 |
| get_raw_event | `backend/app/services/raw_event_service.py` | 단일 row 조회 (폴링용) |
| PATCH /raw-events/{id}/status | `backend/app/api/admin.py` | agent-worker → backend 통보 |
| GET /raw-events/{id} | `backend/app/api/admin.py` | status 폴링 |
| _notify_status | `agents/agent_worker.py` | agent pipeline 결과 backend 통보 |
| 0003 migration | `backend/alembic/versions/0003_raw_events_event_card_link.py` | event_card_id + processed_at 컬럼 |

## STEP 008A 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| `LANGSMITH_TRACING` | `""` | `true`/`1`/`yes` 이면 LangSmith tracing 활성화 |
| `BACKEND_INTERNAL_URL` | `http://backend:8000` | agent-worker → backend 내부 통신 |
| `RUN_LANGSMITH_SMOKE` | `""` | `1`이면 LangSmith 실전송 smoke opt-in |

## STEP 008A DB 구성

| 테이블 | 신규 컬럼/인덱스 | 비고 |
|---|---|---|
| `raw_events` | `event_card_id UUID NULL`, `processed_at TIMESTAMPTZ NULL` | Alembic revision c3d4e5f6a7b8 |
| `raw_events` | ix_raw_events_event_card_id, ix_raw_events_processed_at | — |

## STEP 008A status 라이프사이클

`collected → enqueued → processed | failed`

- XADD 실패: `collected → failed` (error_reason: "xadd_failed:...")
- agent pipeline 성공: `enqueued → processed` (event_card_id, processed_at 저장)
- agent pipeline 예외: `enqueued → failed` (error_reason, processed_at 저장)
