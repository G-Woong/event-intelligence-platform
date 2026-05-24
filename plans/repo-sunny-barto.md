# STEP 008B — Pipeline Reliability Hardening Skeleton

## Context

STEP 008A에서 raw_event linkage + status lifecycle + LangSmith skeleton이 들어왔지만, 운영 안정성 측면에서 다음 결함이 남아 있다:

- **Docker migration 누락 위험**: STEP 008A 빌드 중 신규 migration 파일이 컨테이너에 반영되지 않아 `docker cp` 수동 복사가 필요했다. 원인 조사 결과 Dockerfile/.dockerignore/compose 설정은 모두 정상이며 현재 이미지에는 0001~0003이 모두 존재한다. 즉 **stale build cache** (`COPY backend/ backend/` 레이어 캐시 재사용)가 원인일 가능성이 가장 높다. 다음 revision 추가 시 동일 사고를 막을 안전망이 필요하다.
- **Stuck enqueued 잔존**: `agents/agent_worker.py:42-68`에서 `_notify_status` PATCH가 timeout/실패해도 finally 블록의 `xack`가 무조건 실행된다. PATCH 실패 → 메시지는 ack되지만 `raw_events.status`는 `enqueued`로 영구 잔존한다. 5가지 stuck 경로 확인됨 (worker 죽음, PATCH 실패, backend 다운, graph hang, ingest forward 후 fail).
- **회수 메커니즘 부재**: `grep reconcile|stuck|cleanup` 결과 코드 0건. `update_status`에 전이 가드 없음, bulk query 함수 없음.
- **단발 PATCH**: `_notify_status`는 단발 `httpx.patch(timeout=10)`, retry 없음. transient network 실패에도 즉시 stuck.

STEP 008B 목표: **재빌드/재시작/부분 실패 시에도 수동 개입 없이 동작하도록 Docker migration 정책을 굳히고, stuck enqueued raw_event를 감지/처리하는 reconciler skeleton과 PATCH retry를 추가한다.**

## 사용자 결정 사항 (확정)

| 항목 | 결정 |
|---|---|
| Reconciler 동작 모드 | `dry_run=true` 기본 + `dry_run=false`일 때 mark_failed. re-enqueue는 STEP 008C로 보류 |
| Dockerfile 안전망 | ARG CACHEBUST + `backend/alembic/versions/` 분리 COPY **및** 절차 강제 (`--no-cache` 명시) 둘 다 |
| processing 중간 상태 | **보류** — 워커 1개 + consumer group이 race 자동 방지. enqueued + updated_at threshold로 충분. 문서화만 |
| event_card_id FK | **보류** — publish_card 실패 가드까지 함께 손봐야 회귀 안전. STEP 008C+ |
| agent-worker async 전환 | **보류** — 광범위 refactor 회피. STEP 008C/D로 분리 |
| agent-worker PATCH retry | **도입** — tenacity로 1-2회 retry. 의존성 추가 없음 (tenacity 기설치) |

## 비범위 (절대 하지 않음)

- OpenSearch / Next.js UI / 검색 UI
- DART/SEC/YouTube/Reddit collector
- DLQ / circuit breaker 본격 구현
- admin endpoint token 인증 (STEP 008C)
- raw_event re-enqueue (STEP 008C+)
- `processing` 상태 도입
- event_card_id FK 제약
- agent-worker async 전환
- LangSmith dashboard 고도화

## 절대 금지

- `Remove-Item`, `rm`, `del`, `git reset --hard`, `git clean -fdx`
- `git push` (전 변형)
- `docker volume rm`, `docker compose down -v`
- `.env` 실제 키 값 로그/응답 노출
- codex worktree 파일을 claude에서 직접 수정

---

## 수정 / 신규 파일

### 신규

| 경로 | 목적 |
|---|---|
| `backend/app/services/reconciler_service.py` | `list_stuck_enqueued()`, `mark_stuck_as_failed()` (dry-run 모드 포함) |
| `backend/tests/test_reconciler_service.py` | unit (list/mark/dry-run/limit 6 케이스) |
| `backend/tests/test_reconciler_api.py` | endpoint unit (dry-run, mark_failed, empty, 4 케이스) |
| `tests/smoke/test_reconciler.py` | stuck row 삽입 → endpoint 호출 → status=failed 폴링 (1 케이스) |
| `plans/008B_PIPELINE_RELIABILITY_HARDENING_PLAN.md` | 본 plan 영구 사본 |
| `plans/008B_PIPELINE_RELIABILITY_HARDENING_REPORT.md` | 실행 보고 |

### 수정

| 경로 | 변경 |
|---|---|
| `backend/Dockerfile` | `ARG CACHEBUST` 추가. `backend/alembic/versions/`를 별도 COPY 레이어로 분리 (CACHEBUST 직후 위치) |
| `backend/entrypoint.sh` | `alembic upgrade head` 실패 시 명확한 exit code + 로그. set -e 확인 |
| `backend/app/services/raw_event_service.py` | `list_by_status_older_than(session, status, before_seconds, limit)` 헬퍼 추가 |
| `backend/app/api/admin.py` | `POST /api/admin/raw-events/reconcile-stuck` 라우트 추가. `GET /api/admin/raw-events?status=&before_seconds=&limit=` skeleton 추가 |
| `backend/app/schemas/raw_events.py` | `ReconcileStuckRequest(before_seconds=600, limit=100, dry_run=True, error_reason="reconciler: stuck enqueued")`, `ReconcileStuckResponse(stuck_count, marked_failed, dry_run, items)` 추가 |
| `agents/agent_worker.py` | `_notify_status`에 tenacity retry 2회 (1s, 2s backoff) 적용. PATCH 실패 카운트 로그 명시 |
| `docs/ARCHITECTURE.md` | reconciler 흐름 추가 |
| `docs/TRD.md` | STEP 008B 컴포넌트/환경변수 섹션 |
| `docs/API_CONTRACT.md` | `POST /api/admin/raw-events/reconcile-stuck`, `GET /api/admin/raw-events?status=` 섹션 |
| `docs/COMPATIBILITY_NOTES.md` | Docker migration 정책 (ARG CACHEBUST + 절차) 기록 |
| `docs/OBSERVABILITY.md` | reconciler 호출 시 로그 패턴 메모 |
| `.env.example` | 신규 변수 없음 (필요 시 `RAW_EVENT_STUCK_THRESHOLD_SEC` 주석으로만) |

---

## 핵심 코드 스니펫

### `backend/Dockerfile` 수정

```dockerfile
WORKDIR /app

# (기존 requirements 설치 레이어)

COPY backend/ backend/
COPY workers/ workers/

# STEP 008B: ensure new alembic revisions invalidate cache
ARG CACHEBUST=0
COPY backend/alembic/versions/ backend/alembic/versions/
```

`COPY backend/ backend/`가 이미 alembic 포함이지만, 별도 레이어 + ARG CACHEBUST로 신규 revision 추가 시 캐시 무효화를 보장한다. 빌드 명령:
```
docker compose -f docker-compose.dev.yml build --build-arg CACHEBUST=$(date +%s) backend
```

### `backend/app/services/reconciler_service.py` (신규)

```python
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, update
from backend.app.models.raw_event import RawEventORM
from backend.app.schemas.raw_events import RawEventRecord
from .raw_event_service import _orm_to_record

async def list_stuck_enqueued(
    session, before_seconds: int = 600, limit: int = 100,
) -> list[RawEventRecord]:
    threshold = datetime.now(timezone.utc) - timedelta(seconds=before_seconds)
    result = await session.execute(
        select(RawEventORM)
        .where(RawEventORM.status == "enqueued")
        .where(RawEventORM.updated_at < threshold)
        .order_by(RawEventORM.updated_at.asc())
        .limit(limit)
    )
    return [_orm_to_record(r) for r in result.scalars().all()]

async def mark_stuck_as_failed(
    session, before_seconds: int = 600, limit: int = 100,
    error_reason: str = "reconciler: stuck enqueued",
    dry_run: bool = True,
) -> tuple[list[RawEventRecord], int]:
    items = await list_stuck_enqueued(session, before_seconds, limit)
    if dry_run or not items:
        return items, 0
    ids = [it.id for it in items]
    await session.execute(
        update(RawEventORM)
        .where(RawEventORM.id.in_(ids))
        .values(status="failed", error_reason=error_reason[:500], processed_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return items, len(ids)
```

### `backend/app/api/admin.py` 추가 라우트

```python
@router.post("/raw-events/reconcile-stuck", response_model=ReconcileStuckResponse)
async def reconcile_stuck(
    body: ReconcileStuckRequest, session: AsyncSession = Depends(get_session)
):
    items, marked = await reconciler_service.mark_stuck_as_failed(
        session, before_seconds=body.before_seconds, limit=body.limit,
        error_reason=body.error_reason, dry_run=body.dry_run,
    )
    return ReconcileStuckResponse(
        stuck_count=len(items), marked_failed=marked, dry_run=body.dry_run, items=items,
    )

@router.get("/raw-events", response_model=list[RawEventRecord])
async def list_raw_events(
    status: str | None = None, before_seconds: int | None = None, limit: int = 50,
    session: AsyncSession = Depends(get_session),
):
    return await raw_event_service.list_by_status_older_than(
        session, status=status, before_seconds=before_seconds, limit=limit,
    )
```

### `agents/agent_worker.py` PATCH retry

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    reraise=False,
    stop=stop_after_attempt(3),  # 1차 + 2회 retry
    wait=wait_exponential(multiplier=1, min=1, max=3),
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
)
def _patch_status(url: str, payload: dict) -> None:
    resp = httpx.patch(url, json=payload, timeout=10)
    resp.raise_for_status()

def _notify_status(raw_event_id, status, error_reason=None, event_card_id=None):
    if raw_event_id is None:
        logger.warning("raw_event_id absent — status update skipped status=%s", status)
        return
    url = f"{settings.BACKEND_INTERNAL_URL}/api/admin/raw-events/{raw_event_id}/status"
    payload = {"status": status, "error_reason": error_reason, "event_card_id": event_card_id}
    try:
        _patch_status(url, payload)
    except Exception as exc:
        logger.warning("raw_event status update failed after retries id=%s reason=%s", raw_event_id, str(exc)[:200])
```

---

## 테스트 전략

### Unit — `backend/tests/test_reconciler_service.py` (6 케이스)
1. `list_stuck_enqueued` — threshold 미만 row만 반환
2. `list_stuck_enqueued` — limit 동작
3. `list_stuck_enqueued` — processed/collected/failed는 제외
4. `mark_stuck_as_failed(dry_run=True)` — UPDATE 없음, items 반환
5. `mark_stuck_as_failed(dry_run=False)` — status=failed, error_reason, processed_at 저장
6. `mark_stuck_as_failed` — 빈 결과면 marked=0

### Unit — `backend/tests/test_reconciler_api.py` (4 케이스)
1. POST dry_run=true → marked_failed=0, items 반환
2. POST dry_run=false → marked_failed=N, GET으로 status=failed 확인
3. GET `?status=enqueued&before_seconds=600` → 필터 동작
4. POST stuck 없음 → stuck_count=0

### Unit — `agents/tests/test_agent_worker_status.py` (기존 + 케이스 추가)
1. `_notify_status` 첫 호출 실패 → 2회 retry 후 성공 (mock 2번 실패 + 3번째 성공)
2. 3번 모두 실패 → warn log + 예외 swallow

### Smoke — `tests/smoke/test_reconciler.py` (1 케이스)
1. raw_event INSERT (status=enqueued, updated_at = now - 1h) → POST `/reconcile-stuck` dry_run=false → 폴링 status=failed

### 회귀 게이트 (필수 PASS, 0 diff)
- `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_raw_event_lifecycle.py tests/smoke/test_rss_collector_fixture.py -v`
- `pytest backend/tests agents/tests workers/tests -v`
- Docker migration 자동 실행 검증: `docker compose down && docker compose build --no-cache backend && docker compose up -d` → 컨테이너 로그에 `alembic upgrade head` 성공 라인

---

## 실행 순서

### Phase 1 — 정적 점검
```powershell
git status; git log --oneline -8; git worktree list
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml config --quiet
```

### Phase 2 — Dockerfile 안전망
1. `backend/Dockerfile` ARG CACHEBUST + versions/ 분리 COPY 패치
2. `backend/entrypoint.sh` 실패 노출 확인 (set -e + alembic 실패 시 exit)
3. `docker compose build --no-cache backend` → 시간 측정
4. `docker compose run --rm backend ls -la backend/alembic/versions/` → 0001~0003 존재 확인
5. `docker compose up -d backend` → 로그에 alembic upgrade head 성공 확인

### Phase 3 — Reconciler service + schema
1. `schemas/raw_events.py`에 `ReconcileStuckRequest/Response` 추가
2. `services/raw_event_service.py`에 `list_by_status_older_than()` 추가
3. `services/reconciler_service.py` 신규 (list + mark)
4. `backend/tests/test_reconciler_service.py` 작성 → PASS

### Phase 4 — Admin API endpoint
1. `api/admin.py` POST `/reconcile-stuck` + GET `/raw-events` skeleton 추가
2. `backend/tests/test_reconciler_api.py` 작성 → PASS

### Phase 5 — agent-worker retry
1. `agents/agent_worker.py` `_patch_status` + retry decorator 적용
2. `_notify_status` 호출부 정리
3. `agents/tests/test_agent_worker_status.py`에 retry 케이스 2개 추가 → PASS

### Phase 6 — Smoke
1. backend/worker/agent-worker 재빌드 + up
2. `tests/smoke/test_reconciler.py` 작성 + 실행 → PASS
3. 기존 smoke 회귀 게이트 실행

### Phase 7 — 문서
1. `docs/ARCHITECTURE.md` — reconciler 흐름 + Docker migration 정책
2. `docs/TRD.md` — STEP 008B 컴포넌트
3. `docs/API_CONTRACT.md` — reconcile-stuck + GET ?status=
4. `docs/COMPATIBILITY_NOTES.md` — ARG CACHEBUST + --no-cache 절차
5. `docs/OBSERVABILITY.md` — reconciler 로그 패턴
6. `plans/008B_PIPELINE_RELIABILITY_HARDENING_PLAN.md` + REPORT.md 작성

### Phase 8 — Commit
- Commit A: `feat(step-008b): add raw event reconciler skeleton + patch retry`
- Commit B: `chore(step-008b): docker migration safety + docs/plan/report`
- `git push` 미실행

### Phase 9 — Codex sync
```powershell
git -C C:/Users/computer/Desktop/business/codex status --short
git -C C:/Users/computer/Desktop/business/codex fetch
git -C C:/Users/computer/Desktop/business/codex merge --no-ff main
```

---

## 검증 체크리스트

- [ ] `docker compose config --quiet` PASS
- [ ] `docker compose build --no-cache backend` 성공
- [ ] 신규 컨테이너 안 `backend/alembic/versions/`에 0001~0003 존재
- [ ] backend 로그에 `alembic upgrade head` 자동 실행 확인
- [ ] `entrypoint.sh` 실패 시 컨테이너가 조용히 뜨지 않음 (alembic 실패 → exit 1)
- [ ] reconciler service 6 케이스 PASS
- [ ] reconciler API 4 케이스 PASS
- [ ] `_notify_status` retry 케이스 2개 PASS
- [ ] reconciler smoke PASS (stuck → mark_failed → 폴링)
- [ ] 기존 smoke 회귀 0 (pipeline/persistence/lifecycle/rss_fixture)
- [ ] `pytest backend/tests agents/tests workers/tests -v` 전체 PASS
- [ ] 8개 컨테이너 Up/healthy
- [ ] docs 6개 갱신/신규 + plan/report 2개
- [ ] processing 상태/event_card_id FK/async 전환 보류 사유 문서화
- [ ] Commit A/B 성공, `.env`/.venv/RSS 원문 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료
- [ ] WARNING/BLOCKED/UNKNOWN 명시

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | ARG CACHEBUST 추가로 매 빌드 캐시 무효화 가능 | 낮음 | `CACHEBUST=0` default 유지. 신규 revision 추가 시에만 `--build-arg CACHEBUST=$(date +%s)` 사용 |
| R2 | `_notify_status` retry 도입으로 PATCH 호출 latency 증가 | 낮음 | exponential backoff max=3s, 총 stop=3회. 정상 시 영향 없음 |
| R3 | reconciler가 정상 처리 중인 enqueued를 false-positive로 failed 전환 | 중간 | default `before_seconds=600` (10분). default `dry_run=true`. 호출자가 명시적으로 `dry_run=false` 설정해야 변경 발생 |
| R4 | smoke `test_reconciler.py`에서 `updated_at`을 직접 과거로 INSERT — production semantic과 다름 | 낮음 | 테스트 한정. 코멘트로 명시 |
| R5 | tenacity가 이미 OpenAI client retry에 쓰이므로 import 충돌 가능 | 낮음 | 동일 패키지 — `from tenacity import retry, ...` |
| U1 | re-enqueue 메커니즘 | — | STEP 008C에서 검토 (이번 단계 mark_failed만) |
| U2 | reconciler를 cron으로 자동 실행할지 | — | STEP 008C/009에서 결정. 이번엔 endpoint 수동 호출만 |
| U3 | processing 상태 + 멀티 워커 | — | 워커 수평 확장 시 STEP 008C+ 재검토 |
| U4 | event_card_id FK + publish_card 실패 가드 | — | STEP 008C+ |

---

## 다음 STEP 제안

1. **STEP 008C** — admin endpoint token 인증 + raw_event re-enqueue + reconciler cron + `GET /raw-events` 페이징 + status 전이 가드
2. **STEP 008D** — agent-worker async 전환 + processing 중간 상태 (멀티 워커 도입 시) + event_card_id FK + publish_card 가드
3. **STEP 009** — Next.js `/events` UI + `/raw-events` admin UI + collector_sources 테이블
4. **STEP 010** — DART/SEC collector + vector dedup threshold + entity linking LLM 전환
