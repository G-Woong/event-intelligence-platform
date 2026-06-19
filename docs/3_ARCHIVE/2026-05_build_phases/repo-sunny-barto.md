# STEP 011.5 — 고도화 전 전체 구현 상황 명세서 작성 (문서화 PLAN)

## Context

STEP 003 ~ STEP 011까지 RSS 수집 → raw_events → Redis Stream → worker → agent-worker(LangGraph) → event_cards(Postgres) → Milvus/OpenSearch 색인 → FastAPI → Next.js frontend → admin/reconcile/requeue/reindex/scheduler 스켈레톤이 코드 레벨에서 모두 연결되었고 10개 컨테이너가 동시 healthy 상태다 (`HEAD 38d0028`).

문제: 코드는 흩어져 있고, 어디까지가 real이며 어디부터가 mock/stub인지, 4대 고도화 축(Dense/Graph RAG, 다수 API 수집 확장, 본문 전처리, Agent loop 고도화)이 어떤 파일에 붙는지 한눈에 보이지 않는다. 17개 docs는 STEP별 단편이라 신규 독자(또는 비개발자)가 전체 그림을 읽어내기 어렵다.

이번 STEP은 **새 기능을 0개 추가**한다. 대신 **현재 구현 상황을 빠짐없이 풀어 쓴 명세서 묶음**을 `docs/system_overview/` 아래에 작성한다. 비개발자도 읽고 구조를 이해할 수 있도록 모든 핵심 용어를 "한 줄 설명 + 왜 필요한가 + 비유 + 현재 repo에서의 역할 + 관련 파일 + 부족한 점" 형식으로 풀어 설명한다.

---

## 직접 확인한 현재 상태 (탐색 결과)

### Backend (`backend/app/`)
- `main.py`, `core/config.py`, `core/security.py`, `core/observability.py`, `core/logging.py` — real
- `db/{postgres,redis,milvus,opensearch}.py` — real
- `api/`: `events.py`, `health.py`, `admin.py`, `internal.py` — real / `themes.py`, `sectors.py` — partial(스켈레톤 자료) / `comments.py`, `ai_replies.py` — partial
- `services/`: `event_service.py`, `raw_event_service.py`, `search_service.py`, `vector_index_service.py`, `opensearch_index_service.py`, `reconciler_service.py` — real
- `services/llm_client.py` (line 42에 `MockLLMClient`), `services/embedding_client.py` (line 22에 `MockEmbeddingClient`) — **real path + mock path 양립**
- `alembic/versions/0001~0003_*.py` — 3개 마이그레이션 real
- `entrypoint.sh` — alembic upgrade head → uvicorn

### Worker / Collector (`workers/`, `scripts/`)
- `collectors/rss_collector.py`, `collectors/sources.py`, `collectors/__main__.py` — real (RSS만)
- `queue/producer.py`, `queue/consumer.py` (heartbeat 내장) — real
- `pipelines/ingest_pipeline.py`, `pipelines/publish_pipeline.py` — real
- `scripts/reconcile_stuck_once.py`, `scripts/reindex_opensearch_once.py` — real (외부 cron 트리거 가정)
- **DART/SEC collector**: 부재 (TODO)
- **scheduler 전용 daemon**: 부재 (TODO — 외부 cron/k8s 가정)

### Agents (`agents/`) — LangGraph 11 노드

| # | 노드 | 파일 | 상태 |
|---|---|---|---|
| 1 | source_parse | `nodes/parse_source.py` | real |
| 2 | normalize_event | `nodes/normalize_event.py` | real |
| 3 | deduplicate_event | `nodes/deduplicate.py` | partial (mock 흔적) |
| 4 | entity_linking | `nodes/entity_linking.py` | **mock** |
| 5 | theme_sector_mapping | `nodes/sector_mapping.py` | **mock** |
| 6 | retrieve_past_context | `nodes/retrieve_context.py` | real (Milvus 호출) |
| 7 | impact_analysis | `nodes/impact_analysis.py` | **mock** |
| 8 | evidence_check | `nodes/evidence_check.py` | **mock** |
| 9 | run_fact_check | `nodes/fact_check.py` | **mock** |
| 10 | final_card_writer | `nodes/final_writer.py` | **mock** |
| 11 | publish_or_hold | `nodes/publish_or_hold.py` | real |

→ **real 5 / mock 6** (사용자가 들은 비율과 일치)

- `agent_worker.py`, `graphs/event_processing_graph.py`, `state/event_state.py`, `tools/llm.py`, `tools/vector_search.py` — real
- `agents/prompts/` — **사실상 빈 패키지** (`__init__.py`만, TODO)

### Frontend (`frontend/src/`, Next.js 15.5.18 / React 19 / standalone)
- 11개 라우트(`/`, `/events`, `/events/[id]`, `/themes`, `/themes/[id]`, `/sectors`, `/sectors/[id]`, `/search`, `/admin`) + 4개 API route(`/api/health`, `/api/admin/{reindex,reconcile,requeue/[id]}`)
- `components/{EventCard,EventList,EventFilters,SearchBar,HealthStatus,AdminPanel,EmptyState,ErrorState}.tsx` — real
- `lib/config.ts`, `lib/api/{types,client,server}.ts` — real (`server.ts`는 `import "server-only"` 격리)
- `Dockerfile`: multi-stage node:20-alpine, 비루트 user, `wget /api/health` HEALTHCHECK
- 테스트: `client.test.mjs` 3건 + `proxy.test.mjs` 5건 = 8건 (node --test)

### Docker (`docker-compose.dev.yml`) — 10 서비스
milvus-etcd, milvus-minio, milvus-standalone, redis, postgres, opensearch, backend, worker, agent-worker, frontend. 인프라 서비스는 `127.0.0.1` 바인딩(STEP 011), 사용자 접점(backend 8000 / frontend 3000)은 `0.0.0.0`. worker/agent-worker는 heartbeat file healthcheck.

### Docs (`docs/`) — 17개 `.md`
ARCHITECTURE / API_CONTRACT / TRD / RAG_VECTOR_DESIGN / FRONTEND_DESIGN / DEPLOYMENT / COMPATIBILITY_NOTES / SKELETON_COMPLETION_CHECKLIST / EVENT_SCHEMA / COLLECTOR_DESIGN / SEARCH_DESIGN / OBSERVABILITY / LLM_AGENT_DESIGN / AGENT_WORKFLOW / DATA_POLICY / COMPLIANCE_BOUNDARY / PROMPT_EXPERIMENT_GUIDE. **PRD.md는 없음**.

### Plans (`plans/`)
STEP 000 ~ 011 PLAN/REPORT 페어(000/001 PLAN만, 002.6/002.7 REPORT만, 005.5 REPORT만). 본 PLAN 파일(`repo-sunny-barto.md`) = STEP 011.5 scratch.

### Git
- HEAD: `38d0028` (main, STEP 011 완료 commit)
- working tree: 본 plan 파일만 modified
- worktree: `claude`=`[main]`, `codex`=`[codex] fb3b8a6` clean

---

## 사용자 결정 (확정)

| 항목 | 결정 |
|---|---|
| 산출물 위치 | `docs/system_overview/` 하위 13개 MD 파일 (`00_INDEX.md` + 12개 본문) |
| 톤 | 비개발자도 이해 가능. 모든 핵심 용어는 "한 줄 설명 + 비유 + 왜 필요한가 + repo 내 역할 + 관련 파일 + 부족한 점" 형식 |
| 코드 변경 | **없음** (문서 작성에 필요한 사소한 docs 보정만 허용; 기능 코드 0 변경) |
| 새 기능 | **없음** (DART/SEC, hybrid search, RBAC, shadcn 등 일체 금지) |
| 4대 고도화 축 | A(Dense/Graph/KG-RAG), B(다수 API 수집 확장), C(웹 본문 전처리), D(Agent Framework Loop) — 각 축이 현재 구조 어디에 붙는지 파일 경로 단위로 명시 |
| 검증 | 모든 MD 파일 존재 / 00_INDEX.md에서 상대 링크 / 필수 용어 포함 / mock·stub·TODO 분리 / .env·.venv·node_modules·.next 미커밋 |
| Commit | 문서만 별도 commit (`docs(step-011.5): ...`), git push 금지. codex worktree clean이면 `merge --no-ff`로 sync |

---

## 핵심 설계

### 문서 디렉터리 구조

```
docs/system_overview/
├── 00_INDEX.md                              # 전체 목차 + 읽기 순서 가이드
├── 01_BIG_PICTURE_FOR_NON_DEVELOPERS.md     # 비개발자용 전체 그림 (뉴스룸 비유)
├── 02_GLOSSARY_FULL_TERMS.md                # 핵심 용어 사전 (60+ 항목)
├── 03_END_TO_END_DATA_FLOW.md               # RSS → Next.js까지 데이터 흐름
├── 04_BACKEND_API_AND_DATABASE.md           # FastAPI + Postgres + Alembic + 스키마
├── 05_COLLECTOR_QUEUE_WORKER_AGENT.md       # RSS collector + Redis Stream + worker/agent-worker
├── 06_LLM_RAG_SEARCH_PIPELINE.md            # LLMClient + LangGraph + Milvus + OpenSearch
├── 07_FRONTEND_AND_ADMIN_UI.md              # Next.js App Router + admin proxy + token 격리
├── 08_DOCKER_INFRA_AND_ENV.md               # 10개 서비스 + healthcheck + .env
├── 09_CURRENT_IMPLEMENTATION_STATUS.md      # 컴포넌트별 real/partial/mock/stub/TODO 표
├── 10_STUB_MOCK_TODO_MAP.md                 # mock 6노드 + Mock 클라이언트 + DART/SEC 부재 등
├── 11_NEXT_ENHANCEMENT_ROADMAP.md           # 4대 고도화 축이 현재 어디에 붙는지
└── 12_FILE_MAP_FOR_MAINTENANCE.md           # 파일 경로 인덱스 (역할별·기능별)
```

### 각 문서 작성 가이드

#### `00_INDEX.md`
- 모든 12개 문서로의 상대 링크
- 비개발자: `01 → 02 → 03 → 09 → 11` 순서 권장
- 개발자: `03 → 04~08 → 09 → 10 → 11 → 12` 순서 권장
- 마지막 갱신일(2026-05-24), 기준 commit hash(38d0028 + 본 STEP 011.5 commit)

#### `01_BIG_PICTURE_FOR_NON_DEVELOPERS.md`
- "전세계 뉴스/공시를 수집해 사람이 읽기 좋은 사건 카드로 가공하는 뉴스룸 비유"
- 7단계 흐름 그림 텍스트로 표현
- "투자 조언이 아니라 정보 제공"(CLAUDE.md 원칙) 강조
- 어떤 화면을 사용자가 보게 되는지 5개 페이지 스크린샷 대신 텍스트 설명

#### `02_GLOSSARY_FULL_TERMS.md`
사용자 요구한 60+ 용어를 카테고리별로 분류. 각 항목 형식:

```
## <용어>
**한 줄 설명**: ...
**왜 필요한가**: ...
**비유**: ...
**현재 repo에서의 역할**: ...
**관련 파일**: ...
**아직 부족한 점**: ...
```

카테고리: 서비스/제품 · 백엔드 · 큐/작업처리 · AI/Agent · RAG/Search · Frontend · Infra · 보안/운영. 사용자 명시 용어 전부 포함.

#### `03_END_TO_END_DATA_FLOW.md`
- 8단계 흐름표 (단계 / 입력 / 처리 주체 / 출력 / 저장소 / 관련 파일)
- "RSS feed XML → feedparser → raw_events PG row → Redis Stream message → consumer.py → ingest_pipeline.normalize → agent_worker.py → LangGraph 11 노드 → FinalEventCard JSON → publish_pipeline → event_cards PG row + Milvus vector + OpenSearch doc → FastAPI /api/events → Next.js page"
- 각 단계마다 데이터 모양 예시 1개씩

#### `04_BACKEND_API_AND_DATABASE.md`
- FastAPI 구조 (router → service → db 계층)
- 모든 router 파일 + 각 endpoint 표
- Postgres 스키마(`raw_events`, `event_cards`, `comments` 등) — `EVENT_SCHEMA.md` 참조
- Alembic 마이그레이션 3건 요약
- CORS / X-Admin-Token / healthcheck 정책

#### `05_COLLECTOR_QUEUE_WORKER_AGENT.md`
- RSS collector 동작(`feedparser` + `content_hash` 중복 제거)
- Redis Stream 개념(producer / consumer / consumer group / XADD / XREADGROUP / ack / PEL)
- worker(`consumer.py`) → ingest_pipeline → agent_worker(`agent_worker.py`) 분리 이유
- heartbeat file healthcheck 동작
- reconciler / scheduler(외부 cron) 구조

#### `06_LLM_RAG_SEARCH_PIPELINE.md`
- LLMClient 추상화 + MockLLMClient / OpenAIClient 분리
- EmbeddingClient / Mock 동일
- LangGraph 11 노드 도식 + real/mock 표
- Milvus(벡터 색인) vs OpenSearch(키워드 색인) 차이와 왜 둘 다 필요한가
- `try_index_card` swallow 정책
- 현재 검색은 OpenSearch keyword only, hybrid는 STEP 012 예정

#### `07_FRONTEND_AND_ADMIN_UI.md`
- Next.js App Router / server component vs client component
- 11개 라우트 표
- Route Handler proxy의 보안 의미(`X-Admin-Token` 서버 측 주입, `server-only`)
- HealthStatus 구조(STEP 011 components 중첩 + flat fallback)

#### `08_DOCKER_INFRA_AND_ENV.md`
- 10개 서비스 표(image / port / healthcheck / depends_on / volume)
- 127.0.0.1 바인딩 의미와 사용자 접점 예외(backend/frontend)
- `.env.example` 키 전체 그룹별 정리 (실값 절대 미포함)
- 컨테이너 재기동 절차 요약(DEPLOYMENT.md 참조)

#### `09_CURRENT_IMPLEMENTATION_STATUS.md`
- 13단계 흐름표(`SKELETON_COMPLETION_CHECKLIST.md`를 참고하되 더 상세)
- 각 단계: 상태(DONE / PARTIAL / TODO) + mock/real + 관련 파일 + 테스트 개수
- LangGraph 11 노드 real/mock 표
- 컨테이너 10개 healthcheck 상태
- 회귀 테스트 현황(130 pytest + 8 node --test PASS)

#### `10_STUB_MOCK_TODO_MAP.md`
mock/stub/TODO를 한 곳에 집계:

| 위치 | 분류 | 왜 mock인가 | 교체 조건 / 시점 |
|---|---|---|---|
| `backend/app/services/llm_client.py:MockLLMClient` | mock | 외부 API 비용 회피 / 결정론적 테스트 | `LLM_PROVIDER=openai` env |
| `backend/app/services/embedding_client.py:MockEmbeddingClient` | mock | 동일 | `EMBEDDING_PROVIDER=openai` env |
| `agents/nodes/entity_linking.py` | mock | 도메인 모델 부재 | STEP 013 NER 도입 |
| `agents/nodes/sector_mapping.py` | mock | 동일 | STEP 013 분류기 |
| `agents/nodes/impact_analysis.py` | mock | LLM 프롬프트 미완 | STEP 014 |
| `agents/nodes/evidence_check.py` | mock | 외부 fact-check 미통합 | STEP 014 |
| `agents/nodes/fact_check.py` | mock | 동일 | STEP 014 |
| `agents/nodes/final_writer.py` | mock | 프롬프트 미완 | STEP 014 |
| `agents/nodes/deduplicate.py` | partial | 벡터 유사도 기준 미정 | STEP 012 |
| `agents/prompts/` | empty | 프롬프트 자산 미수립 | STEP 014 |
| `workers/collectors/` (RSS만) | partial | DART/SEC 미구현 | STEP 013 |
| scheduler daemon | TODO | 외부 cron 가정 | STEP 015 운영 진입 시 |
| Admin auth | bypass | dev 모드 (token 빈값 허용) | STEP 015 RBAC |
| LangGraph node 3 (deduplicate) | partial | 동일 | STEP 012 |

#### `11_NEXT_ENHANCEMENT_ROADMAP.md`
사용자 4대 고도화 축 → 현재 파일 매핑:

- **축 A — Dense/Graph/KG-RAG**: 현재 `agents/tools/vector_search.py`가 Milvus 단순 top-k. Dense RAG 강화는 (1) `embedding_client.py` 실모델 교체, (2) `nodes/retrieve_context.py` rerank 추가. Graph/KG-RAG는 신규 `graph_store/` 모듈 필요(entity → relation → event 시간축). 과거 사건 연결은 `event_cards.created_at` + entity overlap 기반.
- **축 B — 다수 API 수집 확장**: 입구는 `workers/collectors/`. RSS(`rss_collector.py`)와 동일 모양으로 DART(공시), SEC EDGAR, 정부 OpenAPI, 소셜 API collector 추가. 공통 출구는 `raw_events` 테이블 + Redis Stream `raw_events_stream` — 이미 추상화되어 있어 신규 collector는 producer 호출만 하면 됨.
- **축 C — 웹 본문 전처리**: 현재 RSS summary 텍스트만 사용. 실제 본문 추출은 `workers/pipelines/ingest_pipeline.py`에 `trafilatura` / `readability-lxml` 단계 삽입. 저장 위치는 `raw_events.body_text`(신규 컬럼) 또는 별도 `raw_event_bodies` 테이블. 저작권 경계는 `docs/DATA_POLICY.md` 정책 준수.
- **축 D — Agent Framework Loop**: 현재 LangGraph는 선형 11 노드. 고도화는 (1) `graphs/event_processing_graph.py`를 sub-graph 분해(수집 / 정제 / 검증 / 검색 / 작성 agent), (2) 실패 재처리 loop(`reconciler_service.py` 패턴을 graph 내부에 흡수), (3) LangSmith trace로 노드별 실패 카탈로그. `tools/` 디렉터리에 검색·외부 API 호출 도구 추가.

각 축마다 "지금 어디까지 / 다음 1단계 / 다음 3단계" 명시.

#### `12_FILE_MAP_FOR_MAINTENANCE.md`
- 역할별 파일 인덱스(데이터 수집 / 큐 / 에이전트 / DB / API / Frontend / Infra / 운영 스크립트 / 테스트 / 문서)
- 파일 경로 → 한 줄 요약 → 관련 STEP
- 신규 기여자가 "어디를 고치면 X가 바뀌는가" 즉답 가능하도록

### 검증 체크리스트

#### 문서 존재 & 링크
- [ ] 13개 MD 파일 모두 생성됨
- [ ] `00_INDEX.md`에서 12개 본문 파일로 상대 링크 작동
- [ ] 각 본문 파일에서 관련 docs(`../ARCHITECTURE.md` 등)로 링크 작동

#### 내용 빠짐
- [ ] 사용자 명시 60+ 핵심 용어 모두 glossary 포함 (Redis Stream, Milvus, OpenSearch, Docker, FastAPI, Next.js, LangGraph, worker, agent-worker, reconciler, scheduler, raw_event, event_card, embedding, index, vector search, keyword search, hybrid search, KG-RAG, RAG, Dense RAG, CORS, environment variable, healthcheck, Admin auth, RBAC, OAuth, UI/UX 등 전부)
- [ ] 13단계 흐름이 `03_END_TO_END_DATA_FLOW.md`와 `09_CURRENT_IMPLEMENTATION_STATUS.md`에 빠짐없이 표현
- [ ] LangGraph 11 노드 real/mock 표가 `06_..._PIPELINE.md`, `09_...STATUS.md`, `10_...TODO_MAP.md`에 모두 일관되게 등장
- [ ] 4대 고도화 축 4개가 `11_NEXT_ENHANCEMENT_ROADMAP.md`에 모두 등장
- [ ] 비개발자 비유가 `01_BIG_PICTURE_FOR_NON_DEVELOPERS.md`와 `02_GLOSSARY_FULL_TERMS.md`에 포함

#### 사실성
- [ ] 추측 0건 — 모든 파일 경로/노드 이름/서비스 이름은 실제 repo에서 확인된 것만
- [ ] mock/stub/TODO 분리 명확 (real 항목을 mock으로 잘못 적지 않음, 그 반대도)
- [ ] STEP 000 ~ 011 진행 이력과 일치 (`SKELETON_COMPLETION_CHECKLIST.md` 기준)

#### 보안 & policy
- [ ] `.env` 실값 / OPENAI_API_KEY / LANGSMITH_API_KEY / ADMIN_API_TOKEN 실값 0건
- [ ] `git diff --stat`에 node_modules / .next / .venv / volume / data 디렉터리 0건
- [ ] 기능 코드 변경 0건 (`git diff` 결과는 `docs/system_overview/` + `plans/repo-sunny-barto.md` + commit log 한정)

#### Commit
- [ ] Commit 1건: `docs(step-011.5): add full system implementation overview for enhancement planning`
- [ ] `git push` 미실행
- [ ] codex sync는 main commit 후 worktree clean이면 `merge --no-ff`

---

## 신규 / 수정 파일

### 신규 (13개 문서)
| 경로 | 목적 |
|---|---|
| `docs/system_overview/00_INDEX.md` | 전체 문서 목차 + 읽기 순서 |
| `docs/system_overview/01_BIG_PICTURE_FOR_NON_DEVELOPERS.md` | 비개발자용 전체 그림 |
| `docs/system_overview/02_GLOSSARY_FULL_TERMS.md` | 핵심 용어 사전 (60+) |
| `docs/system_overview/03_END_TO_END_DATA_FLOW.md` | RSS → Next.js 데이터 흐름 |
| `docs/system_overview/04_BACKEND_API_AND_DATABASE.md` | FastAPI + Postgres + Alembic |
| `docs/system_overview/05_COLLECTOR_QUEUE_WORKER_AGENT.md` | 수집/큐/워커/에이전트 분리 구조 |
| `docs/system_overview/06_LLM_RAG_SEARCH_PIPELINE.md` | LLM + LangGraph + Milvus + OpenSearch |
| `docs/system_overview/07_FRONTEND_AND_ADMIN_UI.md` | Next.js + admin proxy + token 격리 |
| `docs/system_overview/08_DOCKER_INFRA_AND_ENV.md` | 10개 서비스 + healthcheck + env |
| `docs/system_overview/09_CURRENT_IMPLEMENTATION_STATUS.md` | 컴포넌트별 real/partial/mock/stub/TODO |
| `docs/system_overview/10_STUB_MOCK_TODO_MAP.md` | mock 6노드 + Mock 클라이언트 등 집계 |
| `docs/system_overview/11_NEXT_ENHANCEMENT_ROADMAP.md` | 4대 고도화 축 ↔ 현재 파일 매핑 |
| `docs/system_overview/12_FILE_MAP_FOR_MAINTENANCE.md` | 역할별 파일 인덱스 |

### 수정 (있다면 최소)
| 경로 | 변경 |
|---|---|
| `docs/SKELETON_COMPLETION_CHECKLIST.md` (선택) | "전체 명세서 위치: `docs/system_overview/00_INDEX.md`" 한 줄 추가 |
| `plans/repo-sunny-barto.md` | 본 PLAN (이미 갱신 중) |

**기능 코드 변경: 0건.**

---

## 비범위 (절대 하지 않음)

- DART/SEC collector 코드 추가
- Hybrid search / KG-RAG / Dense RAG 코드 작업
- 본문 전처리(trafilatura 등) 코드 추가
- LangGraph mock 6 노드 → 실모델 교체
- RBAC / OAuth / 로그인
- shadcn/ui / 디자인 시스템 / i18n
- Playwright e2e
- Production deploy / TLS / CDN
- Dockerfile 변경
- backend/frontend 기능 refactor
- `agents/prompts/` 자산 신규 작성

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실값, `ADMIN_API_TOKEN` / `OPENAI_API_KEY` / `LANGSMITH_API_KEY` 실값 출력/커밋
- `NEXT_PUBLIC_ADMIN_*` 변수 신규 정의
- `npm audit fix --force`
- node_modules / .next / build / volume / .venv / data 커밋
- codex worktree 파일 직접 수정
- 추측으로 문서 채우기 — 모르면 `UNKNOWN`/`TODO`로 표기

---

## 실행 순서

### Phase 0 — Pre-flight
- `git status` clean 재확인 (plan 파일만 modified)
- `git log --oneline -5` HEAD `38d0028` 확인
- `docs/system_overview/` 디렉터리 생성 가능 위치인지 확인

### Phase 1 — Foundation 3개 문서
1. `00_INDEX.md` 작성 (전체 목차, 읽기 순서)
2. `01_BIG_PICTURE_FOR_NON_DEVELOPERS.md` 작성
3. `02_GLOSSARY_FULL_TERMS.md` 작성 (60+ 용어, 카테고리별)

### Phase 2 — Flow 3개 문서
4. `03_END_TO_END_DATA_FLOW.md` 작성
5. `04_BACKEND_API_AND_DATABASE.md` 작성
6. `05_COLLECTOR_QUEUE_WORKER_AGENT.md` 작성

### Phase 3 — AI/UI/Infra 3개 문서
7. `06_LLM_RAG_SEARCH_PIPELINE.md` 작성
8. `07_FRONTEND_AND_ADMIN_UI.md` 작성
9. `08_DOCKER_INFRA_AND_ENV.md` 작성

### Phase 4 — Status & Roadmap 4개 문서
10. `09_CURRENT_IMPLEMENTATION_STATUS.md` 작성
11. `10_STUB_MOCK_TODO_MAP.md` 작성
12. `11_NEXT_ENHANCEMENT_ROADMAP.md` 작성
13. `12_FILE_MAP_FOR_MAINTENANCE.md` 작성

### Phase 5 — 검증
1. 13개 파일 `Glob` 으로 존재 확인
2. `00_INDEX.md`의 모든 상대 링크가 실제 파일 경로와 일치하는지 `Grep`으로 확인
3. 필수 용어가 `02_GLOSSARY_FULL_TERMS.md`에 모두 등장하는지 grep
4. LangGraph 11 노드 표가 `06`, `09`, `10`에 모두 일관되게 등장하는지 확인
5. 4대 고도화 축이 `11`에 모두 등장하는지 확인
6. `git diff --stat`로 기능 코드 변경 0건 재확인

### Phase 6 — Commit
1. `git add docs/system_overview/ plans/repo-sunny-barto.md` (선택적으로 `docs/SKELETON_COMPLETION_CHECKLIST.md`)
2. Commit 1건: `docs(step-011.5): add full system implementation overview for enhancement planning`
3. `git status` clean 확인
4. `git log --oneline -3` 확인

### Phase 7 — Codex sync
1. `git -C C:/Users/computer/Desktop/business/codex status --short` clean 확인
2. clean이면 main을 codex로 `merge --no-ff` (sync only)
3. 충돌 시 자동 해결 금지, 보고

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | 13개 문서 작성 중 일부 노드/파일 경로 오기재 | 중간 | 문서 작성 시 Grep으로 파일 존재 즉시 검증, 추측 금지 |
| R2 | glossary 60+ 항목 누락 | 낮음 | Phase 5 검증 단계에서 사용자 명시 용어 리스트와 1:1 대조 |
| R3 | 4대 고도화 축 설명이 코드 위치와 어긋남 | 중간 | `tools/vector_search.py`, `nodes/retrieve_context.py`, `workers/collectors/`, `workers/pipelines/ingest_pipeline.py` 실제 코드 한 번 더 읽고 매핑 확정 |
| R4 | 문서가 너무 길어져서 가독성 저하 | 낮음 | 12개로 분리, 각 파일은 핵심 표 + 짧은 본문 위주 |
| R5 | docs/SKELETON_COMPLETION_CHECKLIST.md 와 09 문서 내용 중복 | 낮음 | 09는 더 상세, CHECKLIST는 한눈 요약 — 한 줄 cross-link만 추가 |
| U1 | 비개발자에게 어디까지 풀어 써야 하는지 기준 | — | "비유 1개 + 한 줄 정의 + repo 역할" 최소 셋트 강제 |
| U2 | `agents/prompts/` 빈 패키지를 mock인지 stub인지 미정 | — | `10_STUB_MOCK_TODO_MAP.md`에 "empty package — STEP 014에서 자산화" 명시 |
| U3 | DART/SEC collector 위치를 `workers/collectors/dart_collector.py` 같이 추정해도 되는가 | — | "현재 부재 — 신규 추가 시 RSS와 동일 폴더 권장" 으로 prescriptive하게 명시 |

---

## 최종 보고 형식

작업 완료 후 한국어로 다음 10개 항목 보고:

1. 어떤 파일을 읽고 현재 상태를 확인했는가
2. 생성한 문서 목록 (13개)
3. 각 문서의 목적 한 줄씩
4. 필수 용어 60+ glossary 포함 여부
5. 전체 skeleton 흐름(13단계) 설명 포함 여부
6. mock/stub/TODO 분리 여부
7. 사용자의 4대 고도화 축과 현재 구조 연결 여부 (축별 매핑 파일 경로)
8. 검증 체크리스트 결과 (Phase 5 모든 항목)
9. WARNING / BLOCKED / UNKNOWN
10. commit hash + codex sync 여부
