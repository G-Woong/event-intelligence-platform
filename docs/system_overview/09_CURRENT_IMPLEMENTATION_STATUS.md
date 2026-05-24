# 현재 구현 상태 (STEP 011 기준)

> 2026-05-24, HEAD commit: 38d0028  
> DONE = 실제 동작, PARTIAL = 일부 mock/미완성, TODO = 미구현

---

## 13단계 파이프라인 상태

| # | 단계 | 컴포넌트 | 상태 | Real/Mock | 테스트 | 비고 |
|---|---|---|---|---|---|---|
| 1 | RSS 수집 | `workers/collectors/rss_collector.py` | **DONE** | REAL | `tests/test_rss_collector.py` | feedparser, 3 sources, content_hash 중복 제거 |
| 2 | raw_events 저장 | `backend/app/services/raw_event_service.py` | **DONE** | REAL | backend/tests | PG upsert, ON CONFLICT DO NOTHING |
| 3 | Redis Stream 발행 | `workers/queue/producer.py` | **DONE** | REAL | `tests/test_stream_payload_compat.py` | XADD stream:raw_events |
| 4 | Stream 소비 | `workers/queue/consumer.py` | **DONE** | REAL | workers/tests | XREADGROUP, heartbeat 내장 |
| 5 | Ingest 파이프라인 | `workers/pipelines/ingest_pipeline.py` | **DONE** | REAL | workers/tests | 정규화 → stream:to_agent |
| 6 | Agent-worker → LangGraph | `agents/agent_worker.py` | **DONE** | REAL | agents/tests | heartbeat, XREADGROUP |
| 7 | LangGraph 그래프 | `agents/graphs/event_processing_graph.py` | **PARTIAL** | REAL 5 / MOCK 6 | agents/tests | 선형 11노드, 6노드 mock |
| 8 | FinalEventCard 발행 | `workers/pipelines/publish_pipeline.py` | **DONE** | REAL | — | backend upsert API 호출 |
| 9 | event_cards 저장 | `backend/app/services/event_service.py` | **DONE** | REAL | backend/tests | ON CONFLICT DO UPDATE |
| 10 | Milvus 벡터 색인 | `backend/app/services/vector_index_service.py` | **DONE** | REAL (mock embedding) | backend/tests | try_index_card swallow |
| 11 | OpenSearch 키워드 색인 | `backend/app/services/opensearch_index_service.py` | **DONE** | REAL | backend/tests | try_index_card swallow |
| 12 | FastAPI 검색 | `backend/app/api/events.py` | **DONE** | REAL | backend/tests | OpenSearch multi_match + bool filter |
| 13 | Next.js 화면 + Admin | `frontend/src/app/` | **DONE** | REAL | 8건 node --test | 11 라우트, 4 API route |

---

## LangGraph 11 노드 Real/Mock 상세

| # | 노드명 | 파일 | 상태 | 비고 |
|---|---|---|---|---|
| 1 | source_parse | `agents/nodes/parse_source.py` | **REAL** | 소스 메타 파싱 |
| 2 | normalize_event | `agents/nodes/normalize_event.py` | **REAL** | 텍스트 정규화 |
| 3 | deduplicate_event | `agents/nodes/deduplicate.py` | **PARTIAL** | dedupe_key 생성, 벡터 유사도 기준 미정 |
| 4 | entity_linking | `agents/nodes/entity_linking.py` | **MOCK** | `["[mock-entity-1]", "[mock-entity-2]"]` 고정 반환 |
| 5 | theme_sector_mapping | `agents/nodes/sector_mapping.py` | **MOCK** | 키워드 매칭 단순 분류 |
| 6 | retrieve_past_context | `agents/nodes/retrieve_context.py` | **REAL** | Milvus top-k 실호출 |
| 7 | impact_analysis | `agents/nodes/impact_analysis.py` | **MOCK** | MockLLMClient 템플릿 반환 |
| 8 | evidence_check | `agents/nodes/evidence_check.py` | **MOCK** | 빈 목록 반환 |
| 9 | run_fact_check | `agents/nodes/fact_check.py` | **MOCK** | "pass" 고정 반환 |
| 10 | final_card_writer | `agents/nodes/final_writer.py` | **MOCK** | headline·summary mock 값 |
| 11 | publish_or_hold | `agents/nodes/publish_or_hold.py` | **REAL** | fact_check 기반 status 결정 |

→ REAL: 5개 (1, 2, 6, 11 + partial 3)  
→ MOCK: 6개 (4, 5, 7, 8, 9, 10)

---

## 컨테이너 10개 healthcheck 상태 (STEP 011 기준)

| 컨테이너 | Healthcheck 방식 | 상태 |
|---|---|---|
| `ei-backend` | `curl /health` (15s/10s/5회) | HEALTHY |
| `ei-frontend` | `wget /api/health` (15s/5s/5회) | HEALTHY |
| `ei-postgres` | `pg_isready` (10s/5s/5회) | HEALTHY |
| `ei-redis` | `redis-cli ping` (10s/5s/5회) | HEALTHY |
| `ei-milvus` | `curl /healthz` (30s/20s/5회) | HEALTHY |
| `ei-milvus-etcd` | `etcdctl endpoint health` (30s/20s/3회) | HEALTHY |
| `ei-milvus-minio` | `curl /minio/health/live` (30s/20s/3회) | HEALTHY |
| `ei-opensearch` | `curl /_cluster/health` (10s/5s/30회) | HEALTHY |
| `ei-worker` | heartbeat `/tmp/worker_heartbeat` (30s/5s/3회) | HEALTHY |
| `ei-agent-worker` | heartbeat `/tmp/agent_heartbeat` (30s/5s/3회) | HEALTHY |

---

## 회귀 테스트 현황

| 범위 | 파일 위치 | 테스트 수 | 상태 |
|---|---|---|---|
| backend | `backend/tests/` | ~50건 | PASS |
| agents | `agents/tests/` | ~22건 | PASS |
| workers | `workers/tests/` | ~19건 | PASS |
| smoke (gate) | `tests/smoke/` | 8건 | SKIP (RUN_FULL_PIPELINE_SMOKE=1 시 실행) |
| frontend | `frontend/src/lib/__tests__/` | 8건 | PASS |
| docker config | compose config check | 1건 | PASS |
| **합계** | | **~108건** | **PASS** |

---

## Backend API 구현 상태

| Router | 상태 | 비고 |
|---|---|---|
| `api/health.py` | DONE | — |
| `api/events.py` | DONE | list, search, detail |
| `api/admin.py` | DONE | 10개 엔드포인트 (인증 bypass 주의) |
| `api/internal.py` | DONE | 내부 서비스 전용 |
| `api/themes.py` | PARTIAL | 스켈레톤 자료 |
| `api/sectors.py` | PARTIAL | 스켈레톤 자료 |
| `api/comments.py` | PARTIAL | 미완성 |
| `api/ai_replies.py` | PARTIAL | 미완성 |

---

## 인프라 레이어 구현 상태

| 컴포넌트 | 파일 | 상태 | 비고 |
|---|---|---|---|
| PostgreSQL 연결 | `backend/app/db/postgres.py` | DONE | asyncpg |
| Redis 연결 | `backend/app/db/redis.py` | DONE | 동기 + Stream |
| Milvus 연결 | `backend/app/db/milvus.py` | DONE | pymilvus |
| OpenSearch 연결 | `backend/app/db/opensearch.py` | DONE | opensearch-py |
| 설정 관리 | `backend/app/core/config.py` | DONE | pydantic-settings |
| 보안 | `backend/app/core/security.py` | DONE | Admin token (bypass 상태) |
| 관측성 | `backend/app/core/observability.py` | DONE | LangSmith (선택적) |
| 로깅 | `backend/app/core/logging.py` | DONE | structlog |

---

## 미구현 (TODO) 항목 요약

| 항목 | 현재 상태 | 예정 STEP |
|---|---|---|
| DART collector | 없음 | STEP 013 |
| SEC EDGAR collector | 없음 | STEP 013 |
| 웹 본문 전처리 (trafilatura) | 없음 | STEP 013 (축 C) |
| Hybrid search | OpenSearch keyword only | STEP 012 (축 A) |
| LangGraph mock 6노드 → 실모델 | mock | STEP 014 (축 D) |
| 내장 scheduler daemon | 외부 cron 가정 | STEP 015 |
| RBAC / OAuth | bypass | STEP 015 |
| 한국어 nori analyzer | 없음 | STEP 013 |
| shadcn/ui 디자인 시스템 | 없음 | STEP 014 |
| i18n (국제화) | 없음 | 미정 |
| Playwright e2e | 없음 | 미정 |
| Production deploy / TLS | 없음 | STEP 015+ |
