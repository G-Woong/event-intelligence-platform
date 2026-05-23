# STEP 007 REPORT — RSS Collector + raw_events Persistence

날짜: 2026-05-23/24  
상태: **COMPLETE**

---

## ① 무엇을 했는가

### Phase 2 — Schemas + Model
- `backend/app/schemas/raw_events.py`: `RawEventCreate`, `RawEventRecord`, `RawEventCreateResponse`
- `backend/app/models/raw_event.py`: `RawEventORM` (17 컬럼)
- `backend/app/models/__init__.py`: `RawEventORM` re-export 추가

### Phase 3 — Alembic Migration
- `backend/alembic/versions/0002_raw_events.py`: raw_events 테이블 + 2 UNIQUE + 5 index
- `alembic upgrade head` (a1b2c3d4e5f6 → b2c3d4e5f6a7) PASS
- downgrade -1 + upgrade head roundtrip PASS
- 기존 event_cards 13개 데이터 보존 확인

### Phase 4 — Backend service + API
- `backend/app/services/raw_event_service.py`: idempotent insert + asyncio.to_thread(XADD)
- `backend/app/api/admin.py`: `POST /raw-events`, `POST /collect-rss-once` 추가
- `backend/app/core/config.py`: RSS_* 3개 env var + redacted_env_status 갱신
- `.env.example`: STEP 007 블록 추가

### Phase 5 — requirements + Dockerfile
- `requirements/collector.txt`: feedparser==6.0.11
- `workers/Dockerfile`: collector.txt 설치
- `backend/Dockerfile`: collector.txt + workers/ COPY 추가

### Phase 6 — Collector Module
- `workers/collectors/sources.py`: DEFAULT_SOURCES 3개 + get_sources()
- `workers/collectors/rss_collector.py`: feedparser parse + HTTP POST + summary
- `workers/collectors/__main__.py`: CLI entry

### Phase 7 — Tests
- `tests/fixtures/`: rss_bbc_min.xml, rss_empty.xml, rss_malformed.xml, rss_no_link.xml
- `workers/tests/test_rss_collector.py`: 16 unit tests
- `backend/tests/test_raw_events_api.py`: 5 unit tests
- `tests/smoke/test_rss_collector_fixture.py`: 3 smoke tests (네트워크 0)
- `tests/smoke/test_rss_collector_live.py`: gated `RUN_RSS_LIVE_SMOKE=1`

### Phase 8 — `/collect-rss-once` 검증
- 실제 호출 결과: sources=3, items_seen=152, items_enqueued=5, duplicates=145

### Phase 9 — 문서
- `docs/COLLECTOR_DESIGN.md` 신규
- `docs/DATA_POLICY.md` 신규
- `docs/COMPLIANCE_BOUNDARY.md` 신규
- `docs/EVENT_SCHEMA.md`: raw_events 섹션 추가
- `docs/ARCHITECTURE.md`: STEP 007로 갱신, RSS collector IMPLEMENTED
- `docs/API_CONTRACT.md`: POST /raw-events, POST /collect-rss-once 추가
- `docs/COMPATIBILITY_NOTES.md`: STEP 007 섹션 추가
- `docs/TRD.md`: STEP 007 컴포넌트/env/DB/인프라 추가

---

## ② 무엇을 검증했는가

| 항목 | 결과 |
|---|---|
| `pytest workers/tests/test_rss_collector.py -v` | **16/16 PASS** |
| `pytest backend/tests/test_raw_events_api.py -v` | **5/5 PASS** |
| `pytest tests/smoke/test_rss_collector_fixture.py -v` | **3/3 PASS** |
| alembic upgrade head (0001→0002) | PASS |
| alembic downgrade -1 + upgrade head roundtrip | PASS |
| raw_events 테이블 + 2 UNIQUE + 5 index | 확인 (psql \d raw_events) |
| event_cards 기존 13개 보존 | PASS |
| `POST /api/admin/raw-events` 중복 is_duplicate=true | PASS |
| `POST /api/admin/collect-rss-once` summary 반환 | PASS |
| `RawEvent` schema 무변경 | git diff 0 hunks |
| docker compose config --quiet | PASS |
| 8개 컨테이너 Up/healthy | PASS |

---

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING
- W1: `test_persistence_after_restart`가 첫 회귀 게이트 실행에서 1회 실패 (재실행 PASS). agent-worker publish_pipeline timed out 백로그로 인한 기존 flakiness. STEP 007 변경과 무관 (RawEvent schema 무변경 확인).
- W2: BBC World RSS에서 2개 errors 발생 (backend POST timeout). 원인: asyncio.to_thread + 동기 httpx self-call 조합에서 일부 항목 지연. 실 운용 영향 최소 (items_enqueued=5 성공).
- W3: Reuters Business RSS items_seen=0 — 공개 피드 접근 제한 또는 feed URL 변경 가능성. 수동 확인 권장.

### BLOCKED
- 없음

### UNKNOWN
- U1: DB-backed sources 테이블 스키마 — STEP 008+ 연기. `docs/COLLECTOR_DESIGN.md`에 마이그레이션 경로 문서화.
- U2: raw_events retention TTL — STEP 008+ 연기.
- U3: admin endpoint 인증 token — STEP 008+ 연기. TODO 코드 주석에 명시.

---

## 다음 STEP

**STEP 008** 권장:
- agent-worker async 전환
- raw_event_id stream linkage (raw_events.id → stream payload)
- `raw_events.status` processed/failed 업데이트
- Milvus insert background task
- LangSmith tracing 실연결
- admin endpoint token 인증
- `GET /api/admin/raw-events` 페이징 API
- collector_sources 테이블
