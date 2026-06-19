# STEP 008C — Admin Auth + Re-enqueue + Scheduler Skeleton (REPORT)

날짜: 2026-05-24

## ① 무엇을 했는가

### Phase 1 — Auth skeleton
- `backend/app/core/config.py`: `ADMIN_API_TOKEN: str = ""` 추가, `redacted_env_status` 목록 등록
- `backend/app/core/security.py` (신규): `require_admin_token` FastAPI Header dependency. `secrets.compare_digest` timing-safe 비교. 미설정 시 즉시 return.
- `backend/app/main.py`: lifespan에 `ADMIN_API_TOKEN` 미설정 WARNING 추가. `admin.router` + `internal.router`에 `dependencies=[Depends(require_admin_token)]` 적용.
- `backend/tests/test_admin_auth.py` (신규): 6 케이스 작성 (unset+미발송, set+미발송, set+오발송, set+정발송, jobs 보호, internal 보호)
- 기존 테스트 4개 모듈에 `dependency_overrides[require_admin_token] = lambda: None` fixture 추가

### Phase 2 — Internal caller token wiring
- `agents/agent_worker.py`: `_patch_status` 시그니처에 `headers` 파라미터 추가. `_notify_status`에서 `settings.ADMIN_API_TOKEN` 읽어 헤더 삽입.
- `workers/collectors/rss_collector.py`: `_ADMIN_TOKEN = os.getenv(...)` 추가, POST 시 헤더 삽입.
- `workers/pipelines/publish_pipeline.py`: 동일 패턴.
- `agents/tests/test_agent_worker_status.py`: side_effect 함수 시그니처에 `headers=None` 추가 (호환성 수정).

### Phase 3 — Requeue
- `backend/app/schemas/raw_events.py`: `RequeueRequest(force: bool)`, `RequeueResponse(record, enqueued_msg_id, requeue_count)` 추가
- `backend/app/services/raw_event_service.py`: `requeue_raw_event()` 신규 — row 로드 → processed 가드 → enqueue → requeue_count 증가 → row 갱신 → refreshed record 반환
- `backend/app/api/admin.py`: `POST /raw-events/{raw_event_id}/requeue` endpoint 추가. NoResultFound→404, ValueError→409. 라우터 순서 보존.
- `backend/tests/test_requeue_service.py` (신규): 5 케이스
- `backend/tests/test_requeue_api.py` (신규): 4 케이스

### Phase 4 — List 확장
- `raw_event_service.list_by_status_older_than`: `source_type`, `offset`, `order` 파라미터 추가. 기존 호출자는 기본값으로 동작 무변경.
- `admin.py GET /raw-events`: query param 노출.

### Phase 5 — Scheduler script
- `scripts/__init__.py` (신규): 패키지 마커
- `scripts/reconcile_stuck_once.py` (신규): env 기반 1회 실행. 성공 exit 0, 실패 exit 1.
- `backend/tests/test_reconcile_script.py` (신규): 3 케이스 (happy/HTTP fail/env override)

### Phase 6 — Docker rebuild + smoke
- `docker compose build backend worker agent-worker` → PASS
- `docker compose up -d` → 8개 컨테이너 Up/healthy
- `tests/smoke/test_requeue.py` (신규): 1 케이스 (create→fail→requeue→settled)

### Phase 7 — 문서
- `docs/API_CONTRACT.md`: 인증 섹션 신규, requeue endpoint 추가, list params 표 갱신, TODO 제거
- `docs/COMPATIBILITY_NOTES.md`: STEP 008C dev-mode policy + prod checklist + RBAC TODO
- `docs/COLLECTOR_DESIGN.md`: 아키텍처 다이어그램에 X-Admin-Token 흐름 명시
- `.env.example`: ADMIN_API_TOKEN + RECONCILER_* 추가

## ② 무엇을 검증했는가

| 검증 | 결과 |
|---|---|
| `pytest backend/tests/ agents/tests/ workers/tests/ -v` | **107 passed, 5 skipped** |
| test_admin_auth.py 6 케이스 | PASS |
| test_requeue_service.py 5 케이스 | PASS |
| test_requeue_api.py 4 케이스 | PASS |
| test_reconcile_script.py 3 케이스 | PASS |
| 기존 admin/internal/status/reconciler API 테스트 | 전체 PASS (dependency_override 적용 후) |
| `tests/smoke/test_requeue.py` | PASS (12.71s) |
| 기존 smoke 5종 회귀 | 7 passed (52.21s) |
| 8개 컨테이너 Up/healthy | PASS |
| `docker compose config --quiet` | PASS |

## ③ WARNING / BLOCKED / UNKNOWN

- WARNING: `ADMIN_API_TOKEN` 이 `.env`에 미설정 상태 → dev-mode allow (의도됨). prod 배포 전 설정 필수.
- UNKNOWN: `processing` 상태 도입 → **STEP 008D 재검토**
- UNKNOWN: `event_card_id` FK + publish_card 실패 가드 → **STEP 008D**
- UNKNOWN: RBAC / OAuth / per-endpoint scope → **STEP 010+**
- UNKNOWN: scheduler를 cron service로 분리 → **STEP 009/010**
- BLOCKED: `git push` — 정책상 미실행
- codex sync: 이번 commit 후 별도 실행 필요
