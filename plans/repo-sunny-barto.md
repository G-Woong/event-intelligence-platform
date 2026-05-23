# STEP 008A — RawEvent Processing Linkage + Status Lifecycle + Observability Skeleton

## Context

STEP 007에서 RSS collector → `raw_events` insert → Redis Stream XADD까지 입구가 뚫렸지만, 그 이후의 결과 추적은 비어 있다:
- `raw_events.status`는 `collected → enqueued`에서 멈춘다 (`backend/app/models/raw_event.py:25` default `"collected"`, `raw_event_service.py:99-106` UPDATE)
- Redis Stream payload(`workers/queue/producer.py:12-18`)에 `raw_event_id`가 없다 → agent-worker가 어떤 row를 처리 중인지 모른다
- `EventState`(`agents/state/event_state.py:9-26`)에 `raw_event_id` 슬롯이 없다
- agent-worker(`agents/agent_worker.py:36-39`)는 성공/실패 결과를 backend에 통보하지 않는다 — backend도 status update endpoint가 없다
- `docs/EVENT_SCHEMA.md:112` 주석에 "processed/failed (STEP 008)"으로 이미 약속됨

STEP 008A의 목표:
**raw_event_id를 stream payload → worker → agent-worker → LangGraph state → backend status update까지 최소 침습으로 전달하고, processed/failed 전이를 채우며, LangSmith를 plug-in 가능한 skeleton 수준으로 정리한다.**

OpenSearch, Next.js, 신규 collector, 본격 retry/DLQ, admin auth는 본 STEP 범위 외.

---

## 사용자 결정 (Claude가 탐색 결과로 확정한 설계)

| 결정 항목 | 선택 | 근거 |
|---|---|---|
| status 라이프사이클 확장 | `collected → enqueued → processed \| failed` (별도 `processing` 상태 도입 안 함) | 단일 worker, 짧은 처리 시간. enqueued 동안에는 "처리 중"으로 간주. processing 추가 시 race condition만 늘어남. |
| `raw_event_id` 전송 채널 | `RawEvent` Pydantic 스키마에 `raw_event_id: Optional[str] = None` 추가, stream payload에 같은 키로 직렬화 | 신규 payload 키 1개만 추가. Optional이므로 STEP 003-007의 sample raw_event는 정상 동작 (backward compat). |
| status update 경로 | `PATCH /api/admin/raw-events/{raw_event_id}/status` 신규 + `raw_event_service.update_status()` 신규 | 기존 admin prefix 일관성. backend 단일 write boundary 유지 (CLAUDE.md). |
| status 조회 경로 | `GET /api/admin/raw-events/{raw_event_id}` 신규 (smoke 폴링용) | 기존 `/api/events`로는 raw_event 단위 status 폴링 불가. PATCH와 짝. `GET /api/admin/raw-events`(목록)는 STEP 008B/009로 연기. |
| event_card linkage | `raw_events.event_card_id UUID NULL` 컬럼 추가 + Alembic 0003 | `metadata_json`에 묻지 않고 1급 컬럼으로. JOIN/디버깅 용이. nullable이라 기존 row와 호환. |
| agent-worker 통보 방식 | 동기 `httpx.Client.patch(backend, ...)` 호출 + 실패 시 warn log only (재시도 없음) | 기존 `publish_card`도 동일 패턴. 본격 retry는 STEP 008B. |
| LangSmith | runtime auto-init helper(`backend/app/core/observability.py` 신규) — `LANGSMITH_TRACING=true`이면 환경 wiring, 아니면 no-op | LangChain `LANGCHAIN_*` 환경변수 자동 매핑. 실전송 검증은 `RUN_LANGSMITH_SMOKE=1` opt-in only. |

---

## 비범위 (절대 하지 않음)

- OpenSearch / Next.js UI / 검색 UI
- DART / SEC / YouTube / Reddit / Web crawler
- `processing` 중간 상태 도입
- retry/DLQ/circuit breaker 본격 구현
- LangSmith dashboard 셋업, span 커스텀 메타데이터 시스템
- admin endpoint token 인증 (STEP 008C)
- `GET /api/admin/raw-events` 페이징 목록 (STEP 008B/009)
- backend 자기 호출용 새 internal stream

## 절대 금지

- `Remove-Item`, `rm`, `del`, `rmdir`, `git reset --hard`, `git clean -fdx`
- `git push` (전 변형)
- `docker volume rm`, `docker compose down -v`, `docker system prune -af`
- `.env` 실 키 값 출력. `LANGSMITH_API_KEY` 길이만 redacted_env_status로
- LangSmith 실전송을 기본 테스트에 포함 (반드시 `RUN_LANGSMITH_SMOKE=1` 게이트)
- codex worktree 파일을 claude에서 직접 수정

---

## raw_events.status 라이프사이클

```
RSS collector → POST /api/admin/raw-events
   pg_insert ON CONFLICT DO NOTHING
   status="collected"
        │
        ├─ enqueue success (XADD)
        │      └─ status="enqueued", enqueued_msg_id=...
        │             │
        │             ├─ agent pipeline success → backend upsert success
        │             │      └─ PATCH /api/admin/raw-events/{id}/status
        │             │             status="processed", event_card_id=<uuid>,
        │             │             processed_at=now()
        │             │
        │             └─ agent pipeline 예외 또는 upsert 실패
        │                    └─ PATCH ... status="failed",
        │                           error_reason=<sanitized snippet>,
        │                           processed_at=now()
        │
        └─ XADD 실패 (raw_event_service)
               └─ status="failed", error_reason="xadd_failed: ..."   (신규 — 기존엔 status=collected 잔존)
```

**기존 의미 보존**: `collected`, `enqueued`의 의미는 변경 없음. `processed`/`failed`만 추가. STEP 007의 회귀 0.

**전이 규칙**: backend `raw_event_service.update_status()`가 단일 진입점. 잘못된 전이(processed → collected 등)는 거부하지 않음 — skeleton 단계에서 단순성 우선, 가드는 STEP 008B에서 검토.

---

## raw_event_id 전달 경로

```
raw_event_service.create_raw_event()
  └─ row.id (UUID)
       └─ RawEvent(..., raw_event_id=str(row.id))   ← schemas/events.py 신규 Optional 필드
            └─ enqueue_raw_event(raw)
                 └─ XADD stream:raw_events  payload["raw_event_id"]=str(row.id)
                      └─ workers/queue/consumer.py  fields["raw_event_id"] propagate
                           └─ workers/pipelines/ingest_pipeline.py  to_agent payload 동일 키 forward
                                └─ agents/agent_worker.py  RawEvent(..., raw_event_id=fields.get("raw_event_id"))
                                     └─ EventProcessingGraph.run(raw_event)
                                          └─ EventState["raw_event_id"] = raw_event.raw_event_id
                                               └─ pipeline 종료 후 agent_worker에서 status update PATCH 호출
```

**Backward compat**: `raw_event_id`가 없는 payload(legacy sample, 기존 test fixture)는 `EventState["raw_event_id"]=None`. agent_worker는 None이면 status update 호출을 skip하고 warn log만 남긴다.

---

## 신규 / 수정 파일

### 신규

| 경로 | 목적 |
|---|---|
| `backend/alembic/versions/0003_raw_events_event_card_link.py` | `event_card_id UUID NULL` 컬럼 + `processed_at TIMESTAMPTZ NULL` 컬럼 추가, FK 없음(skeleton) |
| `backend/app/core/observability.py` | `setup_langsmith()` — `LANGSMITH_TRACING=true`이면 `LANGCHAIN_TRACING_V2/ENDPOINT/API_KEY/PROJECT` 환경 wiring + 로그. 아니면 no-op |
| `backend/tests/test_raw_event_status_api.py` | PATCH/GET endpoint unit (5 케이스) |
| `agents/tests/test_agent_worker_status.py` | agent_worker가 성공/실패/raw_event_id 부재 케이스에서 PATCH 호출하는지 unit |
| `workers/tests/test_stream_payload_compat.py` | producer/consumer/ingest forward에서 raw_event_id 전파 + 부재 시 backward compat 단위 |
| `tests/smoke/test_raw_event_lifecycle.py` | fixture RSS collect → enqueued → processed 폴링 검증. mock LLM 실패 주입 케이스로 failed 폴링 |
| `docs/OBSERVABILITY.md` | LangSmith setup, tracing skeleton, runtime activation, opt-in smoke |
| `plans/008A_RAW_EVENT_LINKAGE_OBSERVABILITY_PLAN.md` | 본 plan 영구 사본 |
| `plans/008A_RAW_EVENT_LINKAGE_OBSERVABILITY_REPORT.md` | 실행 보고 |

### 수정

| 경로 | 변경 |
|---|---|
| `backend/app/models/raw_event.py` | `event_card_id Column(UUID, nullable=True)`, `processed_at Column(DateTime(timezone=True), nullable=True)` 추가 |
| `backend/app/schemas/raw_events.py` | `RawEventRecord`에 `event_card_id: Optional[str]`, `processed_at: Optional[datetime]` 추가. `RawEventStatusUpdate(status, error_reason?, event_card_id?)` 신규 |
| `backend/app/schemas/events.py` | `RawEvent`에 `raw_event_id: Optional[str] = None` 추가 (마지막 필드, default Optional → wire backward compat) |
| `backend/app/services/raw_event_service.py` | `update_status(session, raw_event_id, status, error_reason?, event_card_id?)` 신규. XADD 실패 시 `status="failed", error_reason="xadd_failed: ..."` UPDATE 추가 (현재 로그만 남기는 부분 — `raw_event_service.py:107-108`) |
| `backend/app/api/admin.py` | `PATCH /raw-events/{raw_event_id}/status`, `GET /raw-events/{raw_event_id}` 추가 |
| `backend/app/main.py` 또는 lifespan | `setup_langsmith()` 호출 (startup 1회) |
| `workers/queue/producer.py` | `enqueue_raw_event` payload에 `raw_event_id` 키 추가 (raw.raw_event_id가 None이면 빈 문자열로 — 소비측 normalize) |
| `workers/queue/consumer.py` | `fields.get("raw_event_id")` propagate (소비측 변경 없을 수도 있음 — fields dict 그대로 forward 중인지 확인) |
| `workers/pipelines/ingest_pipeline.py` | to_agent payload에 `raw_event_id` forward (`ingest_pipeline.py:26-33`) |
| `agents/state/event_state.py` | `raw_event_id: Optional[str] = None` 필드 추가 |
| `agents/graphs/event_processing_graph.py` | `run(raw_event)` 초기 state에 `raw_event_id=raw_event.raw_event_id` 주입 (`event_processing_graph.py:54-71`) |
| `agents/agent_worker.py` | graph 성공 후 `_notify_status(raw_event_id, "processed", event_card_id=card.id)` 호출. 예외 catch 후 `_notify_status(raw_event_id, "failed", error_reason=str(e)[:500])`. `raw_event_id is None`이면 skip + warn |
| `docs/EVENT_SCHEMA.md` | `RawEvent` 표에 `raw_event_id` 행, `raw_events` 표에 `event_card_id`/`processed_at` 행, status 주석 "STEP 008A 완료"로 갱신 |
| `docs/API_CONTRACT.md` | `PATCH /api/admin/raw-events/{id}/status`, `GET /api/admin/raw-events/{id}` 섹션 추가 |
| `docs/ARCHITECTURE.md` | raw_event_id 흐름 화살표 추가, status update PATCH 경로 다이어그램 반영 |
| `docs/COLLECTOR_DESIGN.md` | status 라이프사이클 다이어그램 갱신 |
| `docs/TRD.md` | STEP 008A 컴포넌트/env 섹션 추가 |
| `docs/LLM_AGENT_DESIGN.md` | EventState 필드 표에 `raw_event_id` 추가 (파일 존재 시) |
| `.env.example` | `RUN_LANGSMITH_SMOKE` 주석 1줄 추가. production 코드에 test-only env toggle은 추가하지 않음 (사용자 결정: failed 케이스는 unit monkeypatch만) |

---

## 핵심 코드 변경 스니펫

### `backend/app/schemas/events.py` (RawEvent 확장)
```python
class RawEvent(BaseModel):
    source: str
    url: str
    fetched_at: datetime
    raw_text: str
    raw_metadata: dict = Field(default_factory=dict)
    raw_event_id: Optional[str] = None   # STEP 008A: backward-compat optional
```

### `backend/app/services/raw_event_service.py` (XADD 실패 시 failed 전이)
```python
try:
    enqueued_msg_id = await asyncio.to_thread(enqueue_raw_event, raw_event)
except Exception as exc:
    logger.warning("xadd_failed raw_event_id=%s reason=%s", row.id, str(exc)[:200])
    await session.execute(
        update(RawEventORM).where(RawEventORM.id == row.id)
        .values(status="failed", error_reason=f"xadd_failed: {str(exc)[:480]}")
    )
    await session.commit()
    return RawEventCreateResponse(record=..., is_duplicate=False, enqueued_msg_id=None)
```

### `backend/app/services/raw_event_service.py` (update_status 신규)
```python
async def update_status(
    session, raw_event_id: str, status: str,
    error_reason: Optional[str] = None,
    event_card_id: Optional[str] = None,
) -> RawEventRecord:
    values = {"status": status, "updated_at": func.now()}
    if status in ("processed", "failed"):
        values["processed_at"] = func.now()
    if error_reason:
        values["error_reason"] = error_reason[:500]
    if event_card_id:
        values["event_card_id"] = event_card_id
    result = await session.execute(
        update(RawEventORM).where(RawEventORM.id == raw_event_id).values(**values)
    )
    await session.commit()
    if result.rowcount == 0:
        raise NoResultFound(f"raw_event_id={raw_event_id} not found")
    row = (await session.execute(select(RawEventORM).where(RawEventORM.id == raw_event_id))).scalar_one()
    return RawEventRecord.model_validate(row)
```

### `agents/agent_worker.py` (성공/실패 통보)
```python
def _notify_status(raw_event_id, status, error_reason=None, event_card_id=None):
    if raw_event_id is None:
        logger.warning("raw_event_id absent — status update skipped status=%s", status)
        return
    try:
        httpx.patch(
            f"{BACKEND_URL}/api/admin/raw-events/{raw_event_id}/status",
            json={"status": status, "error_reason": error_reason, "event_card_id": event_card_id},
            timeout=10,
        )
    except Exception as exc:
        logger.warning("raw_event status update failed id=%s reason=%s", raw_event_id, str(exc)[:200])

# 기존 처리 루프
try:
    card = graph_run(raw)
    publish_card(card)
    _notify_status(raw.raw_event_id, "processed", event_card_id=str(card.id))
except Exception as exc:
    logger.exception("agent pipeline failed")
    _notify_status(raw.raw_event_id, "failed", error_reason=str(exc)[:500])
finally:
    r.xack(STREAM, GROUP, msg_id)
```

### `backend/app/core/observability.py` (skeleton)
```python
def setup_langsmith():
    settings = get_settings()
    flag = (settings.LANGSMITH_TRACING or "").lower()
    if flag not in ("1", "true", "yes"):
        logger.info("LangSmith tracing disabled (LANGSMITH_TRACING unset/false)")
        return
    # LangChain reads env vars; map our settings to LangChain's expected names
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    if settings.LANGSMITH_ENDPOINT:
        os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    if settings.LANGSMITH_PROJECT:
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
    logger.info("LangSmith tracing enabled project=%s", settings.LANGSMITH_PROJECT or "<default>")
```

---

## Alembic 0003

```python
revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"

def upgrade():
    op.add_column("raw_events", sa.Column("event_card_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("raw_events", sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_raw_events_event_card_id", "raw_events", ["event_card_id"])
    op.create_index("ix_raw_events_processed_at", "raw_events", ["processed_at"])

def downgrade():
    op.drop_index("ix_raw_events_processed_at", table_name="raw_events")
    op.drop_index("ix_raw_events_event_card_id", table_name="raw_events")
    op.drop_column("raw_events", "processed_at")
    op.drop_column("raw_events", "event_card_id")
```

FK는 만들지 않음 — `event_cards.id`가 정의되어 있으나 raw_event는 event_card 없이도 존재 가능. 향후 STEP 008B에서 검토.

---

## 테스트 전략

### Unit (backend) — `backend/tests/test_raw_event_status_api.py`
1. PATCH processed: status/event_card_id/processed_at 저장 + 200
2. PATCH failed + error_reason: error_reason truncate(500자)
3. PATCH unknown raw_event_id: 404 (NoResultFound → HTTPException)
4. GET 존재: 200 + RawEventRecord
5. GET 미존재: 404

### Unit (agent) — `agents/tests/test_agent_worker_status.py`
1. graph 성공: `httpx.patch` mock — status="processed" + event_card_id 전송
2. graph 예외: status="failed" + error_reason
3. `raw_event_id=None`: PATCH 미호출 + warn log
4. PATCH 자체 실패: warn log만, xack는 정상 수행

### Unit (worker) — `workers/tests/test_stream_payload_compat.py`
1. producer가 `raw_event_id` 키를 XADD payload에 포함
2. producer가 raw.raw_event_id=None이면 빈 문자열로 포함
3. consumer가 `raw_event_id`를 fields dict에 보존
4. ingest_pipeline이 to_agent payload에 forward
5. legacy payload (raw_event_id 키 없음) → `RawEvent(raw_event_id=None)` 정상

### Smoke — `tests/smoke/test_raw_event_lifecycle.py`
1. fixture RSS collect → `/api/admin/raw-events/{id}` 폴링 30s → status="processed" + event_card_id 존재
2. `_poll_status(deadline=30s, interval=2s)` 패턴 (`tests/smoke/test_persistence.py:25-37` 차용)

**failed 케이스 e2e는 작성하지 않음** (사용자 결정). failed 전이는 다음 unit test로만 검증:
- `agents/tests/test_agent_worker_status.py`의 "graph 예외" 케이스 — `graph_run`을 monkeypatch로 예외 raise하여 PATCH failed 호출 검증
- `backend/tests/test_raw_event_status_api.py`의 "PATCH failed + error_reason" 케이스 — service layer까지 단위 검증
- `backend/tests/test_raw_events_api.py`(기존)에 XADD 실패 시 status="failed" 전이 케이스 1개 추가

### 회귀 게이트 (필수 PASS, 0 diff)
- `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_vector_search.py tests/smoke/test_rss_collector_fixture.py -v`
- `RawEvent` 스키마: `raw_event_id` Optional default None이므로 기존 payload 무효화 없음 — git diff로 확인
- `EventProcessingGraph.run()` signature 불변
- `pytest backend/tests agents/tests workers/tests -v`

### LangSmith opt-in
- `RUN_LANGSMITH_SMOKE=1` smoke 본 STEP에서 작성 안 함. `docs/OBSERVABILITY.md`에 활성화 방법만 기록.

---

## 실행 순서

### Phase 1 — 정적 점검
```powershell
git status; git log --oneline -8; git worktree list
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml config --quiet
```

### Phase 2 — Alembic 0003 + ORM/Schema
1. `0003_raw_events_event_card_link.py` 작성
2. `models/raw_event.py` 컬럼 추가
3. `schemas/raw_events.py` `RawEventRecord` 필드 + `RawEventStatusUpdate` 신규
4. `schemas/events.py` `RawEvent.raw_event_id` 추가
5. `docker compose run --rm backend alembic upgrade head` (0002 → 0003)
6. `alembic downgrade -1 && alembic upgrade head` roundtrip
7. `psql \d raw_events`로 2개 신규 컬럼 + 2개 신규 index 확인
8. event_cards / 기존 raw_events 데이터 보존 확인

### Phase 3 — Backend service + API
1. `raw_event_service.update_status()` 작성
2. `raw_event_service.create_raw_event()` XADD 실패 분기 패치 (failed 전이 추가)
3. `api/admin.py` PATCH/GET 라우트 추가
4. `backend/tests/test_raw_event_status_api.py` 작성 (5 케이스)
5. `pytest backend/tests/test_raw_event_status_api.py -v` PASS

### Phase 4 — Stream payload propagation
1. `producer.py` payload에 raw_event_id 추가
2. `consumer.py` fields dict propagate 확인
3. `ingest_pipeline.py:26-33` forward에 raw_event_id 추가
4. `workers/tests/test_stream_payload_compat.py` 작성 (5 케이스)
5. `pytest workers/tests -v` PASS

### Phase 5 — Agent state + worker 통보
1. `agents/state/event_state.py` `raw_event_id` 필드
2. `agents/graphs/event_processing_graph.py:54-71` 초기 state 주입
3. `agents/agent_worker.py` `_notify_status` helper + 성공/실패 분기
4. `agents/tests/test_agent_worker_status.py` 작성 (4 케이스)
5. `pytest agents/tests -v` PASS

### Phase 6 — Observability skeleton
1. `backend/app/core/observability.py` 작성
2. `backend/app/main.py` lifespan 또는 startup에 `setup_langsmith()` 호출
3. `LANGSMITH_TRACING=false`(기본) 상태에서 backend 기동 정상 확인 (로그 1줄 "disabled")
4. `docs/OBSERVABILITY.md` 작성

### Phase 7 — Build + e2e
1. `docker compose build backend worker agent-worker`
2. `docker compose up -d` 8개 컨테이너 healthy
3. `curl http://localhost:8000/health`
4. fixture RSS collect → `_poll_status` 30s → processed 확인
5. (failed 케이스는 e2e 미수행 — unit only)

### Phase 8 — 회귀 게이트
1. `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_vector_search.py tests/smoke/test_rss_collector_fixture.py -v` PASS
2. `pytest backend/tests agents/tests workers/tests -v` PASS

### Phase 9 — 문서 + plan/report
1. `docs/EVENT_SCHEMA.md`, `API_CONTRACT.md`, `ARCHITECTURE.md`, `COLLECTOR_DESIGN.md`, `TRD.md`, `LLM_AGENT_DESIGN.md` 갱신
2. `docs/OBSERVABILITY.md` 신규
3. `plans/008A_RAW_EVENT_LINKAGE_OBSERVABILITY_PLAN.md`, `..._REPORT.md` 작성

### Phase 10 — Commit
- Commit A: `feat(step-008a): add raw event processing linkage and status lifecycle`
- Commit B: `docs(step-008a): observability skeleton + plan/report snapshot`
- `git push` 미실행

### Phase 11 — Codex sync
```powershell
git -C C:/Users/computer/Desktop/business/codex status --short
git -C C:/Users/computer/Desktop/business/codex fetch
git -C C:/Users/computer/Desktop/business/codex merge --ff-only main
# ff-only 실패 시 --no-ff merge (충돌 시 abort + 사용자 보고)
```

---

## 검증 체크리스트

- [ ] `docker compose config --quiet` PASS
- [ ] alembic 0002 → 0003 clean
- [ ] alembic downgrade -1 + upgrade head roundtrip clean
- [ ] event_cards / raw_events 기존 데이터 보존
- [ ] `RawEvent.raw_event_id` Optional 추가 — 기존 sample raw_event 폴링 정상
- [ ] `producer.py` payload에 raw_event_id 키 포함
- [ ] `ingest_pipeline.py` to_agent forward에 raw_event_id 포함
- [ ] `EventState["raw_event_id"]` graph.run() 진입 시 주입
- [ ] agent-worker 성공 → PATCH processed + event_card_id 저장
- [ ] agent-worker 실패 → PATCH failed + error_reason 저장
- [ ] `raw_event_id=None` legacy payload → PATCH skip + warn log
- [ ] backend XADD 실패 → status=failed + error_reason 저장 (raw_event_service 분기)
- [ ] PATCH /raw-events/{id}/status 3 케이스 PASS
- [ ] GET /raw-events/{id} 2 케이스 PASS
- [ ] worker/agent/backend unit 전부 PASS
- [ ] fixture lifecycle smoke processed 폴링 PASS (failed는 unit only)
- [ ] 기존 e2e smoke (pipeline/persistence/vector/rss_fixture) 회귀 0
- [ ] `setup_langsmith()` LANGSMITH_TRACING=false에서 no-op (log 1줄)
- [ ] `LANGSMITH_API_KEY` 값이 어떤 로그/응답에도 노출되지 않음
- [ ] 8개 컨테이너 Up/healthy
- [ ] docs 7개 갱신/신규 + plan/report
- [ ] Commit A/B 성공, `.env`/`.venv`/`node_modules`/RSS 원문 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료
- [ ] WARNING/BLOCKED/UNKNOWN 명시
- [ ] STEP 008B/009 제안 포함

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | `RawEvent.raw_event_id=Optional` 추가가 Pydantic 직렬화 영향 | 중간 | 마지막 필드. `model_dump()` 키 추가만 발생. 기존 consumer는 새 키 무시 |
| R2 | XADD 성공 후 backend가 status="enqueued" UPDATE 전에 backend 죽으면 status="collected"+enqueued_msg_id=NULL 잔존 | 낮음 | STEP 007부터 존재한 split-brain. dedup이 재시도 안전. STEP 008B reconciler |
| R3 | agent-worker가 PATCH 호출 실패 시 raw_event 영원히 enqueued 잔존 | 중간 | warn log + STEP 008B reconciler. xack는 정상 — 무한 재시도 회피 우선 |
| R4 | agent_worker에서 동기 `httpx.patch` 호출이 stream 폴링 블록 | 낮음 | 단일 worker, timeout=10s. STEP 008B async 전환 검토 |
| R5 | LangSmith 환경 wiring이 LangChain 미설치 환경에서 부작용 | 낮음 | `os.environ` 설정만 — 미설치여도 noop. 실 활성화는 LangChain runtime이 알아서 |
| R6 | failed 전이 검증 — e2e 미수행 | 낮음 | 사용자 결정: unit monkeypatch만 (production 코드에 test-only env toggle 추가 회피). agent unit + backend service unit + XADD 실패 분기 unit으로 3중 검증 |
| R7 | smoke 폴링 30s가 LLM 실호출 시 부족 | 중간 | mock 기본. opt-in OpenAI smoke는 본 STEP 회귀 게이트에서 제외 |
| U1 | `event_card_id`를 FK로 만들 가치 | — | 본 STEP은 nullable column only. STEP 008B 검토 |
| U2 | `processing` 중간 상태 도입 | — | 단일 worker라 불필요 판단. 멀티 worker 시 STEP 008B 검토 |
| U3 | reconciler (raw_events에서 enqueued 오래된 row 회수) | — | STEP 008B |
| U4 | admin endpoint 인증 | — | STEP 008C |

---

## 다음 STEP 제안

1. **STEP 008B** — agent-worker async 전환 + reconciler(stuck enqueued 회수) + retry/DLQ 1차 + `processing` 상태 도입 검토
2. **STEP 008C** — admin endpoint token 인증 + `GET /api/admin/raw-events?status=` 페이징 목록
3. **STEP 009** — Next.js `/events` UI + `/raw-events` admin UI + collector_sources 테이블
4. **STEP 010** — DART/SEC collector + vector dedup threshold + entity linking LLM 전환
