# STEP 004.5 — Skeleton Integration Audit: 실행 보고서

실행일: 2026-05-23

## ① 무엇을 했는가

### Phase A — Health 표현 통일
- `backend/app/api/health.py:17`: `"disconnected"` → `"error"` (1줄 수정)
- `docs/API_CONTRACT.md`: `/health` 응답 스키마 표 추가, 모든 필드 `"ok"|"error"` 통일 명시

### Phase B — AI Reply endpoint 일관성
- `backend/app/api/ai_replies.py:12`: `def` → `async def`, `response_model=dict` 추가
- 기존 동작 보존: mock provider, 응답 body 동일

### Phase C — Codex worktree 동기화
- `C:\Users\computer\Desktop\business\codex`에서 `git merge main --no-edit` 실행
- 결과: `ort` 전략, 충돌 없음, 70개 파일 동기화 (STEP 003 전체 포함)
- codex 고유 변경 (`.gitignore`의 `pyproject.toml` 제외) 보존됨
- 비고: STEP 004 Postgres 변경은 main에 미커밋 상태 → 다음 commit 후 재sync 필요

### Phase D — 문서 갱신
- `docs/ARCHITECTURE.md`: 헤더 STEP 004.5 갱신, skeleton 현황 표(PASS/STUB/MISSING), 다음 STEP 순서 추가
- `docs/TRD.md`: 헤더 STEP 004.5 갱신
- `docs/COMPATIBILITY_NOTES.md`: W4–W7 기록 추가, codex 동기화 시점 기록
- `plans/004_5_SKELETON_INTEGRATION_AUDIT.md`: 신규 (plan 영구 사본)
- `plans/004_5_SKELETON_INTEGRATION_REPORT.md`: 신규 (본 파일)

## ② 무엇을 검증했는가

| 항목 | 결과 | 비고 |
|---|---|---|
| health.py milvus "error" 통일 | PASS | 코드 수정 완료 (컨테이너 재빌드 시 반영) |
| ai_replies.py async def 전환 | PASS | 코드 수정 완료, mock 동작 유지 확인 |
| codex worktree STEP 003 동기화 | PASS | git merge 충돌 없이 완료 |
| docker compose ps 7/7 | PASS | backend/milvus/etcd/minio/postgres/redis healthy, worker/agent-worker up |
| /health 응답 4필드 | PASS | `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}` |
| ai-replies POST mock | PASS | `{"event_id":"test-uuid","reply":"[mock] response for prompt length=40"}` |
| backend unit 6/6 | PASS | `pytest backend/tests -q` → 6 passed in 1.21s |
| smoke/test_pipeline.py | PASS | 2 passed in 34.96s |
| smoke/test_persistence.py | PASS | 2 passed (위 포함) |
| docs 4종 갱신 | PASS | ARCHITECTURE / TRD / API_CONTRACT / COMPATIBILITY_NOTES |
| plan 사본 + report | PASS | plans/ 디렉터리에 신규 2개 파일 |

## ③ WARNING / BLOCKED / UNKNOWN / STUB / MISSING

### WARNING
- **W4** (문서 기록): `milvus.py:29-30` `_connected` 플래그 stale 가능 → STEP 006 시 ping 기반 교체
- **W5** (문서 기록): `themes.py`, `sectors.py` 정적 상수 — 의도된 skeleton, 변경 대상 아님
- **W6** (문서 기록): `worker`/`agent-worker` healthcheck 미정의 — 다음 minor STEP 후보
- **W7** (문서 기록): `ai.txt`의 `llama-index-vector-stores-lancedb` 분류 일관성 — 기능 영향 없음
- **STEP 004 Postgres 변경 미커밋**: 현재 main HEAD=`7704d17`(STEP 003). STEP 004 변경은 working dir에만 존재. codex 재sync는 commit 후 필요.

### BLOCKED
- 없음.

### UNKNOWN
- 없음.

### STUB (의도된 미구현)
- LangGraph 노드 8/11 mock 하드코딩 (`entity_linking.py` 등)
- `LLMClient` — `backend/app/services/llm_client.py` 존재, agent 노드에서 미사용
- Milvus `insert_embedding` / `search_similar_events` — stub (no-op)
- themes/sectors 정적 상수 (service layer 없음)

### MISSING (자리 없음)
- `workers/collectors/` crawler 코드 — STEP 007 후보
- OpenSearch — 먼 STEP
- `frontend/` Next.js — 먼 STEP

## 다음 STEP 권장 순서

| 순번 | STEP | 핵심 작업 |
|---|---|---|
| 1 | STEP 005 | LLMClient → agent 노드 wire-up (mock 유지, 노드 1-2개) |
| 2 | STEP 006 | Milvus insert/search 실호출 (`retrieve_past_context`/`deduplicate`) |
| 3 | STEP 007 | RSS crawler 1종 (`raw_events` 테이블 도입) |
| 4 | STEP 008 | OpenAI provider 활성화 (비용 가드) |
| 5 | STEP 009 | Next.js `/events` 목록 UI (read-only) |

근거: 데이터가 들어오기 전에 처리 경로 신뢰도를 먼저 올린다. crawler 먼저 투입하면 mock 노드를 거친 잘못된 카드가 DB에 쌓인다.
