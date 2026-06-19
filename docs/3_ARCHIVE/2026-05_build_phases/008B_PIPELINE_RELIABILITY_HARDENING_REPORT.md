# STEP 008B — Pipeline Reliability Hardening Report

날짜: 2026-05-24

## ① 무엇을 했는가

### Phase 2: Dockerfile 안전망
- `backend/Dockerfile`에 `ARG CACHEBUST=0` + `COPY backend/alembic/versions/` 분리 레이어 추가
- `docker compose build --no-cache backend` 성공, 컨테이너 내 0001~0003 확인
- `backend/entrypoint.sh`는 기존에 `set -e` 적용됨 — alembic 실패 시 exit 1 보장

### Phase 3: Reconciler service + schema
- `backend/app/schemas/raw_events.py`: `ReconcileStuckRequest`, `ReconcileStuckResponse` 추가
- `backend/app/services/raw_event_service.py`: `list_by_status_older_than()` 추가 + `timedelta` import
- `backend/app/services/reconciler_service.py` 신규: `list_stuck_enqueued()`, `mark_stuck_as_failed()`

### Phase 4: Admin API endpoint
- `backend/app/api/admin.py` 재작성 (라우터 순서 정렬):
  - `POST /api/admin/raw-events/reconcile-stuck` 추가
  - `GET /api/admin/raw-events` (status/before_seconds/limit 필터) 추가
  - 기존 `POST /raw-events`, `GET /raw-events/{id}`, `PATCH /{id}/status` 순서 유지

### Phase 5: agent-worker PATCH retry
- `agents/agent_worker.py`: tenacity `_patch_status()` 분리 + `@retry(stop=3, backoff=1-3s)` 적용
- `TransportError`, `HTTPStatusError` 재시도. 3회 실패 시 WARNING 로그 + 예외 swallow

### Phase 6: Smoke 테스트
- `tests/smoke/test_reconciler.py` 신규: create → pipeline settle → force enqueued via PATCH → sleep 3s → reconcile dry_run=false → poll status=failed

### Phase 7: 문서
- `docs/ARCHITECTURE.md`: Reconciler 흐름 + stuck 5경로 + Docker migration 정책 추가
- `docs/TRD.md`: STEP 008B 컴포넌트/환경변수/보류 섹션 추가
- `docs/API_CONTRACT.md`: `POST /reconcile-stuck`, `GET /raw-events` 섹션 추가
- `docs/COMPATIBILITY_NOTES.md`: ARG CACHEBUST + --no-cache 절차 기록
- `docs/OBSERVABILITY.md`: reconciler 로그 패턴 + stuck 탐지 기준 추가

## ② 무엇을 검증했는가

| 항목 | 결과 |
|---|---|
| `docker compose build --no-cache backend` | PASS |
| 컨테이너 내 `backend/alembic/versions/` 0001~0003 | PASS |
| backend 로그에 alembic upgrade head 자동 실행 | PASS |
| `test_reconciler_service.py` 6 케이스 | PASS |
| `test_reconciler_api.py` 4 케이스 | PASS |
| `test_agent_worker_status.py` 6 케이스 (기존 4 + 신규 2) | PASS |
| `tests/smoke/test_reconciler.py` 1 케이스 | PASS |
| smoke 회귀 게이트 (pipeline/persistence/lifecycle/rss_fixture) | 6/6 PASS |
| 전체 `backend/tests agents/tests workers/tests` | 89 PASS, 5 SKIP |
| 8개 컨테이너 Up/healthy | PASS |
| git push | 미실행 |

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING
- `ei-worker` / `ei-agent-worker`가 초기에 Restarting 상태였다가 복구됨. smoke 테스트는 pipeline settle 후 force-enqueued 방식으로 race condition 회피.
- smoke `test_reconciler.py`의 `before_seconds=2` + `sleep(3)` 접근: Python clock ↔ Postgres clock 미세 차이 존재. 실전 운영은 `before_seconds=600` 권장.

### UNKNOWN
- U1: re-enqueue 메커니즘 → STEP 008C 검토
- U2: reconciler cron 자동 실행 → STEP 008C/009 결정
- U3: processing 상태 + 멀티 워커 → STEP 008C+ 재검토
- U4: event_card_id FK + publish_card 실패 가드 → STEP 008C+

## 다음 STEP 제안

1. **STEP 008C** — admin endpoint token 인증 + re-enqueue + reconciler cron + `GET /raw-events` 페이징 + status 전이 가드
2. **STEP 008D** — agent-worker async + processing 중간 상태 + event_card_id FK
3. **STEP 009** — Next.js `/events` UI + `/raw-events` admin UI
