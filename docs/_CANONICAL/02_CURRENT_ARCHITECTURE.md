# 02 — CURRENT ARCHITECTURE (현재 아키텍처 단일 출처)

> 수치·상태가 다른 문서와 어긋나면 **이 문서를 따른다**. 근거는 코드/산출물.

---

## 1. 두 서브시스템 (병행, 미통합)

| | A. ingestion 엔진 | B. 다운스트림 앱 |
|---|---|---|
| 위치 | `ingestion/` | `backend/` `workers/` `agents/` `frontend/` |
| 역할 | 57소스 수집·정규화·품질·정책 게이트 | raw_events→사건카드 생성·검색·표시 |
| 출력 | EventQueue JSONL → bridge(mirror **또는** backend) | event_cards PG + Milvus + OpenSearch |
| 입력 | 공개 RSS/API/정적HTML/Playwright | `workers/` RSS 3소스 + **A 통합경유** → raw_events PG |
| 패러다임 | deterministic, 신규 설치 0 | 컨테이너 10개, Redis Stream 기반 |
| 연결 | **A→B 배선 PARTIAL**: `ingestion/integration/`(BackendApiRawEventsWriter). **라이브 외부→backend sink→card E2E 관찰**(ap_news 100→event_cards 100 hold). 남은 blocker: 기본 sink mirror·46소스 전수 sweep·LLM급 카드(01/04/05) | — |

## 2. 컨테이너 (10개, docker-compose.dev.yml, project `event-intelligence-dev`)

`ei-backend`(FastAPI) · `ei-frontend`(Next.js) · `ei-postgres` · `ei-redis` ·
`ei-milvus` (+ `ei-milvus-etcd`, `ei-milvus-minio`) · `ei-opensearch` ·
`ei-worker` · `ei-agent-worker`. 인프라 서비스는 `127.0.0.1` 바인딩, backend/frontend만 `0.0.0.0`.
heartbeat 파일 healthcheck(worker/agent-worker, 60s 임계).

## 3. Backend API (FastAPI, `backend/app/api/`)

| Router | 상태 | 비고 |
|---|---|---|
| health | DONE | components.opensearch 포함 |
| events | DONE | list/search(OpenSearch multi_match)/detail; OpenSearch down 시 503 |
| admin | DONE | 10 엔드포인트, raw-events upsert/status/reconcile/requeue; **dev bypass 주의** |
| internal | DONE | /search-similar(Milvus) |
| themes / sectors | **PARTIAL** | 스켈레톤 자료 |
| comments / ai_replies | **PARTIAL** | 미완성 |

## 4. 데이터 스키마 (Postgres, alembic 0001~0005)

- **raw_events**: source_type/name, external_id, url, title(≤1024), raw_text(요약만, 본문 저장 금지),
  published_at(UTC), feed metadata JSONB, status(collected→enqueued→processed|failed),
  content_hash UNIQUE, event_card_id FK, requeue_count. (`backend/app/models/raw_event.py`)
- **event_cards**: id/title/summary/theme/sectors(JSONB)/entities(JSONB)/impact_path/evidence/
  confidence_score/status/llm_provider/model_used/created_at + **event_id nullable FK→events**(S1, ADR#16: 카드=Event 스냅샷, NULL=degenerate). (`backend/app/models/event.py`)
- **events / event_updates** (S1 토대, alembic 0004, 2026-06-22): `events`(canonical_title/status/first_seen/last_update/heat/domains·tags·primary_entity_ids JSONB/snapshot_card_id FK→event_cards) + `event_updates`(append-only: observed_at/delta_summary/evidence·source_refs·added_domains JSONB/heat_delta, event_id FK→events CASCADE). (`backend/app/models/event_timeline.py`)
- **cluster_event_map / event_links** (S2a, alembic 0005, 2026-06-22): `cluster_event_map`(cluster_id PK→event_id 라우팅 단일 진실원천) + `event_links`(event↔event, status possible/confirmed/rejected/merged CheckConstraint, 약신호 자동병합 금지). (`backend/app/models/event_resolution.py`) — **entities 는 S4~ 미생성.**
- **Event Resolution 서비스 계층** (S2c/S2d/S2e, 2026-06-22): `event_resolver.resolve_routing`(순수 라우팅 APPEND/HOLD/CREATE + clique 게이트, ingestion 비의존) + `event_timeline_service`(CRUD 영속: create_event/append_update append-only/get_event/set_snapshot 쌍방향강제/map_cluster·get_cluster_event/hold_link possible/apply_routing 단일 원자 tx+동시 CREATE rollback — ADR#19) + **`event_resolution_pipeline`(S2e: 실 cross_source_dedup→resolver→apply_routing 배선, ingestion 비의존 duck-typed)**. 통합 로직 E2E 입증(in-memory fake session, `test_event_resolution_pipeline`): 2번째 보도→append·transitive 약신호 보류·멱등·FSD·sanitize. **삭제 정책 ADR#20**(app no-delete + status 라이프사이클). **잔여:** live-PG E2E·heat 4신호(S2.5)·merge_score entity/domain(S4)·LLM 보조 레이어(경계만 개방).
- **comments**: 스켈레톤. comment body_text/debate 확장 마이그레이션은 미생성(S9). (0004=event_timeline, 0005=event_resolution 에 할당됨)

## 5. 검색·RAG (3엔진 분리)

- **Milvus** `event_embeddings` dim=1536 IVF_FLAT/COSINE — 시맨틱. `retrieve_past_context` 노드가 top-k 실호출.
- **OpenSearch** `event_cards` standard analyzer + `text_all` 복합필드 — 키워드(bool/must multi_match, title^2).
- **Postgres** — 원천·정확필터.
- 인덱싱: `upsert_card → PG commit → Milvus insert(swallow) → OpenSearch index(swallow)`.

## 6. LLM / 임베딩 추상화

- `BaseLLMClient` Protocol: `complete()` + `complete_json(schema=...)`, 무상태, 예외 전파 안 함(실패 시 None→안전 기본값).
- `MockLLMClient`(schema.__name__ 디스패치) ↔ `OpenAIClient` — `LLM_PROVIDER` env로 전환.
- `MockEmbeddingClient`(sha256 결정론) ↔ `OpenAIEmbeddingClient`(text-embedding-3-small) — `EMBEDDING_PROVIDER`.
- 출력 스키마는 `agents/tools/llm.py`에 집중. 프롬프트는 `agents/prompts/*.md`(현재 코드 미연결, 08).

## 7. Frontend (`frontend/`, Next.js 15.5.18 / React 19 / TS5 / Tailwind / Node20-alpine)

11 페이지 라우트 + 4 API route handler(health/reindex/reconcile/requeue).
`server-only` 격리로 `X-Admin-Token`은 서버측만(`NEXT_PUBLIC_*` 금지). 8 UI 컴포넌트. 멀티스테이지 Dockerfile(non-root).

## 8. 버전 핀 (변경 금지 항목)

Python 3.11 / langgraph 0.2.76 / langchain 0.2.11(v1 업그레이드 보류) /
FastAPI 0.115.x / SQLAlchemy 2.0.x / asyncpg 0.30 / alembic 1.14 / pymilvus 2.4.4 / openai 1.108.x /
Next.js 15.5.18(CVE-2025-29927 대응). uv 전용, conda 금지.

## 9. 관측성·보안

- LangSmith: `setup_langsmith()`, `LANGSMITH_TRACING=true` opt-in, API 키 로깅 금지(길이만).
- Admin 토큰 bypass(빈 값=허용)는 dev 한정 — 운영 전 해제 필요(05 R-Auth).
- 비밀: `.env`만, `os.getenv`/pydantic-settings로만 읽음, 직렬화/로그 금지.
