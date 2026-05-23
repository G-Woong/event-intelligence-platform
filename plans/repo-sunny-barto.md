# STEP 003 — App Scaffold (Backend MVP Pipeline)

## Context

STEP 002.7에서 worktree 격리 PASS, STEP 002.6에서 codex .venv + shared infra(Redis/Milvus healthy) PASS가 확인됐다. 환경은 준비됐다.

본 step의 목적은 **풀 서비스 구현이 아니라 backend MVP scaffold + end-to-end mock pipeline**이다. 검증 골든 패스:

> 샘플 raw_event → Redis Stream → worker(consumer) → agent-worker(LangGraph mock) → final_event_card → FastAPI `GET /api/events`로 조회.

본 plan은 기존 `plans/003_APP_SCAFFOLD_PLAN.md`를 사용자 새 요구사항으로 확장한 실행 plan이며, 이전 `repo-sunny-barto.md`(STEP 002.7) 내용은 본 파일에서 대체된다.

## 핵심 결정 (사용자 확정)

| 항목 | 결정 |
|---|---|
| Redis Queue 방식 | **Redis Stream** (XADD/XREADGROUP, consumer group) |
| worker vs agent-worker | **책임 분리** — worker=Stream I/O+ingest, agent-worker=LangGraph 실행 |
| LLM 호출 | **전부 mock** — `OPENAI_API_KEY` 길이/존재만 확인, 실제 호출 0회 |
| Postgres | **placeholder만** — 컨테이너 없음, 향후 추가 |
| Docker network | 기존 `event-intelligence-dev` compose에 backend/worker/agent-worker 추가 → 동일 default network 공유 |
| host에서 패키지 설치 | **수행 안 함** — 기존 venv 사용. Dockerfile 안에서는 `pip install -r requirements/...` (uv 경로 의존 회피) |

## 비범위 (STEP 003에서 하지 않음)

Next.js UI, 실제 crawler/Playwright/Selenium, torch/transformers/Gemma 로컬, KG-RAG 고도화, production deploy, 도메인 연결, pymilvus 2.6.x 업그레이드, LanceDB, Postgres 컨테이너/migration, 실제 OpenAI 호출, Celery (사용 안 함 — Stream worker만).

## 진행 순서 (atomic phase 분해)

### Phase A. Runtime Environment 문서화 (commit 대상 아님)

`CLAUDE.md`와 `AGENTS.md`는 모두 `.gitignore` 처리되어 있음 → 로컬 운영 문서. commit/push 하지 않는 정책 유지.

- `C:\Users\computer\Desktop\business\claude\CLAUDE.md` 최상단에 `## Runtime Environment` 섹션 신규 추가
  - OS: Windows 11 / PowerShell 5.1
  - Path: `C:\Users\computer\Desktop\business\claude`
  - Branch: `main`
  - venv: `.venv` (Python 3.11.9, uv venv)
  - Shared infra: `docker-compose.dev.yml` (event-intelligence-dev compose, default network)
  - Role: **main orchestrator**. PLAN/리뷰/통합 담당. atomic task는 codex worktree에 위임.

- `C:\Users\computer\Desktop\business\codex\AGENTS.md` 최상단에 동일 `## Runtime Environment` 섹션 신규 추가
  - Path: `C:\Users\computer\Desktop\business\codex`
  - Branch: `codex`
  - venv: `.venv` (Python 3.11.9)
  - Shared infra: claude의 `docker-compose.dev.yml` 참조 (`.codex/config.toml` `shared_compose`)
  - Role: **sub-agent execution worktree**. atomic task만 수행. main 직접 merge/push 금지. 완료 후 diff/report 작성 → Claude 검토.

`.gitignore` 추적 상태 재확인만 수행 (commit 시도 금지).

### Phase B. 디렉토리 / 공통 schema 생성

```
backend/
  app/
    __init__.py
    main.py
    core/__init__.py, config.py, logging.py
    api/__init__.py, events.py, themes.py, sectors.py, comments.py, ai_replies.py, admin.py, health.py
    services/__init__.py, event_service.py, comment_service.py, llm_client.py
    db/__init__.py, redis.py, milvus.py, postgres.py
    schemas/__init__.py, events.py, comments.py
    models/README.md
  Dockerfile
  tests/__init__.py, test_health.py

agents/
  __init__.py
  graphs/__init__.py, event_processing_graph.py
  state/__init__.py, event_state.py
  nodes/__init__.py, parse_source.py, deduplicate.py, entity_linking.py,
              sector_mapping.py, retrieve_context.py, impact_analysis.py,
              evidence_check.py, fact_check.py, final_writer.py,
              publish_or_hold.py, normalize_event.py
  Dockerfile
  README.md

workers/
  __init__.py
  queue/__init__.py, producer.py, consumer.py
  pipelines/__init__.py, ingest_pipeline.py, publish_pipeline.py
  Dockerfile
  README.md

tests/  (repo root)
  smoke/test_pipeline.py
```

#### 핵심 schema (Phase 전체에서 재사용)

`backend/app/schemas/events.py`:
- `RawEvent` — source, url, fetched_at, raw_text, raw_metadata
- `NormalizedEvent` — id, source, title, body, occurred_at, language, hash
- `FinalEventCard` — title, summary, theme, sectors[], entities[], impact_path, evidence[], confidence_score (0–1), status ("published"|"hold")

`backend/app/schemas/comments.py`:
- `Comment` — id, event_id, author, body, created_at
- `AIReplyRequest` — event_id, prompt_hint

`agents/state/event_state.py` (`TypedDict` 또는 pydantic):
- raw, normalized, dedupe_key, entities, theme, sectors, past_context, impact, evidence, fact_check, final_card, status

### Phase C. DB / Service / LLM wrapper

| 파일 | 내용 |
|---|---|
| `backend/app/core/config.py` | `pydantic-settings.BaseSettings` — `.env` 8개 키 로드. **값 출력 금지**: `redacted_env_status()` 헬퍼는 길이/존재만 반환 |
| `backend/app/core/logging.py` | stdlib logging configure (JSON 또는 plain). secret 마스킹 필터 |
| `backend/app/db/redis.py` | `get_redis()` (sync + async 둘 다 가능), `ping()`, `xadd(stream, payload)`, `xreadgroup(stream, group, consumer)`, `ensure_group(stream, group)` |
| `backend/app/db/milvus.py` | `connect()`, `ensure_collection(name, dim)` (stub), `insert_embedding()` (stub), `search_similar_events()` (stub) — pymilvus 2.4.4 |
| `backend/app/db/postgres.py` | `# placeholder` + `get_conn()` raise `NotImplementedError("postgres not provisioned in STEP 003")` |
| `backend/app/services/llm_client.py` | `LLMClient(provider="mock")` 기본. `provider="openai"`도 인터페이스만. `complete(prompt, **kw)` → mock은 deterministic 문자열 반환. 실제 호출 0회 |
| `backend/app/services/event_service.py` | in-memory `dict[event_id, FinalEventCard]` 저장소 + `list_events()`, `get_event(id)`, `upsert_card(card)`. 향후 DB 교체 가능하도록 interface |
| `backend/app/services/comment_service.py` | in-memory `list[Comment]` + `add_comment()`, `list_by_event()` |

### Phase D. FastAPI endpoint 12종

`backend/app/main.py`:
- FastAPI app, `lifespan` 안에서 Redis ping → log only, Milvus connect → log only (실패해도 startup은 진행, `/health`에서 상태 노출)
- 라우터: `health`, `events`, `themes`, `sectors`, `comments`, `ai_replies`, `admin`

| Method | Path | 구현 메모 |
|---|---|---|
| GET | `/health` | redis/milvus 상태 dict 반환 |
| GET | `/api/events` | `event_service.list_events()` |
| GET | `/api/events/{event_id}` | 404 처리 |
| GET | `/api/themes` | hardcoded mock theme 목록 |
| GET | `/api/themes/{theme_id}/events` | theme 필터 |
| GET | `/api/sectors` | hardcoded mock sector 목록 |
| GET | `/api/sectors/{sector_id}/events` | sector 필터 |
| POST | `/api/comments` | `comment_service.add_comment()` |
| GET | `/api/events/{event_id}/comments` | `comment_service.list_by_event()` |
| POST | `/api/ai-replies/request` | mock LLM 응답 즉시 반환 (큐잉 없음, STEP 003 단순화) |
| GET | `/api/admin/jobs` | Redis Stream pending/length 등 통계 |

### Phase E. LangGraph EventProcessingGraph

`agents/graphs/event_processing_graph.py`:
- `langgraph.StateGraph(EventState)`
- 노드 11개 (모두 mock — 입력 받아 state 업데이트 후 다음 단계로):
  1. `source_parse` (= `parse_source` + `normalize_event` 통합)
  2. `normalize_event` (raw → normalized)
  3. `deduplicate_event`
  4. `entity_linking`
  5. `theme_sector_mapping` (= `sector_mapping`)
  6. `retrieve_past_context` (= `retrieve_context`)
  7. `impact_analysis`
  8. `evidence_check`
  9. `fact_check`
  10. `final_card_writer` (= `final_writer`)
  11. `publish_or_hold`
- 그래프 컴파일 후 `run(raw_event) -> FinalEventCard` 함수 export
- 모든 mock은 deterministic + 길이/형식만 채움 (의미 있는 NLP는 STEP 004 이후)

### Phase F. Worker / Agent-worker

**worker (`workers/`):**
- `workers/queue/producer.py` — `enqueue_raw_event(raw_event)` → `XADD stream:raw_events`
- `workers/queue/consumer.py` — Stream consumer group 구성. `XREADGROUP group:ingest consumer:worker-1 BLOCK 5000` → ingest_pipeline 호출
- `workers/pipelines/ingest_pipeline.py` — raw_event 검증, 정규화 준비 후 `stream:to_agent` 로 forward
- 실행: `python -m workers.queue.consumer`

**agent-worker (`agents/`):**
- `agents/agent_worker.py` (신규) — `stream:to_agent` 소비 group, raw → `EventProcessingGraph.run()` → 결과 `FinalEventCard`
- `workers/pipelines/publish_pipeline.py` — final_card 받아 backend `event_service.upsert_card()` 호출 — STEP 003에서는 같은 Redis Stream `stream:final_cards`에 publish + backend가 별도 background task로 drain. **단순화**: agent-worker가 backend의 `event_service`를 직접 import해서 호출 (모두 같은 codebase). docker network에서는 backend가 다른 컨테이너이므로 **HTTP `POST /api/admin/upsert-event`** 로 전송하는 방향이 더 클린 — 본 step에서는 후자 채택. admin endpoint는 internal-only로 표시.

**Stream 이름 정리:**
- `stream:raw_events` — producer → worker
- `stream:to_agent` — worker → agent-worker
- (선택) `stream:final_cards` — 관측용 mirror

**선택 이유**: Stream은 consumer group으로 메시지 ack/replay가 명확하다. STEP 003 시점에 List 대비 추가 비용은 consumer group 1줄 init 정도. 향후 DLQ/관측 확장에 유리. → `docs/ARCHITECTURE.md`에 기록.

### Phase G. Docker 확장

`docker-compose.dev.yml`에 3개 서비스 추가:
- `backend` — build: `./backend`, port `8000:8000`, env `REDIS_URL=redis://redis:6379/0`, `MILVUS_HOST=milvus-standalone`, `MILVUS_PORT=19530`, depends_on redis/milvus-standalone (healthy)
- `worker` — build: `./workers`, command: `python -m workers.queue.consumer`, depends_on redis/backend
- `agent-worker` — build: `./agents`, command: `python -m agents.agent_worker`, depends_on redis/backend

각 Dockerfile (모두 `python:3.11-slim` 기반):
- backend: `requirements/base.txt` + `requirements/serve.txt`, copy `backend/`
- worker: `requirements/base.txt` + `requirements/worker.txt`, copy `workers/`, `backend/app/db`, `backend/app/schemas` (필요 모듈만)
- agent-worker: `requirements/base.txt` + `requirements/ai.txt` + `requirements/worker.txt`, copy `agents/`, `backend/app/schemas`, `backend/app/services/llm_client.py`

**대안**: 단일 monorepo image — 모든 코드를 같은 image에 넣고 service별 command만 다르게. STEP 003 단순화 측면에서 **monorepo image 1개 + command 분기**가 더 빠를 수 있음 → 본 plan에서는 service별 Dockerfile로 가되, requirements 레이어 caching을 위해 base requirements 먼저 install.

### Phase H. 문서

| 파일 | 내용 |
|---|---|
| `docs/EVENT_SCHEMA.md` | RawEvent / NormalizedEvent / FinalEventCard 필드 표 + JSON 예시 |
| `docs/API_CONTRACT.md` | 12개 endpoint request/response 예시 |
| `docs/ARCHITECTURE.md` | 컴포넌트 다이어그램(text), Stream 선택 이유, mock 영역 명시 |
| `docs/TRD.md` | 기술 요구사항 정리 (Python 3.11, Redis Stream, Milvus 2.4.10, FastAPI, LangGraph, mock LLM) |
| `plans/003_APP_SCAFFOLD_EXECUTION_REPORT.md` | 최종 실행 보고 (구현/검증/실패&수정/STEP 004 제안) |

### Phase I. 검증 (모두 PowerShell에서)

순차 실행, 실패 시 원인 기록 → 수정 → 재검증.

1. **Import smoke (host venv)**
   - `.\.venv\Scripts\python.exe -c "import backend.app.main"`
   - `.\.venv\Scripts\python.exe -c "import agents.graphs.event_processing_graph"`
   - `.\.venv\Scripts\python.exe -c "import workers.queue.consumer"`
2. **Unit smoke**
   - `.\.venv\Scripts\python.exe -m pytest backend/tests -q`
3. **Compose config**
   - `docker compose -f docker-compose.dev.yml config --quiet`
4. **Build**
   - `docker compose -f docker-compose.dev.yml build backend worker agent-worker`
5. **Up**
   - `docker compose -f docker-compose.dev.yml up -d backend worker agent-worker`
   - `docker compose -f docker-compose.dev.yml ps`
6. **Health**
   - `curl http://localhost:8000/health` (또는 `Invoke-RestMethod`)
7. **End-to-end smoke**
   - `python tests/smoke/test_pipeline.py` — sample raw_event enqueue → 5–10s 대기 → `GET /api/events` 에 final_card 노출 확인
8. **관측**
   - `docker compose logs --tail=50 worker agent-worker backend`

### Phase J. BLOCKED / WARNING 처리

| 시나리오 | 처리 |
|---|---|
| build 실패 (의존성 충돌) | requirements pin 조사 → 보고서에 기록 → 수정 후 재빌드 |
| backend → redis/milvus 연결 실패 | service name(`redis`, `milvus-standalone`) vs container name(`ei-redis`, `ei-milvus`) 차이 확인. compose service name으로 정정 |
| pymilvus pkg_resources warning | 알려진 이슈(STEP 002.6에서 기록). WARNING으로만 보고 |
| stream consumer가 메시지 못 받음 | group 생성 누락 가능. `ensure_group()` 호출 위치 점검 |
| 격리 테스트 파일 잔존 발견 | 자동 삭제 금지. 사용자에게 보고만 |

## 수정·생성 대상 파일 요약

| 경로 | worktree | 작업 | commit 대상 |
|---|---|---|---|
| `CLAUDE.md` | claude | Runtime Environment 섹션 추가 | ❌ (gitignored) |
| `codex/AGENTS.md` | codex | Runtime Environment 섹션 추가 | ❌ (gitignored) |
| `backend/**` | claude | 신규 scaffold | ✅ |
| `agents/**` | claude | 신규 scaffold | ✅ |
| `workers/**` | claude | 신규 scaffold | ✅ |
| `tests/smoke/test_pipeline.py` | claude | 신규 | ✅ |
| `docker-compose.dev.yml` | claude | 3개 서비스 추가 | ✅ |
| `docs/EVENT_SCHEMA.md`, `docs/API_CONTRACT.md`, `docs/ARCHITECTURE.md`, `docs/TRD.md` | claude | 신규 | ✅ |
| `plans/003_APP_SCAFFOLD_EXECUTION_REPORT.md` | claude | 신규 보고서 | ✅ |
| `plans/repo-sunny-barto.md` | claude | 본 plan | ✅ |
| `plans/003_APP_SCAFFOLD_PLAN.md` | claude | 기존 plan은 outdated → header에 "superseded by repo-sunny-barto.md (STEP 003 expanded)" 한 줄 추가 | ✅ |

codex worktree에는 본 step에서 atomic task를 위임하지 않음. 모두 claude worktree에서 진행. codex AGENTS.md만 갱신.

## 절대 금지 (재확인)

- `Remove-Item`, `rm`, `del`, `erase`, `rmdir` (어떤 형태든)
- `git push`, `git reset --hard`, `git clean -fdx`
- `.env` 실값 출력 (길이/존재만)
- 실제 OpenAI/외부 API 호출
- production deploy
- pyproject.toml dependencies 직접 추가 (requirements 분리 정책 유지)
- `__CLAUDE_ONLY_TEST.txt`, `__CODEX_ONLY_TEST.txt` 재생성 또는 임의 삭제 (이미 사용자가 정리함)

## 검증 체크리스트 (보고서에 반영)

- [ ] CLAUDE.md / AGENTS.md에 Runtime Environment 섹션 추가 + gitignored 유지
- [ ] backend/agents/workers 디렉토리 생성 + `__init__.py` 배치
- [ ] schemas (events, comments) + EventState 정의
- [ ] DB wrapper 3종 (redis/milvus/postgres) — redis는 실동작, milvus는 connect까지, postgres는 placeholder
- [ ] llm_client mock-only 동작
- [ ] FastAPI 12개 endpoint 라우팅 (`/health` 포함)
- [ ] LangGraph 11개 노드 + run() 실행 가능
- [ ] worker consumer + agent-worker consumer (stream group 분리)
- [ ] Dockerfile 3종 빌드 성공
- [ ] docker compose config → build → up → ps 모두 PASS
- [ ] `curl /health` 200 + redis/milvus 상태 노출
- [ ] sample raw_event enqueue → final_card published → `GET /api/events`에 반영
- [ ] docs 4종 + execution report 작성
- [ ] PASS / WARNING / BLOCKED / UNKNOWN 명시

## STEP 004 후보 (보고서 말미에 제안)

- 실제 crawler 1종 (RSS 또는 단일 sitemap)
- normalize_event / deduplicate 실제 로직
- Milvus embedding insert/search 실제 호출
- LangSmith tracing 연동
- OpenAI provider 활성화 + 비용 가드
- Postgres 도입 + comment/event 영속화
- 기초 Next.js page 1개 (`/events` 목록 조회)
