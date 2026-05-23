# STEP 008A — 실행 보고

실행일: 2026-05-24

## 1. 무엇을 했는가

### Phase 2 — Alembic 0003 + ORM/Schema
- `backend/alembic/versions/0003_raw_events_event_card_link.py` 작성 (revision: c3d4e5f6a7b8)
- `raw_events` 테이블에 `event_card_id UUID NULL`, `processed_at TIMESTAMPTZ NULL` 컬럼 추가
- `ix_raw_events_event_card_id`, `ix_raw_events_processed_at` 인덱스 추가
- `models/raw_event.py` ORM 컬럼 추가
- `schemas/raw_events.py` `RawEventRecord`에 신규 필드 + `RawEventStatusUpdate` 스키마 추가
- `schemas/events.py` `RawEvent`에 `raw_event_id: Optional[str] = None` 추가

### Phase 3 — Backend service + API
- `raw_event_service.update_status()` 신규 구현
- `raw_event_service.get_raw_event()` 신규 구현
- `raw_event_service.create_raw_event()` XADD 실패 시 `status="failed"` 전이 추가 (기존: log만)
- `api/admin.py` `PATCH /raw-events/{id}/status`, `GET /raw-events/{id}` 라우트 추가
- `backend/tests/test_raw_event_status_api.py` 5케이스 작성 → PASS
- `backend/tests/test_raw_events_api.py` XADD 실패 failed 전이 케이스 추가 → PASS

### Phase 4 — Stream payload propagation
- `workers/queue/producer.py` payload에 `raw_event_id` 키 추가
- `workers/pipelines/ingest_pipeline.py` `raw_event_id` forward + `RawEvent` 생성 시 주입
- `workers/tests/test_stream_payload_compat.py` 5케이스 작성 → PASS

### Phase 5 — Agent state + worker 통보
- `agents/state/event_state.py` `raw_event_id: Optional[str]` 필드 추가
- `agents/graphs/event_processing_graph.py` 초기 state에 `raw_event_id` 주입
- `agents/agent_worker.py` `_notify_status()` helper 추가, 성공/실패 분기 + `finally: xack`
- `agents/tests/test_agent_worker_status.py` 4케이스 작성 → PASS

### Phase 6 — Observability skeleton
- `backend/app/core/observability.py` `setup_langsmith()` 구현
- `backend/app/main.py` lifespan에 `setup_langsmith()` 호출 추가
- `docs/OBSERVABILITY.md` 신규 작성

### Phase 7/8 — Build + e2e + 회귀 게이트
- backend/worker/agent-worker 이미지 재빌드 (`--no-cache`)
- 8개 컨테이너 Up/healthy 확인
- `curl /health` → `{"status":"ok","redis":"ok","milvus":"ok","postgres":"ok"}`
- lifecycle smoke test PASS (6.3s)
- 기존 smoke 회귀 게이트 (pipeline, persistence, rss_fixture) PASS
- unit test 전체 76 passed, 5 skipped (opt-in)

### Phase 9 — 문서
- `docs/EVENT_SCHEMA.md`: raw_event_id 행, event_card_id/processed_at 행 추가, status 주석 갱신
- `docs/API_CONTRACT.md`: PATCH/GET 섹션 추가
- `docs/COLLECTOR_DESIGN.md`: 아키텍처 다이어그램 갱신, XADD 실패 처리 갱신
- `docs/TRD.md`: STEP 008A 컴포넌트/환경변수/DB/status lifecycle 섹션 추가
- `docs/OBSERVABILITY.md`: 신규 (LangSmith 활성화 가이드)
- `.env.example`: `RUN_LANGSMITH_SMOKE` 주석 추가

## 2. 무엇을 검증했는가

| 검증 항목 | 결과 |
|---|---|
| alembic 0002 → 0003 clean | PASS |
| alembic downgrade -1 + upgrade head roundtrip | PASS |
| `event_card_id`, `processed_at` 컬럼 + 2개 인덱스 추가 | PASS |
| `RawEvent.raw_event_id` Optional 추가 — 기존 sample 정상 | PASS |
| `producer.py` payload에 raw_event_id 포함 | unit PASS |
| `ingest_pipeline.py` to_agent forward에 raw_event_id | unit PASS |
| legacy payload(raw_event_id 없음) → `RawEvent(raw_event_id=None)` | unit PASS |
| PATCH processed: status/event_card_id/processed_at 저장 200 | unit PASS |
| PATCH failed + error_reason | unit PASS |
| PATCH unknown id → 404 | unit PASS |
| GET 존재 → 200 | unit PASS |
| GET 미존재 → 404 | unit PASS |
| agent-worker 성공 → PATCH processed + event_card_id 전송 | unit PASS |
| agent-worker 실패 → PATCH failed + error_reason | unit PASS |
| raw_event_id=None → PATCH skip + warn log | unit PASS |
| PATCH 자체 실패 → warn only, xack 정상 | unit PASS |
| XADD 실패 → status=failed + error_reason | unit PASS |
| lifecycle smoke: collect → enqueued → processed 폴링 | smoke PASS (6.3s) |
| 기존 smoke 회귀 (pipeline/persistence/rss_fixture) | PASS |
| setup_langsmith() LANGSMITH_TRACING=false → no-op (log 1줄) | 기동 로그 확인 |
| LANGSMITH_API_KEY 값 로그 미노출 | 확인 |
| 8개 컨테이너 Up/healthy | PASS |
| unit 전체 76 passed, 5 skipped (opt-in) | PASS |

## 3. WARNING / BLOCKED / UNKNOWN

- WARNING: Alembic migration 파일을 Docker 컨테이너 빌드 이미지에 포함하려면 `docker cp`가 필요함. 현재 workaround로 운영. Dockerfile에 migration 파일 빌드 포함 여부는 STEP 008B에서 검토.
- UNKNOWN: `processing` 중간 상태 도입 필요성 — 멀티 worker 환경 시 STEP 008B에서 재검토.
- UNKNOWN: `event_card_id` FK 제약 도입 — 현재 nullable column only. STEP 008B 검토.

## 다음 STEP 제안

1. **STEP 008B** — agent-worker async 전환 + reconciler(stuck enqueued 회수) + retry/DLQ 1차 + Dockerfile migration 포함 정책
2. **STEP 008C** — admin endpoint token 인증 + `GET /api/admin/raw-events?status=` 페이징 목록
3. **STEP 009** — Next.js `/events` UI + `/raw-events` admin UI + collector_sources 테이블
4. **STEP 010** — DART/SEC collector + vector dedup threshold + entity linking LLM 전환
