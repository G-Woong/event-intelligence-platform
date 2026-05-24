# Skeleton Completion Checklist — STEP 011

> 13단계 관통 흐름 완료 상태 (2026-05-24 기준)

## 13단계 파이프라인 관통 흐름

| # | 단계 | 컴포넌트 | 상태 | 비고 |
|---|---|---|---|---|
| 1 | RSS 수집 | `workers/rss_collector.py` | DONE | feedparser, 3 sources, `content_hash` 중복 제거 |
| 2 | raw_events 저장 | `backend/app/api/admin/raw_events.py` | DONE | PG upsert, Redis Stream 발행 |
| 3 | Stream → consumer | `workers/queue/consumer.py` | DONE | xreadgroup, heartbeat /tmp/worker_heartbeat |
| 4 | ingest pipeline | `workers/pipelines/ingest_pipeline.py` | DONE | normalize → to_agent stream |
| 5 | agent-worker → LangGraph | `agents/agent_worker.py` | DONE | heartbeat /tmp/agent_heartbeat |
| 6 | LangGraph 그래프 | `agents/graphs/event_processing_graph.py` | PARTIAL | 6/11 mock 노드 (의도된 skeleton) |
| 7 | FinalEventCard 발행 | `workers/pipelines/publish_pipeline.py` | DONE | backend upsert API 호출 |
| 8 | event_cards PG 저장 | `backend/app/services/event_service.py` | DONE | ON CONFLICT DO UPDATE |
| 9 | Milvus 벡터 색인 | `backend/app/services/vector_index_service.py` | DONE | try_index_card swallow 정책 |
| 10 | OpenSearch 키워드 색인 | `backend/app/services/opensearch_index_service.py` | DONE | try_index_card swallow 정책 |
| 11 | FastAPI 검색 | `backend/app/api/events.py` | DONE | OpenSearch multi_match + bool filter |
| 12 | Next.js frontend | `frontend/src/app/` | DONE | events/search/themes/sectors/admin |
| 13 | Admin operations | `frontend/src/app/api/admin/` | DONE | reindex/reconcile/requeue proxy |

## Mock vs Real 컴포넌트 (STEP 011 시점)

| 컴포넌트 | 현재 상태 | 교체 조건 |
|---|---|---|
| LangGraph NER 노드 | **mock** (heuristic) | STEP 013 도메인 모델 도입 |
| LangGraph 분류기 노드 | **mock** (keyword) | STEP 013 |
| LangGraph impact_path 노드 | **mock** (template) | STEP 013 |
| LLMClient | **mock** (`MockLLMClient`) | `LLM_PROVIDER=openai` env로 교체 |
| EmbeddingClient | **mock** (`MockEmbeddingClient`) | `EMBEDDING_PROVIDER=openai` env로 교체 |
| OpenSearch | **real** | 운영 중 |
| Milvus | **real** | 운영 중 |
| PostgreSQL | **real** | 운영 중 |
| Redis | **real** | 운영 중 |
| RSS Collector | **real** | feedparser + 3 live sources |
| Admin auth | **bypass** (dev: `ADMIN_API_TOKEN` 빈값) | prod 진입 시 token 설정 |

## 컨테이너 상태 (STEP 011 기준)

| 컨테이너 | healthcheck | 비고 |
|---|---|---|
| ei-backend | `curl /health` | HEALTHY |
| ei-frontend | `wget /api/health` | HEALTHY |
| ei-postgres | `pg_isready` | HEALTHY |
| ei-redis | `redis-cli ping` | HEALTHY |
| ei-milvus | `curl /healthz` | HEALTHY |
| ei-milvus-etcd | `etcdctl endpoint health` | HEALTHY |
| ei-milvus-minio | `curl /minio/health/live` | HEALTHY |
| ei-opensearch | `curl /_cluster/health` | HEALTHY |
| ei-worker | heartbeat `/tmp/worker_heartbeat` (STEP 011 추가) | HEALTHY |
| ei-agent-worker | heartbeat `/tmp/agent_heartbeat` (STEP 011 추가) | HEALTHY |

## STEP 012+ 후보 목록

| STEP | 주제 | 우선순위 |
|---|---|---|
| 012 | Hybrid search (Milvus vector + OpenSearch BM25 rerank) | HIGH — RAG_VECTOR_DESIGN.md TODO |
| 013 | DART/SEC collector + 한국어 nori analyzer | HIGH — 신규 데이터 소스 |
| 014 | shadcn/ui + Radix 디자인 시스템 + i18n | MED — UX 고도화 |
| 015 | RBAC / OAuth2 / admin 권한 분리 | MED — 보안 본격화 |
| 016 | Production deploy (CDN, TLS, prod CORS, secrets manager) | MED — 운영 진입 |
| 017 | LangGraph mock 노드 → 실모델 (NER, 분류기) | LOW — 정확도 향상 |
| 018 | Dockerfile non-root user + 멀티스테이지 최적화 | LOW — infra hardening |
| 019 | WebSocket / SSE 실시간 push | LOW — UX |
| 020 | Playwright UI e2e | LOW — 테스트 강화 |

## 회귀 테스트 현황

| 범위 | 테스트 수 | 상태 |
|---|---|---|
| backend/tests | ~50건 | PASS |
| agents/tests | ~22건 | PASS |
| workers/tests | ~19건 | PASS |
| tests/smoke (gate) | 8건 | SKIP (RUN_FULL_PIPELINE_SMOKE=1 시 실행) |
| frontend node --test | 8건 | PASS |
| docker compose config | 1건 | PASS |
