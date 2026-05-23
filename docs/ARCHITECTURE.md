# Architecture — Event Intelligence (STEP 004.5)

## 컴포넌트 다이어그램

```
[외부 소스]
     │
     ▼
[producer.py]
  XADD stream:raw_events
     │
     ▼
[worker (consumer.py)]                         group:ingest
  XREADGROUP stream:raw_events
     │ ingest_pipeline: validate + forward
     ▼
  XADD stream:to_agent
     │
     ▼
[agent-worker (agent_worker.py)]               group:agent
  XREADGROUP stream:to_agent
     │ EventProcessingGraph.run(raw_event)
     │   → 11-node LangGraph pipeline (mock)
     │   → FinalEventCard
     ▼
  POST /api/admin/upsert-event
     │
     ▼
[backend (FastAPI)]
  event_service.upsert_card(session, card)
     │ SQLAlchemy INSERT ... ON CONFLICT DO UPDATE
     ▼
[PostgreSQL 17]
  event_cards / comments 테이블
     │
     ▼
  GET /api/events → FinalEventCard[] (DB 조회)
```

## 서비스 구성

| 서비스 | 이미지 | 포트 | 역할 |
|---|---|---|---|
| redis | redis:7.4-alpine | 6379 | Stream broker |
| postgres | postgres:17-alpine | 5432 | 영속 스토리지 (event_cards, comments) |
| milvus-standalone | milvusdb/milvus:v2.4.10 | 19530, 9091 | Vector store (STEP 005 활성화) |
| backend | ./backend/Dockerfile | 8000 | FastAPI API 서버 |
| worker | ./workers/Dockerfile | - | Stream ingest consumer |
| agent-worker | ./agents/Dockerfile | - | LangGraph pipeline consumer |

## 영속성 정책 (STEP 004)

- **backend만 DB 쓰기**: worker/agent-worker는 DB 직접 접근 금지. HTTP를 통해 backend에 위임.
- **Migration**: `backend/entrypoint.sh`에서 `alembic upgrade head` → `uvicorn` 순서로 실행.
- **Alembic driver 분리**: app은 asyncpg, alembic은 psycopg (env.py에서 URL 치환).

## Redis Stream 선택 이유

- Consumer group으로 메시지 ack/replay 명확
- List 대비 추가 비용: consumer group init 1줄 (`XGROUP CREATE`)
- DLQ/관측 확장에 유리 (XPENDING, XCLAIM)
- Celery 의존 없이 순수 Redis로 워커 파이프라인 구성 가능

## Mock 영역 (STEP 003–004 공통)

- LLM 호출: `LLMClient(provider="mock")` — deterministic 문자열 반환
- 모든 LangGraph 노드: 실제 NLP 없음, 고정 mock 값 반환
- Milvus 임베딩: `insert_embedding`, `search_similar_events` stub (no-op)

## STEP 005 이후 활성화 예정

- 실제 crawler (RSS, sitemap)
- normalize/deduplicate 실제 로직
- `raw_events`, `agent_runs` 테이블 (Postgres)
- Milvus embedding insert/search 실호출
- LangSmith tracing
- OpenAI provider 활성화

## Skeleton Integration 현황 (STEP 004.5 Audit)

### PASS — 연결 완료

| 컴포넌트 | 상태 | 근거 |
|---|---|---|
| FastAPI endpoints (8개) | PASS | 6개 `async def` + `Depends(get_session)` + service layer |
| ORM ↔ Pydantic ↔ Alembic 컬럼 매핑 | PASS | `models/event.py`, `schemas/events.py`, `alembic/versions/0001_initial.py` 3-way 일치 |
| Postgres upsert (ON CONFLICT DO UPDATE) | PASS | `event_service.py:18-39` |
| in-memory 잔존 없음 | PASS | 정적 themes/sectors 상수만 의도적 잔존 |
| Redis Stream end-to-end | PASS | producer → worker → agent-worker → backend 경로 연결 |
| LangGraph 11-node graph 컴파일 | PASS | `event_processing_graph.py` StateGraph wiring |
| worktree 격리 | PASS | claude/codex 분리, CLAUDE.md/AGENTS.md 명문화 |
| requirements 9개 레이어 분리 | PASS | serve/worker/ai/vector/ml/crawler/dev/graph_optional + base |
| Docker 7개 컨테이너 healthy | PASS | backend `depends_on: service_healthy` 정상 |
| 볼륨 영속화 | PASS | pg_data, etcd/minio/milvus/redis_data 선언 |

### STUB — 자리 있음, 미구현

| 컴포넌트 | 현황 | 목표 STEP |
|---|---|---|
| LangGraph 노드 8/11 mock | 고정 하드코딩 반환 | STEP 005–006 |
| LLMClient | `backend/app/services/llm_client.py` 존재, agent 노드에서 미사용 | STEP 005 |
| Milvus insert/search | `db/milvus.py:33-42` 빈 stub (no-op) | STEP 006 |
| themes/sectors | 정적 상수, service layer 없음 (의도된 skeleton) | 미정 |

### MISSING — 자리 없음, 코드 부재

| 컴포넌트 | 현황 | 목표 STEP |
|---|---|---|
| crawler collector | `requirements/crawler.txt` pin만 존재 | STEP 007 |
| OpenSearch | 코드·문서에 자리 없음 | 먼 STEP |
| Next.js frontend | `frontend/` 디렉터리 없음 | 먼 STEP |

## 다음 STEP 순서 (Audit 기반 권장)

1. **STEP 005** — LLMClient를 agent 노드에 wire-up (mock provider 유지, 노드 1-2개 교체)
2. **STEP 006** — Milvus insert/search 실호출 (`retrieve_past_context`/`deduplicate` 실연결)
3. **STEP 007** — 첫 번째 실제 crawler (RSS 1종, `raw_events` 테이블 도입)
4. **STEP 008** — OpenAI provider 활성화 (비용 가드 + 토큰 한도)
5. **STEP 009** — Next.js `/events` 목록 UI (read-only, public API)
