# STEP 008B — Pipeline Reliability Hardening Skeleton

## Context

STEP 008A에서 raw_event linkage + status lifecycle + LangSmith skeleton이 들어왔지만, 운영 안정성 측면에서 다음 결함이 남아 있다:

- **Docker migration 누락 위험**: stale build cache (`COPY backend/ backend/` 레이어 캐시 재사용)가 원인. 신규 revision 추가 시 동일 사고를 막을 안전망 필요.
- **Stuck enqueued 잔존**: `agents/agent_worker.py`에서 `_notify_status` PATCH 실패해도 `xack`가 무조건 실행 → status=enqueued 영구 잔존.
- **회수 메커니즘 부재**: reconcile/stuck/cleanup 코드 0건.
- **단발 PATCH**: `_notify_status`에 retry 없음.

## 사용자 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| Reconciler 동작 모드 | `dry_run=true` 기본 + `dry_run=false`일 때 mark_failed |
| Dockerfile 안전망 | ARG CACHEBUST + `backend/alembic/versions/` 분리 COPY + `--no-cache` 절차 |
| processing 중간 상태 | 보류 — 워커 1개 + consumer group이 race 자동 방지 |
| event_card_id FK | 보류 — STEP 008C+ |
| agent-worker async 전환 | 보류 — STEP 008C/D |
| agent-worker PATCH retry | 도입 — tenacity 3회 (1s, 2s, 3s backoff) |

## 비범위

- OpenSearch / Next.js UI / 검색 UI
- DART/SEC/YouTube/Reddit collector
- DLQ / circuit breaker 본격 구현
- admin endpoint token 인증 (STEP 008C)
- raw_event re-enqueue (STEP 008C+)
- `processing` 상태 도입
- event_card_id FK 제약
- agent-worker async 전환

## 수정 / 신규 파일

### 신규

| 경로 | 목적 |
|---|---|
| `backend/app/services/reconciler_service.py` | `list_stuck_enqueued()`, `mark_stuck_as_failed()` |
| `backend/tests/test_reconciler_service.py` | unit 6 케이스 |
| `backend/tests/test_reconciler_api.py` | endpoint unit 4 케이스 |
| `tests/smoke/test_reconciler.py` | stuck row → reconcile → status=failed |
| `plans/008B_PIPELINE_RELIABILITY_HARDENING_PLAN.md` | 이 파일 |
| `plans/008B_PIPELINE_RELIABILITY_HARDENING_REPORT.md` | 실행 보고 |

### 수정

| 경로 | 변경 |
|---|---|
| `backend/Dockerfile` | ARG CACHEBUST + versions/ 분리 COPY 레이어 |
| `backend/app/services/raw_event_service.py` | `list_by_status_older_than()` 추가 |
| `backend/app/api/admin.py` | `POST /reconcile-stuck`, `GET /raw-events` skeleton |
| `backend/app/schemas/raw_events.py` | `ReconcileStuckRequest/Response` 추가 |
| `agents/agent_worker.py` | tenacity retry 2회, `_patch_status` 분리 |
| `agents/tests/test_agent_worker_status.py` | retry 케이스 2개 추가 |
| `docs/ARCHITECTURE.md`, `docs/TRD.md`, `docs/API_CONTRACT.md`, `docs/COMPATIBILITY_NOTES.md`, `docs/OBSERVABILITY.md` | STEP 008B 섹션 추가 |

## 위험 / UNKNOWN

| # | 항목 | 완화 |
|---|---|---|
| R1 | ARG CACHEBUST 매 빌드 캐시 무효화 가능 | CACHEBUST=0 default. 신규 revision 시에만 사용 |
| R2 | retry 도입으로 PATCH latency 증가 | max=3s, stop=3회. 정상 시 영향 없음 |
| R3 | 정상 처리 중인 enqueued를 false-positive failed | default before_seconds=600, dry_run=true |
| R4 | smoke test에서 updated_at을 직접 조작 | PATCH로 force enqueued 후 reconcile |
| R5 | tenacity import 충돌 가능 | 동일 패키지, 문제 없음 |
| U1 | re-enqueue 메커니즘 | STEP 008C |
| U2 | reconciler cron 자동 실행 | STEP 008C/009 |
| U3 | processing 상태 + 멀티 워커 | STEP 008C+ |
| U4 | event_card_id FK + publish_card 실패 가드 | STEP 008C+ |
