# STEP 008C — Admin Auth + Re-enqueue + Scheduler Skeleton

## Context

STEP 008B까지 backend 운영 골격은 다음과 같다:
- Admin/internal endpoint가 **인증 없이 노출**되어 있음 (`/api/admin/*`, `/api/internal/search-similar`).
- Reconciler는 `dry_run|mark_failed`만 지원. **failed/stuck raw_event를 다시 stream에 넣을 방법 없음**.
- Reconciler를 주기 실행할 hook이 없음 (수동 HTTP 호출만).
- `GET /api/admin/raw-events`는 status/before_seconds/limit만 지원 — admin UI/cli에서 쓰기엔 부족.
- `workers/collectors/rss_collector.py`, `workers/pipelines/publish_pipeline.py`, `agents/agent_worker.py`가 모두 backend admin endpoint에 인증 없이 POST/PATCH.

STEP 008C 목표: **OpenSearch/Frontend 진입 전 backend 운영 골격의 최소 안전장치를 닫는다.**
1) admin/internal endpoint에 최소 token 인증 부여
2) failed/stuck raw_event를 다시 Redis Stream에 안전하게 넣는 단일 requeue endpoint
3) reconciler를 1회 실행하는 script skeleton (cron/CI hook용)
4) `GET /api/admin/raw-events`에 source_type/offset/order 추가

## 사용자 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| Dev-mode 정책 | `ADMIN_API_TOKEN`이 비어 있으면 시작 시 WARNING 로그 + 모든 admin 호출 허용. 설정 시 즉시 강제. 기존 smoke/회귀 호환성 유지 |
| Requeue 대상 | `failed`/`enqueued`만 기본 허용. `processed`는 `force=true`로만. 중복 event_card 방지 |
| Scheduler 형태 | `scripts/reconcile_stuck_once.py` 1회 실행. env 기반 (`ADMIN_API_TOKEN`, `RECONCILER_BEFORE_SECONDS`, `RECONCILER_LIMIT`, `RECONCILER_DRY_RUN`, `BACKEND_INTERNAL_URL`). compose 서비스 추가 없음 |
| processing 상태 | **계속 보류** — single agent-worker + consumer group으로 race 자동 방지. requeue 시 force 가드로 중복 위험 통제. 도입 비용 > 이득 |
| event_card_id FK | **계속 보류** — STEP 008D |
| admin token 방식 | `X-Admin-Token: <token>` 헤더. router-level dependency |
| auth 적용 범위 | `/api/admin/*` 전체 + `/api/internal/search-similar`. `/health`, `/api/events|themes|sectors|comments|ai-replies`는 제외 |

## 비범위 (절대 하지 않음)

- OpenSearch / Next.js UI / 검색 UI
- DART/SEC/YouTube/Reddit collector
- production-grade auth (RBAC/OAuth/JWT/user login)
- DLQ / circuit breaker 본격 구현
- bulk requeue / requeue-on-reconcile
- long-running scheduler container
- `processing` 상태 도입
- `event_card_id` FK 제약
- agent-worker async 전환

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (모든 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실제 값(`ADMIN_API_TOKEN` 포함) 로그/응답/문서 노출
- codex worktree 파일을 claude에서 직접 수정

---

## 핵심 설계

### 1. Admin Token Auth (`backend/app/core/security.py` 신규)

```python
# pseudo
def require_admin_token(x_admin_token: str | None = Header(default=None)):
    expected = settings.ADMIN_API_TOKEN
    if not expected:
        # dev mode — startup에서 이미 WARNING 출력됨
        return
    if x_admin_token != expected:
        raise HTTPException(status_code=401, detail="invalid admin token")
```

- 시작 시 `settings.ADMIN_API_TOKEN`이 빈 문자열이면 `logger.warning("ADMIN_API_TOKEN unset — admin endpoints unauthenticated (dev only)")` 출력 (lifespan 또는 module-level).
- `main.py`에서 router-level dependency 적용: `app.include_router(admin.router, dependencies=[Depends(require_admin_token)])`. internal router에도 동일 적용.
- 비교는 `secrets.compare_digest`로 timing-safe.

### 2. Requeue Endpoint + Service

- `backend/app/schemas/raw_events.py`:
  ```python
  class RequeueRequest(BaseModel):
      force: bool = False
  class RequeueResponse(BaseModel):
      record: RawEventRecord
      enqueued_msg_id: str
      requeue_count: int
  ```
- `backend/app/services/raw_event_service.py`에 `requeue_raw_event(session, raw_event_id, force=False)`:
  - row 로드 → not found → `NoResultFound`
  - `status == "processed"` and not `force` → `ValueError("requeue refused: row already processed; pass force=true to override")`
  - `RawEvent` 빌드 (기존 `create_raw_event`의 enqueue 블록 재사용 패턴)
  - `enqueue_raw_event(raw_event)` 호출 → `msg_id`
  - `raw_metadata["requeue_count"]`를 1 증가 (기본 0)
  - row update: `status="enqueued"`, `enqueued_msg_id=msg_id`, `error_reason=None`, `processed_at=None`, `raw_metadata=updated`, `updated_at=now()`
  - 갱신된 record + msg_id + requeue_count 반환
- `backend/app/api/admin.py`에 `POST /raw-events/{raw_event_id}/requeue`:
  - static route 순서 보존: `/raw-events/reconcile-stuck` → `/raw-events` (POST/GET) → `/raw-events/{id}` (GET) → `/raw-events/{id}/requeue` (POST) → `/raw-events/{id}/status` (PATCH)
  - `NoResultFound` → 404, `ValueError` → 409.

### 3. Scheduler Skeleton (`scripts/reconcile_stuck_once.py` 신규)

```python
# env: BACKEND_INTERNAL_URL, ADMIN_API_TOKEN, RECONCILER_BEFORE_SECONDS=600,
#      RECONCILER_LIMIT=100, RECONCILER_DRY_RUN=true
import os, sys, json, httpx
def main() -> int:
    url = f"{os.getenv('BACKEND_INTERNAL_URL', 'http://localhost:8000')}/api/admin/raw-events/reconcile-stuck"
    headers = {}
    token = os.getenv("ADMIN_API_TOKEN", "")
    if token:
        headers["X-Admin-Token"] = token
    body = {
        "before_seconds": int(os.getenv("RECONCILER_BEFORE_SECONDS", "600")),
        "limit": int(os.getenv("RECONCILER_LIMIT", "100")),
        "dry_run": os.getenv("RECONCILER_DRY_RUN", "true").lower() in ("1", "true", "yes"),
    }
    try:
        resp = httpx.post(url, json=body, headers=headers, timeout=30)
        resp.raise_for_status()
        print(json.dumps(resp.json(), default=str))
        return 0
    except Exception as exc:
        print(f"reconcile_stuck_once failed: {exc}", file=sys.stderr)
        return 1
if __name__ == "__main__":
    sys.exit(main())
```

운영 호출 예: `docker compose exec backend python /app/scripts/reconcile_stuck_once.py` 또는 `python -m scripts.reconcile_stuck_once` (venv).

### 4. raw_events list 확장

`backend/app/services/raw_event_service.py` `list_by_status_older_than` 시그니처에 `source_type`, `offset`, `order` 추가 (기본값으로 기존 동작 보존). 호출자 한 곳 (`reconciler_service.list_stuck_enqueued`)은 시그니처 변경 없이 동작 (모두 기본값 사용 가능). `admin.py`에서 query param 노출.

### 5. 내부 caller에 token header 추가

- `agents/agent_worker.py`: `_patch_status`에서 `settings.ADMIN_API_TOKEN` 읽어 `X-Admin-Token` 헤더 추가
- `workers/collectors/rss_collector.py`: `os.getenv("ADMIN_API_TOKEN", "")` 읽어 헤더 추가
- `workers/pipelines/publish_pipeline.py`: 동일

토큰이 비어 있으면 헤더 미포함 → backend가 dev-mode allow 처리.

---

## 수정 / 신규 파일

### 신규

| 경로 | 목적 |
|---|---|
| `backend/app/core/security.py` | `require_admin_token` dependency |
| `scripts/__init__.py` | scripts 패키지 마커 |
| `scripts/reconcile_stuck_once.py` | scheduler skeleton — env 기반 reconcile-stuck 1회 호출 |
| `backend/tests/test_admin_auth.py` | auth 6 케이스 (unset+미발송, set+미발송, set+오발송, set+정발송, internal 동일, dry-run override) |
| `backend/tests/test_requeue_service.py` | service 5 케이스 (failed→requeue, enqueued→requeue, processed→reject, processed+force, not found) |
| `backend/tests/test_requeue_api.py` | endpoint 4 케이스 (200, 404, 409, auth required) |
| `backend/tests/test_reconcile_script.py` | script 3 케이스 (happy/HTTP fail/env override) |
| `tests/smoke/test_requeue.py` | smoke 1 케이스 (create → settle → PATCH=failed → requeue → poll processed) |
| `plans/008C_ADMIN_REQUEUE_SCHEDULER_PLAN.md` | 본 plan 영구 사본 |
| `plans/008C_ADMIN_REQUEUE_SCHEDULER_REPORT.md` | 실행 보고 |

### 수정

| 경로 | 변경 |
|---|---|
| `backend/app/core/config.py` | `ADMIN_API_TOKEN: str = ""` + `redacted_env_status()` 항목 추가 |
| `backend/app/main.py` | `setup_langsmith()` 다음에 `ADMIN_API_TOKEN` 미설정 WARN. router 등록 시 `dependencies=[Depends(require_admin_token)]` 적용 (admin + internal) |
| `backend/app/api/admin.py` | requeue endpoint 추가. list query params 확장 (source_type, offset, order) |
| `backend/app/api/internal.py` | (변경 없음 — main.py에서 router-level dependency 적용) |
| `backend/app/schemas/raw_events.py` | `RequeueRequest`, `RequeueResponse` 추가 |
| `backend/app/services/raw_event_service.py` | `requeue_raw_event()` 추가, `list_by_status_older_than(..., source_type, offset, order)` 확장 |
| `agents/agent_worker.py` | `_patch_status`에 `X-Admin-Token` 헤더 |
| `workers/collectors/rss_collector.py` | POST `/raw-events` 시 `X-Admin-Token` 헤더 |
| `workers/pipelines/publish_pipeline.py` | POST `/upsert-event` 시 `X-Admin-Token` 헤더 |
| `backend/tests/test_raw_events_api.py` | `require_admin_token` dependency override fixture (전체 모듈) |
| `backend/tests/test_raw_event_status_api.py` | 동일 |
| `backend/tests/test_reconciler_api.py` | 동일 |
| `backend/tests/test_internal_api.py` | 동일 |
| `agents/tests/test_agent_worker_status.py` | `httpx.patch` 호출 시 `headers={"X-Admin-Token": ...}` 검증 1 케이스 추가 (선택) |
| `docker-compose.dev.yml` | backend/worker/agent-worker 모두 `env_file: .env`만으로 `ADMIN_API_TOKEN` 주입 (변경 불필요할 수 있음 — 확인) |
| `.env.example` | `ADMIN_API_TOKEN=` 추가 + `RECONCILER_BEFORE_SECONDS`, `RECONCILER_LIMIT`, `RECONCILER_DRY_RUN` placeholder |
| `docs/API_CONTRACT.md` | `X-Admin-Token` 헤더 명시, `POST /raw-events/{id}/requeue` 섹션, `GET /raw-events` 파라미터 표 갱신 |
| `docs/ARCHITECTURE.md` | auth 경계, requeue 흐름, scheduler hook 다이어그램 |
| `docs/TRD.md` | STEP 008C 환경변수, dev/prod policy |
| `docs/OBSERVABILITY.md` | requeue 로그 패턴, scheduler exit code 표 |
| `docs/COMPATIBILITY_NOTES.md` | dev-mode unauthenticated fallback 정책, 향후 RBAC TODO |
| `docs/COLLECTOR_DESIGN.md` | rss_collector가 `ADMIN_API_TOKEN` 사용한다는 점 명시 |

---

## 테스트 전략

### Unit — `backend/tests/test_admin_auth.py` (6 케이스)
1. ADMIN_API_TOKEN 미설정 + 헤더 없음 → 200 (dev allow)
2. ADMIN_API_TOKEN 설정 + 헤더 없음 → 401
3. ADMIN_API_TOKEN 설정 + 잘못된 헤더 → 401
4. ADMIN_API_TOKEN 설정 + 올바른 헤더 → 200
5. `/api/admin/jobs` 보호 적용 확인
6. `/api/internal/search-similar` 보호 적용 확인

테스트는 `monkeypatch.setattr("backend.app.core.security.settings.ADMIN_API_TOKEN", "secret")` 또는 `settings` 인스턴스 직접 패치로 처리. `app.dependency_overrides` 사용 가능.

### Unit — `backend/tests/test_requeue_service.py` (5 케이스)
1. `failed` → `requeue_raw_event` → status=enqueued, enqueued_msg_id set, requeue_count=1, error_reason=None
2. `enqueued` → requeue → status=enqueued, enqueued_msg_id 갱신
3. `processed` 기본 → ValueError
4. `processed` + force=True → status=enqueued, requeue_count 증가
5. not found → NoResultFound

`enqueue_raw_event`는 mock.

### Unit — `backend/tests/test_requeue_api.py` (4 케이스)
1. 200: requeue 성공 → record/msg_id/requeue_count
2. 404: not found
3. 409: processed 기본 (ValueError → 409)
4. 401: token 검증 (auth 모듈과 통합)

### Unit — `backend/tests/test_reconcile_script.py` (3 케이스)
1. `httpx.post` mock → 200 → exit 0, stdout JSON
2. `httpx.post` mock → 500 → exit 1, stderr 메시지
3. env override (`RECONCILER_BEFORE_SECONDS=120`, `RECONCILER_DRY_RUN=false`) → 호출 payload 검증

subprocess 없이 `main()` 직접 호출 + `monkeypatch.setattr("httpx.post", ...)`.

### Unit — 기존 admin 테스트 수정
- `test_raw_events_api.py`, `test_raw_event_status_api.py`, `test_reconciler_api.py`, `test_internal_api.py`: pytest fixture에서 `app.dependency_overrides[require_admin_token] = lambda: None` 추가. 기존 테스트 변경 최소화.

### Smoke — `tests/smoke/test_requeue.py` (1 케이스)
1. create raw_event → _poll_status(processed/failed/enqueued, 30s) → PATCH status=failed → POST requeue → _poll_status(processed, 30s) → assert event_card_id set

`ADMIN_API_TOKEN`이 .env에 있으면 헤더 포함 (env에서 읽기).

### 회귀 게이트 (필수 PASS)
- `pytest backend/tests agents/tests workers/tests -v`
- `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_raw_event_lifecycle.py tests/smoke/test_rss_collector_fixture.py tests/smoke/test_reconciler.py tests/smoke/test_requeue.py -v`
- backend/worker/agent-worker 8개 컨테이너 Up/healthy

---

## 실행 순서

### Phase 0 — 정적 점검
- `git status; git log --oneline -6; docker compose -f docker-compose.dev.yml ps`
- 기존 코드 디렉터리 구조 확인 (scripts/ 신규, security.py 신규)

### Phase 1 — Auth skeleton
1. `config.py`에 `ADMIN_API_TOKEN` 추가 + `redacted_env_status` 등록
2. `security.py` 신규 (Header dependency + secrets.compare_digest)
3. `main.py`에 router-level dependency 적용 + 시작 WARN
4. `backend/tests/test_admin_auth.py` 작성 → PASS
5. 기존 admin/internal 테스트 4개 모듈에 dependency_override fixture 추가 → PASS

### Phase 2 — Internal caller token wiring
1. `agents/agent_worker.py` `_patch_status` 헤더 추가
2. `workers/collectors/rss_collector.py` 헤더 추가
3. `workers/pipelines/publish_pipeline.py` 헤더 추가
4. `agents/tests/test_agent_worker_status.py` 헤더 검증 케이스 추가 (선택) → PASS

### Phase 3 — Requeue
1. `schemas/raw_events.py`에 `RequeueRequest/Response` 추가
2. `services/raw_event_service.py`에 `requeue_raw_event()` 추가
3. `api/admin.py`에 requeue endpoint 추가 + 라우터 순서 확인
4. `test_requeue_service.py`, `test_requeue_api.py` 작성 → PASS

### Phase 4 — List 확장
1. `services/raw_event_service.py` `list_by_status_older_than(source_type, offset, order)` 시그니처 확장
2. `api/admin.py` GET 파라미터 노출
3. `test_reconciler_api.py`에 source_type/offset 검증 케이스 1~2개 추가 → PASS

### Phase 5 — Scheduler script
1. `scripts/__init__.py`, `scripts/reconcile_stuck_once.py` 신규
2. `backend/tests/test_reconcile_script.py` 작성 → PASS

### Phase 6 — Rebuild + Smoke
1. `docker compose -f docker-compose.dev.yml build backend worker agent-worker`
2. `docker compose up -d`
3. 8개 컨테이너 healthy 확인
4. `tests/smoke/test_requeue.py` 작성 + 실행 → PASS
5. 기존 smoke 회귀 게이트 실행 (ADMIN_API_TOKEN 미설정 → dev allow)
6. (선택) `.env`에 `ADMIN_API_TOKEN=devtoken` 추가 → smoke 재실행 → PASS 확인 → 다시 제거

### Phase 7 — 문서
1. `docs/API_CONTRACT.md` — auth header, requeue, list params
2. `docs/ARCHITECTURE.md` — auth/requeue/scheduler
3. `docs/TRD.md` — env var policy
4. `docs/OBSERVABILITY.md` — requeue/script logs
5. `docs/COMPATIBILITY_NOTES.md` — dev-mode policy
6. `docs/COLLECTOR_DESIGN.md` — token usage
7. `plans/008C_*_PLAN.md` + `_REPORT.md` 작성

### Phase 8 — Commit
- Commit A: `feat(step-008c): add admin auth and raw event requeue endpoint`
- Commit B: `chore(step-008c): scheduler script + docs/plan/report`
- `git push` 미실행

### Phase 9 — Codex sync
- `git -C C:/Users/computer/Desktop/business/codex status --short`
- `git -C C:/Users/computer/Desktop/business/codex fetch`
- `git -C C:/Users/computer/Desktop/business/codex merge --no-ff main` (충돌 시 보고)

---

## 검증 체크리스트

- [ ] `docker compose config --quiet` PASS
- [ ] `backend/app/core/security.py` 신규 + `Settings.ADMIN_API_TOKEN` 추가
- [ ] `main.py` lifespan 또는 module-level에 token 미설정 WARN
- [ ] admin/internal router에 router-level `Depends(require_admin_token)`
- [ ] token 미설정 + 헤더 없음 → 200 (dev allow)
- [ ] token 설정 + 헤더 없음/오발송 → 401
- [ ] token 설정 + 정발송 → 200
- [ ] `agents/agent_worker.py`, `workers/collectors/rss_collector.py`, `workers/pipelines/publish_pipeline.py` 모두 `X-Admin-Token` 헤더 전송
- [ ] `POST /raw-events/{id}/requeue` 200 (failed/enqueued)
- [ ] `POST /raw-events/{id}/requeue` 409 (processed, force=false)
- [ ] `POST /raw-events/{id}/requeue` 200 (processed, force=true)
- [ ] `POST /raw-events/{id}/requeue` 404
- [ ] `raw_metadata.requeue_count` 증가
- [ ] `GET /raw-events?source_type=&offset=&order=desc` 동작
- [ ] `scripts/reconcile_stuck_once.py` happy/fail/env override 3 케이스 PASS
- [ ] smoke `test_requeue.py` PASS (create → fail → requeue → processed)
- [ ] 기존 smoke 회귀 0 (pipeline/persistence/lifecycle/rss_fixture/reconciler)
- [ ] `pytest backend/tests agents/tests workers/tests -v` 전체 PASS
- [ ] 8개 컨테이너 Up/healthy
- [ ] docs 6개 갱신 + plan/report 2개
- [ ] processing 상태 / event_card_id FK / RBAC 보류 사유 문서화
- [ ] Commit A/B, `.env`/.venv/실토큰 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료
- [ ] WARNING/BLOCKED/UNKNOWN 명시

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | dev-mode allow 정책이 운영에서 무방비로 이어질 위험 | 중간 | 시작 시 WARN 로그 강제. docs에 prod 체크리스트 명시 |
| R2 | `secrets.compare_digest`는 동일 길이 비교 — 다른 길이 시 항상 false | 낮음 | 정상. 다만 missing 헤더 분기를 먼저 처리 |
| R3 | `require_admin_token`을 router-level로 걸면 backend 테스트 다수 영향 | 중간 | 영향 모듈 4개에 `dependency_overrides` fixture 추가. fixture를 module-level conftest 없이 모듈마다 별도 fixture로 유지 (기존 패턴 보존) |
| R4 | requeue 시 `enqueue_raw_event`가 새 msg_id를 stream에 push — worker가 동일 raw_event_id를 또 처리하면 중복 event_card 생성 | 중간 | force 가드(processed 기본 거부). `raw_metadata.requeue_count` 기록으로 운영 추적 가능. event_card_id FK는 STEP 008D |
| R5 | rss_collector/publish_pipeline은 token이 비어있으면 헤더 미포함 — backend가 dev allow 안 하면 깨짐 | 낮음 | dev-mode allow가 default. token 설정 후엔 모두 동일 .env 공유 |
| R6 | scripts/ 패키지가 PYTHONPATH에 잡혀야 `python -m scripts.reconcile_stuck_once` 동작 | 낮음 | `python /app/scripts/reconcile_stuck_once.py`로도 동작. docs에 두 방법 명시 |
| R7 | smoke `test_requeue.py`에서 agent-worker가 requeue된 메시지를 또 처리 → status=processed로 다시 전이 | 낮음 | 의도된 동작. 폴링은 processed 또는 failed 모두 종료 신호로 인정 |
| U1 | 다중 worker 도입 시 `processing` 상태 | — | STEP 008D 재검토 |
| U2 | bulk requeue / requeue-on-reconcile | — | STEP 008D+ |
| U3 | RBAC / OAuth / per-endpoint scope | — | STEP 010+ |
| U4 | scheduler를 cron service로 분리할지 | — | STEP 009/010 |
| U5 | `event_card_id` FK + publish_card 실패 가드 | — | STEP 008D |

---

## 다음 STEP 제안

1. **STEP 008D** — `processing` 상태 + `event_card_id` FK + publish_card 실패 가드 + agent-worker async 전환 (멀티 worker 진입 전)
2. **STEP 009** — Next.js `/events` UI + `/raw-events` admin UI (X-Admin-Token 사용) + collector_sources 테이블
3. **STEP 010** — OpenSearch keyword search + DART/SEC collector + RBAC 진입
