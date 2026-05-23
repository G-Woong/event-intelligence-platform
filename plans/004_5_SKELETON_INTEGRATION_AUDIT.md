# STEP 004.5 — Skeleton Integration Audit

## Context

STEP 004(Postgres Persistence)까지 완료된 시점에서, 본 STEP의 목적은 **새 기능 추가가 아니라 감사(Audit)** 다. 현재 repo가 이후 테스트 주도 확장(crawler → real LLM → Milvus retrieval → OpenSearch → frontend)을 위한 "최소한이지만 서로 연결되어 살아 움직이는 skeleton" 상태인지 8개 축으로 점검하고, 발견된 표현 충돌·인터페이스 누락·문서 불일치만 최소 수정한다.

핵심 질문 (한 줄): "현재 repo는 이후 확장을 위한 skeleton integration 상태로 충분한가?"

## 감사 결과 요약 (사전 조사 완료)

세 개 병렬 Explore 에이전트로 8개 축을 점검했고, 다음 사실들을 직접 확인했다.

### PASS (이미 연결됨)

| 축 | 항목 | 근거 |
|---|---|---|
| A | FastAPI 8개 endpoint 중 6개가 async + Depends(get_session) + service layer 경유 | `backend/app/api/events.py:13,18`, `comments.py:13`, `admin.py:38` 등 |
| B | Postgres lazy init, ORM↔Pydantic↔Alembic 3-way 컬럼 매핑 일치 | `postgres.py:15-32`, `models/event.py:14-34`, `alembic/versions/0001_initial.py:22-67` |
| B | upsert_card on_conflict_do_update + UUID fallback + tz-aware 변환 | `services/event_service.py:18-39,75-95` |
| B | in-memory dict/list 잔존 0건 (themes/sectors 정적 상수만 의도적 잔존) | `services/event_service.py`, `comment_service.py` |
| D | Redis Stream 파이프라인 end-to-end 연결 (raw→worker→agent-worker→backend) | `workers/queue/producer.py:11-20`, `workers/pipelines/ingest_pipeline.py:13-34`, `agents/agent_worker.py:18-39`, `workers/pipelines/publish_pipeline.py:12-24` |
| E | LangGraph StateGraph 컴파일 + 11개 노드 wiring + EventState/FinalEventCard 정의 | `agents/graphs/event_processing_graph.py:20-49,52-71`, `agents/state/event_state.py:9-22` |
| G | claude/codex worktree 격리 + 역할 분리 명문화 | `git worktree list`, `CLAUDE.md:10`, `codex/AGENTS.md:10` |
| H | 9개 requirements 파일 레이어 분리 깨끗 (serve/worker/ai/vector/ml/crawler/dev/graph_optional + base) | `requirements/*.txt` |
| I | 7개 컨테이너 모두 healthy. backend `depends_on: service_healthy` 정상. 컨테이너 내부 호스트명(postgres/redis/milvus-standalone) 사용 | `docker-compose.dev.yml:117,114,115,120-126` |
| I | 볼륨 영속화 (pg_data, etcd/minio/milvus/redis_data) 선언 | `docker-compose.dev.yml:167-172` |

라이브 검증: `curl http://localhost:8000/health` → `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}` 정상.

### WARNING (표현 충돌 / 누락)

| # | 위치 | 내용 | 수정 여부 |
|---|---|---|---|
| W1 | `backend/app/api/health.py:17` | milvus만 `"disconnected"` 사용, redis/postgres는 `"error"` — 표현 충돌 | **수정** (ok/error로 통일) |
| W2 | `docs/API_CONTRACT.md:13-21` | postgres `ok\|error`만 명시, milvus 부정 값 미기재 | **수정** (통일된 표현 반영) |
| W3 | `backend/app/api/ai_replies.py:12` | sync `def` + `response_model` 미설정 — 다른 endpoint와 비일관 | **수정** (async def + response_model=dict) |
| W4 | `backend/app/db/milvus.py:29-30` | `_connected` 모듈 플래그 → 런타임 stale 가능 | **문서 기록만** (COMPATIBILITY_NOTES) |
| W5 | `backend/app/api/themes.py:12-18`, `sectors.py:12-18` | 정적 `_THEMES`/`_SECTORS` 리스트 — 의도된 skeleton이지만 service layer 부재 | **문서 기록만** (ARCHITECTURE) |
| W6 | `docker-compose.dev.yml:134-165` | worker / agent-worker 서비스 healthcheck 미정의 | **문서 기록만** (다음 STEP 후보) |
| W7 | `requirements/ai.txt:30` | `llama-index-vector-stores-lancedb`가 ai.txt에 있음 — graph_optional.txt가 더 일관 | **문서 기록만** (분류 일관성 메모) |

### MISSING / STUB (확장 자리)

| 항목 | 현재 상태 | 처리 |
|---|---|---|
| crawler collector 코드 | 없음 (`requirements/crawler.txt`만 pin) | 문서에 TODO 명시 |
| LLMClient | `backend/app/services/llm_client.py:7-18` 존재하지만 agent 노드에서 미사용 | 문서에 "STEP 005에서 agent 노드에 import" 명시 |
| Milvus insert/search | `backend/app/db/milvus.py:33-42` 빈 stub | 문서 명시 (이미 stub임을 분명히) |
| OpenSearch | 코드/문서에 자리 없음 | docs/ARCHITECTURE.md에 명시적 TODO 추가 |
| frontend | `frontend/` 디렉터리 없음 | docs/ARCHITECTURE.md에 명시적 TODO 추가 |
| LangGraph 노드 8/11이 mock 하드코딩 | `entity_linking.py:8` 등 | 의도된 skeleton, 문서 기록 |
| codex worktree STEP 003/004 미동기화 | codex=e21ee3d (STEP 002.5에서 정지) | **이번 audit에서 동기화** |

### BLOCKED / UNKNOWN

- 없음.

## Phase 목록 (최소 수정 + 동기화 + 문서)

### Phase A — Health 표현 통일 (코드)
- `backend/app/api/health.py:17`: `"disconnected"` → `"error"` (1줄)
- `docs/API_CONTRACT.md:13-21`: 응답 예시 + `redis`/`milvus` 값 명세 `"ok"|"error"`로 통일

### Phase B — AI Reply endpoint 일관성 (코드)
- `backend/app/api/ai_replies.py:11-14`: `def` → `async def`, `response_model=dict` 명시

### Phase C — Codex worktree 동기화
- `C:\Users\computer\Desktop\business\codex`에서 `git merge main`
- 순서: `git merge main --no-edit`
- 충돌 시 BLOCKED 처리

### Phase D — 문서 갱신
- `docs/ARCHITECTURE.md`: skeleton 현황 표 + frontend / OpenSearch / crawler / LLMClient wire-up TODO
- `docs/TRD.md`: 헤더 STEP 004.5 갱신
- `docs/COMPATIBILITY_NOTES.md`: W4~W7 + codex 동기화 기록
- `plans/004_5_SKELETON_INTEGRATION_AUDIT.md`: 신규 (본 plan 영구 사본)
- `plans/004_5_SKELETON_INTEGRATION_REPORT.md`: 신규 (최종 실행 보고)

### Phase E — 검증
1. `docker compose -f docker-compose.dev.yml ps` → 7개 컨테이너 healthy/up 유지
2. `curl http://localhost:8000/health` → `{status:ok, redis:ok, milvus:ok, postgres:ok}`
3. AI-replies POST mock 동작 확인
4. `pytest backend/tests -q` → 6/6 PASS
5. smoke/test_pipeline.py, smoke/test_persistence.py PASS

## 비범위

- 실제 crawler 코드 구현 (STEP 005 후보)
- LLMClient를 agent 노드에 wire-up (STEP 005 후보)
- Milvus insert/search 실구현 (STEP 006 후보)
- OpenSearch 도입 (먼 STEP)
- Next.js frontend full build (먼 STEP)
- worker/agent-worker healthcheck 보강 (다음 minor STEP)
- LangGraph 노드 8개 mock → 실구현 전환 (STEP 005-006)
- pymilvus 2.6 업그레이드
- 성능 튜닝, auth, user system

## 수정·생성 대상 파일 요약

| 경로 | 작업 | 종류 |
|---|---|---|
| `backend/app/api/health.py` | milvus disconnected → error (1줄) | 코드 |
| `backend/app/api/ai_replies.py` | def → async def + response_model | 코드 |
| `docs/API_CONTRACT.md` | /health 응답 스키마 통일 | 문서 |
| `docs/ARCHITECTURE.md` | skeleton 현황 + frontend/OpenSearch/crawler TODO | 문서 |
| `docs/TRD.md` | 헤더 STEP 004.5 갱신 | 문서 |
| `docs/COMPATIBILITY_NOTES.md` | W4~W7 + codex 동기화 기록 | 문서 |
| `plans/004_5_SKELETON_INTEGRATION_AUDIT.md` | 신규 (본 plan 영구 사본) | 문서 |
| `plans/004_5_SKELETON_INTEGRATION_REPORT.md` | 신규 (실행 보고) | 문서 |
| codex worktree | main의 STEP 003 변경 동기화 (git merge) | 동기화 |

## 다음 STEP 순서 제안

1. STEP 005 — LLMClient를 agent 노드에 wire-up
2. STEP 006 — Milvus insert/search 실호출
3. STEP 007 — 첫 번째 실제 crawler (RSS 1종)
4. STEP 008 — OpenAI provider 활성화
5. STEP 009 — Next.js `/events` 목록 UI
