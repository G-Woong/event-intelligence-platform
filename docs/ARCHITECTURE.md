# Architecture — Event Intelligence (STEP 007)

## 컴포넌트 다이어그램

```
[RSS feed (feedparser)]                       ← IMPLEMENTED (STEP 007)
  feedparser.parse(url)
     │ workers/collectors/rss_collector.py
     ▼
POST /api/admin/raw-events
     │ raw_event_service.create_raw_event()
     │   pg_insert ON CONFLICT DO NOTHING (content_hash)
     │   asyncio.to_thread(enqueue_raw_event)
     ▼
[raw_events 테이블]  status: collected → enqueued
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
     │   → 11-node LangGraph pipeline
     │   → BaseLLMClient (mock|openai) via get_llm_client()
     │   → agents/tools/llm.py helpers
     │   → FinalEventCard
     ▼
  POST /api/admin/upsert-event
     │
     ▼
[backend (FastAPI)]
  event_service.upsert_card(session, card)
     │ SQLAlchemy INSERT ... ON CONFLICT DO UPDATE
     ├─ await session.commit()
     │
     ▼ (STEP 006 추가)
  vector_index_service.try_index_card(card)
     │ EmbeddingClient.embed_text(title + summary)
     │ milvus.insert_event_embedding(event_id, embedding, ...)
     ▼
[Milvus 2.4.10]   collection: event_embeddings (dim=1536)
     │
     ▼ (retrieve_past_context 경로)
[agent-worker retrieve_past_context]
     │ vector_search.search_similar(text, top_k=5)
     │ POST /api/internal/search-similar
     ▼
  milvus.search_similar_events(embedding, top_k)
     │ Postgres lookup (event_id → title/summary)
     ▼
  state.past_context: list[str]
  state.retrieved_context: list[dict]
     │
     ▼
[PostgreSQL 17]
  event_cards / comments 테이블
     │
     ▼
  GET /api/events → FinalEventCard[] (DB 조회)
```

## Reconciler 흐름 (STEP 008B)

```
[관리자 / cron (STEP 008C+)]
  POST /api/admin/raw-events/reconcile-stuck
       { before_seconds: 600, limit: 100, dry_run: false }
     │ reconciler_service.mark_stuck_as_failed()
     │   list_by_status_older_than(status="enqueued", before_seconds=N)
     │   UPDATE raw_events SET status="failed" WHERE id IN (...)
     ▼
[raw_events 테이블]  stuck enqueued → failed

  GET /api/admin/raw-events?status=enqueued&before_seconds=600
     │ raw_event_service.list_by_status_older_than()
     ▼
  [RawEventRecord list]
```

### stuck enqueued 발생 5가지 경로

| 경로 | 원인 |
|---|---|
| 워커 프로세스 사망 | 메시지 ack 전 종료 → xpending 잔존 |
| PATCH 실패 | agent-worker의 _notify_status가 3회 retry 후 실패 |
| backend 다운 | PATCH 수신 불가 → status=enqueued 유지 |
| graph hang | LangGraph 무한 대기 → finally xack만 실행 |
| ingest forward 후 실패 | worker→stream:to_agent 후 agent-worker 처리 실패 |

### Docker migration 정책 (STEP 008B)

신규 alembic revision 추가 시:
```
docker compose -f docker-compose.dev.yml build --build-arg CACHEBUST=$(date +%s) backend
```
`ARG CACHEBUST` + `COPY backend/alembic/versions/` 분리 레이어로 stale cache 방지.

## LLM 호출 경로 (STEP 005)

```
agent-worker
  └── EventProcessingGraph.run()
        └── [impact_analysis node]
              └── agents/tools/llm.py :: analyze_impact()
                    └── get_llm_client()  ← lazy singleton
                          └── BaseLLMClient
                                ├── MockLLMClient   (LLM_PROVIDER=mock, 기본)
                                └── OpenAILLMClient (LLM_PROVIDER=openai, opt-in)
        └── [run_fact_check node]
              └── agents/tools/llm.py :: fact_check_claims()
        └── [final_card_writer node]
              └── agents/tools/llm.py :: write_final_card()
```

## 서비스 구성

| 서비스 | 이미지 | 포트 | 역할 |
|---|---|---|---|
| redis | redis:7.4-alpine | 6379 | Stream broker |
| postgres | postgres:17-alpine | 5432 | 영속 스토리지 (event_cards, comments, raw_events) |
| milvus-standalone | milvusdb/milvus:v2.4.10 | 19530, 9091 | Vector store (STEP 006 활성화) |
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

## Mock 영역 (STEP 005 현황)

- LLM 호출: `LLM_PROVIDER=mock` (기본) → MockLLMClient — deterministic 응답
- 8/11 LangGraph 노드: 여전히 mock (entity_linking, theme_sector_mapping, retrieve_past_context, deduplicate, evidence_check, source_parse, normalize_event, publish_or_hold)
- **3/11 노드 LLM wire-up 완료**: impact_analysis, run_fact_check, final_card_writer
- Milvus 임베딩: `insert_embedding`, `search_similar_events` stub (no-op)
- backend의 ai_replies.py: mock 고정 유지

## Skeleton Integration 현황 (STEP 005)

### PASS — 연결 완료

| 컴포넌트 | 상태 | 근거 |
|---|---|---|
| FastAPI endpoints (8개) | PASS | 6개 `async def` + `Depends(get_session)` + service layer |
| ORM ↔ Pydantic ↔ Alembic 컬럼 매핑 | PASS | `models/event.py`, `schemas/events.py`, `alembic/versions/0001_initial.py` 3-way 일치 |
| Postgres upsert (ON CONFLICT DO UPDATE) | PASS | `event_service.py:18-39` |
| in-memory 잔존 없음 | PASS | 정적 themes/sectors 상수만 의도적 잔존 |
| Redis Stream end-to-end | PASS | producer → worker → agent-worker → backend 경로 연결 |
| LangGraph 11-node graph 컴파일 | PASS | `event_processing_graph.py` StateGraph wiring |
| **LLMClient wire-up** | **PASS** | BaseLLMClient/Mock/OpenAI + get_llm_client() singleton. 3개 노드에 tools/llm.py 경유 연결 |
| **prompt 디렉터리** | **PASS** | `agents/prompts/*.md` 4개 + load_prompt() 헬퍼 |
| worktree 격리 | PASS | claude/codex 분리, CLAUDE.md/AGENTS.md 명문화 |
| requirements 9개 레이어 분리 | PASS | serve/worker/ai/vector/ml/crawler/dev/graph_optional + base |
| Docker 7개 컨테이너 healthy | PASS | backend `depends_on: service_healthy` 정상 |
| 볼륨 영속화 | PASS | pg_data, etcd/minio/milvus/redis_data 선언 |

### STUB — 자리 있음, 미구현

| 컴포넌트 | 현황 | 목표 STEP |
|---|---|---|
| LangGraph 노드 8/11 mock | 고정 하드코딩 반환 (entity_linking, theme, retrieve, dedupe, evidence, parse, normalize, publish) | STEP 006–010 |
| Milvus insert/search | `db/milvus.py:33-42` 빈 stub (no-op) | STEP 006 |
| themes/sectors | 정적 상수, service layer 없음 (의도된 skeleton) | 미정 |
| OpenAI 실호출 | `LLM_PROVIDER=openai` 설정 시 가능하나 기본 비활성 | 수동 opt-in 가능 |

### MISSING — 자리 없음, 코드 부재

| 컴포넌트 | 현황 | 목표 STEP |
|---|---|---|
| crawler collector (RSS) | `workers/collectors/rss_collector.py` | **DONE (STEP 007)** |
| OpenSearch | `backend/app/db/opensearch.py` + `opensearch_index_service` + `search_service` | **DONE (STEP 009)** |
| Next.js frontend | `frontend/` 디렉터리 없음 | 먼 STEP |

## 다음 STEP 순서

1. ~~**STEP 006**~~ — Milvus insert/search 실호출 (완료)
2. ~~**STEP 007**~~ — RSS collector + raw_events + Alembic migration (완료)
3. **STEP 008** — agent-worker async + raw_event_id stream linkage + processed/failed status + LangSmith tracing
4. **STEP 009** — Next.js `/events` 목록 UI + admin raw-events GET + collector_sources 테이블
5. **STEP 010** — DART/SEC collector + vector dedup + entity linking LLM 전환
