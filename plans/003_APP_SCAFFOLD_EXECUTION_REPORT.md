# STEP 003 — App Scaffold Execution Report

실행일: 2026-05-23

## ① 무엇을 했는가

### Phase A — Runtime Environment 문서화
- `CLAUDE.md` 최상단에 `## Runtime Environment` 섹션 추가 (gitignored 유지)
- `codex/AGENTS.md` 최상단에 `## Runtime Environment` 섹션 추가 (gitignored 유지)
- `plans/003_APP_SCAFFOLD_PLAN.md`에 "superseded by repo-sunny-barto.md" 헤더 추가

### Phase B — 디렉토리 / schema 생성
- `backend/app/schemas/events.py` — RawEvent, NormalizedEvent, FinalEventCard
- `backend/app/schemas/comments.py` — Comment, AIReplyRequest
- `agents/state/event_state.py` — EventState TypedDict
- `backend/app/models/README.md` — placeholder
- 모든 `__init__.py` 배치 (backend, agents, workers, tests/smoke)

### Phase C — DB / Service / LLM wrapper
- `backend/app/core/config.py` — pydantic-settings BaseSettings, `.env` 8개 키, `redacted_env_status()`
- `backend/app/core/logging.py` — SecretMaskingFilter (OPENAI_API_KEY, LANGSMITH_API_KEY 마스킹)
- `backend/app/db/redis.py` — get_redis(), ping(), ensure_group(), xadd(), xreadgroup(), xack()
- `backend/app/db/milvus.py` — connect() (실동작), ensure_collection/insert_embedding/search_similar_events (stub)
- `backend/app/db/postgres.py` — placeholder, NotImplementedError
- `backend/app/services/llm_client.py` — LLMClient(provider="mock"), mock는 deterministic, openai는 NotImplementedError
- `backend/app/services/event_service.py` — in-memory dict store
- `backend/app/services/comment_service.py` — in-memory list store

### Phase D — FastAPI 12개 endpoint
- `backend/app/main.py` — FastAPI lifespan, 7개 라우터 mount
- `GET /health`, `GET /api/events`, `GET /api/events/{id}`, `GET /api/themes`, `GET /api/themes/{id}/events`
- `GET /api/sectors`, `GET /api/sectors/{id}/events`, `POST /api/comments`, `GET /api/events/{id}/comments`
- `POST /api/ai-replies/request`, `GET /api/admin/jobs`, `POST /api/admin/upsert-event`

### Phase E — LangGraph EventProcessingGraph
- `agents/graphs/event_processing_graph.py` — 11-node StateGraph 컴파일, `run(RawEvent) -> FinalEventCard`
- 노드: source_parse → normalize_event → deduplicate_event → entity_linking → theme_sector_mapping → retrieve_past_context → impact_analysis → evidence_check → run_fact_check → final_card_writer → publish_or_hold
- 수정: `fact_check` 노드명이 EventState 키와 충돌 → `run_fact_check`으로 rename

### Phase F — Worker / Agent-worker
- `workers/queue/producer.py` — enqueue_raw_event() → XADD stream:raw_events
- `workers/queue/consumer.py` — XREADGROUP group:ingest, ingest_pipeline 호출
- `workers/pipelines/ingest_pipeline.py` — 파싱 후 stream:to_agent forward
- `workers/pipelines/publish_pipeline.py` — FinalEventCard → HTTP POST /api/admin/upsert-event
- `agents/agent_worker.py` — XREADGROUP group:agent, EventProcessingGraph.run() 실행 후 publish_card()

### Phase G — Docker 확장
- `backend/Dockerfile` — python:3.11-slim + curl + serve.txt + vector.txt + worker.txt
- `workers/Dockerfile` — python:3.11-slim + worker.txt
- `agents/Dockerfile` — python:3.11-slim + ai.txt + worker.txt
- `docker-compose.dev.yml` — backend/worker/agent-worker 3개 서비스 추가

### Phase H — 문서
- `docs/EVENT_SCHEMA.md`, `docs/API_CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/TRD.md`

## ② 무엇을 검증했는가

| 항목 | 결과 |
|---|---|
| `import backend.app.main` | PASS |
| `import agents.graphs.event_processing_graph` | PASS (fact_check 충돌 수정 후) |
| `import workers.queue.consumer` | PASS |
| `pytest backend/tests -q` | PASS (6/6) |
| `docker compose config --quiet` | PASS |
| `docker compose build backend worker agent-worker` | PASS |
| `docker compose up -d backend worker agent-worker` | PASS (backend healthcheck curl 수정 후) |
| `GET /health` | `{"status":"ok","redis":"ok","milvus":"ok"}` 200 PASS |
| end-to-end smoke test | PASS — 2 card(s) found, status=published |
| `docker compose logs` 확인 | PASS — worker forward, agent-worker POST 200 OK 전 구간 확인 |

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING
- `pymilvus pkg_resources` deprecation 경고: 알려진 이슈(STEP 002.6 기록). setuptools<81 핀 필요하나 compose 이미지에서는 다른 버전으로 오버라이드됨. 기능 영향 없음.
- backend Dockerfile에 `requirements/worker.txt` 추가 필요 (plan에 누락 → 발견 후 즉시 수정)
- backend Dockerfile에 `curl` 설치 필요 (healthcheck용 — python:3.11-slim에 미포함 → 발견 후 즉시 수정)
- end-to-end smoke test 출력에서 em dash `—` → ASCII `-`로 수정 (Windows CP949 인코딩 이슈)
- event_service in-memory store는 프로세스 재시작 시 소멸. STEP 004에서 Postgres 도입 필요.

### BLOCKED
- 없음

### UNKNOWN
- 없음

## STEP 004 제안

1. **실제 crawler 1종** (RSS 또는 단일 sitemap) — 실시간 수집 시작
2. **normalize_event / deduplicate 실제 로직** — 제목 추출, hash 중복 탐지
3. **Milvus embedding insert/search 실제 호출** — pymilvus 2.4.4 핀 유지
4. **LangSmith tracing 연동** — LANGSMITH_API_KEY 설정 후 활성화
5. **OpenAI provider 활성화** — 비용 가드 + 토큰 한도 설정
6. **Postgres 도입** — comment/event 영속화, SQLAlchemy ORM 추가
7. **기초 Next.js page** — `/events` 목록 조회 UI
