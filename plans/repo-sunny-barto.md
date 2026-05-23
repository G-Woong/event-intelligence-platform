# STEP 007 — RSS Collector + raw_events Persistence + Alembic Migration Skeleton

## Context

STEP 003~006에서 LangGraph + LLMClient + Postgres + Milvus + Docker e2e가 완성됐지만,
파이프라인은 항상 **외부에서 enqueue된 RawEvent**를 가정한다. 실제 외부 소스에서 사건을
가져오는 입구(crawler/collector)는 부재 상태 — `docs/ARCHITECTURE.md:142-144`도
"crawler collector → MISSING → STEP 007"로 명시.

STEP 007의 목표는 **외부 정보 수집의 첫 입구를 RSS로 뚫는 것**:

```
RSS feed (feedparser)
  → workers/collectors/rss_collector.py
  → POST /api/admin/raw-events  (backend admin API)
     ├─ raw_events 테이블 idempotent insert (content_hash UNIQUE)
     ├─ Redis Stream XADD to stream:raw_events
     └─ status: collected → enqueued
  → 기존 worker → ingest_pipeline → stream:to_agent
  → agent-worker → LangGraph → FinalEventCard → Postgres + Milvus
```

DART/SEC/Web/Social crawler, Playwright/Selenium, 본문 크롤링, 고급 dedup,
OpenSearch, Next.js UI, agent 측 raw_events.status 업데이트는 모두 본 STEP 범위 외.

---

## 사용자 확정 결정 (Q1-Q3)

| 결정 항목 | 선택 |
|---|---|
| raw_events.status 라이프사이클 | **수집측만 업데이트**: collected → enqueued까지 collector/backend가 갱신. agent pipeline은 raw_events 미인지. stream payload(5필드) 무변경 → STEP 003-006 회귀 0건. processed/failed는 STEP 008에서 raw_event_id linkage와 함께 도입. |
| DEFAULT_SOURCES + 라이브 fetch 정책 | **공개 피드 2-3개 + fixture-first**: BBC World, Reuters, YNA 공개 RSS 하드코딩. 기본 테스트는 모두 `tests/fixtures/*.xml` 기반(네트워크 0). 실 RSS는 `RUN_RSS_LIVE_SMOKE=1`에서만. |
| `POST /api/admin/collect-rss-once` | **포함**: curl 한 번으로 트리거 가능. backend 이미지에도 feedparser 설치. `asyncio.to_thread`로 블로킹 회피. |

---

## 비범위 (절대 하지 않음)

- DART API / SEC EDGAR / YouTube / Reddit / X / 기타 소셜 collector
- Playwright / Selenium / 본문 크롤링 / anti-bot / paywall 우회 / robots 우회
- OpenSearch / Next.js UI / 검색 UI
- 고급 vector dedup / LLM 기반 dedup
- agent-worker 측 raw_events.status 업데이트 (STEP 008로 연기)
- raw_event_id stream linkage (STEP 008로 연기)
- DB-backed source 테이블 (skeleton은 하드코딩, 마이그레이션 경로만 문서화)
- 새 LLM provider / agent graph 노드 추가
- 새 Milvus collection / schema 변경

---

## 절대 금지 (CLAUDE.md 준수)

- `Remove-Item`, `rm`, `del`, `rmdir`, `git reset --hard`, `git clean -fdx`
- `git push` (전 변형)
- `docker volume rm`, `docker compose down -v`, `docker system prune -af`
- `.env` 실값 출력. `OPENAI_API_KEY` 길이만 logger.debug
- 실 RSS 외부 호출 (`RUN_RSS_LIVE_SMOKE=1` 미설정 시)
- codex worktree 안의 파일을 claude에서 직접 수정 (read-only)

---

## raw_events 테이블 설계

### 컬럼

| 컬럼 | 타입 | NULL | 기본값 | 비고 |
|---|---|---|---|---|
| `id` | UUID | NO | Python `uuid.uuid4` | PK |
| `source_type` | VARCHAR(32) | NO | — | `"rss"` (미래: dart/sec/web/social) |
| `source_name` | VARCHAR(128) | NO | — | feed 식별자 (e.g. `bbc_world`) |
| `external_id` | VARCHAR(512) | YES | NULL | RSS `entry.id`/`guid`/`link` fallback |
| `url` | VARCHAR(2048) | NO | — | canonical link |
| `title` | VARCHAR(1024) | YES | NULL | RSS title (length-capped) |
| `raw_text` | TEXT | NO | `''` | summary only — 본문 저장 금지 |
| `published_at` | TIMESTAMPTZ | YES | NULL | `entry.published_parsed` → UTC |
| `collected_at` | TIMESTAMPTZ | NO | `now()` | 수집 시각 |
| `content_hash` | VARCHAR(64) | NO | — | sha256(source_type\|source_name\|external_id\|url\|title\|raw_text) |
| `theme_hint` | VARCHAR(64) | YES | NULL | sources 설정에서 주입 |
| `status` | VARCHAR(16) | NO | `"collected"` | `collected`/`enqueued`/`processed`/`failed` (STEP 007은 앞 2개만 사용) |
| `enqueued_msg_id` | VARCHAR(64) | YES | NULL | Redis XADD msg id |
| `error_reason` | VARCHAR(512) | YES | NULL | failed status 시 |
| `raw_metadata` | JSONB | NO | `'{}'::jsonb` | RSS tags/feed metadata |
| `created_at` | TIMESTAMPTZ | NO | `now()` | |
| `updated_at` | TIMESTAMPTZ | NO | `now()` + onupdate | |

### Unique 제약 (둘 다)
1. `UNIQUE (content_hash)` — 전역 컨텐츠 dedup. 동일 텍스트 재수집 차단.
2. `UNIQUE (source_type, external_id) WHERE external_id IS NOT NULL` — partial unique. 같은 GUID 재게시 차단(web/scrape NULL 대응).

이유: DART/SEC는 stable external_id 강력 / web/social은 약함 → 두 축 모두 필요. 향후 collector 공통 사용 가능.

### Index
- `ix_raw_events_collected_at` DESC
- `ix_raw_events_status`
- `ix_raw_events_source_type`
- `ix_raw_events_published_at` DESC NULLS LAST
- `ix_raw_events_raw_metadata_gin` GIN jsonb_path_ops

### Pydantic 분리
- `RawEvent` (`backend/app/schemas/events.py:9-14`) **불변** — Redis Stream wire contract.
- 신규 `backend/app/schemas/raw_events.py`:
  - `RawEventCreate` (collector → backend 입력)
  - `RawEventRecord` (DB row 표현)
  - `RawEventCreateResponse` (`record + is_duplicate + enqueued_msg_id`)

---

## RSS Collector 설계

### 모듈 구조
```
workers/collectors/__init__.py
workers/collectors/__main__.py            # python -m workers.collectors entry
workers/collectors/rss_collector.py       # run() one-shot
workers/collectors/sources.py             # DEFAULT_SOURCES 하드코딩 리스트
```

### `DEFAULT_SOURCES` (하드코딩, 2-3개)
```python
DEFAULT_SOURCES = [
    {"name": "bbc_world",        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
     "theme_hint": "geopolitics", "enabled": True},
    {"name": "reuters_business", "url": "https://feeds.reuters.com/reuters/businessNews",
     "theme_hint": "macro",       "enabled": True},
    {"name": "yna_economy",      "url": "https://www.yna.co.kr/rss/economy.xml",
     "theme_hint": "macro_kr",    "enabled": True},
]
```

DB-backed source 테이블은 STEP 008+로 연기. `RSS_SOURCES_CONFIG_PATH` env var는 stub.

### RSS item → DB/Stream 매핑
| 대상 | 출처 |
|---|---|
| `source` (stream) | `f"rss:{source_name}"` |
| `source_type` (DB) | `"rss"` |
| `source_name` (DB) | sources config |
| `external_id` (DB) | `entry.id or entry.guid or entry.link` |
| `url` (DB + stream) | `entry.link` |
| `title` (DB) | `entry.title[:1024]` |
| `raw_text` (DB + stream) | `entry.summary` HTML-stripped via regex (no bs4) |
| `published_at` (DB) | `datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)` |
| `fetched_at` (stream) | `datetime.now(timezone.utc)` |
| `content_hash` (DB) | `sha256(f"{source_type}|{source_name}|{external_id or url}|{title or ''}|{raw_text}").hexdigest()` |
| `theme_hint` (DB) | sources config |
| `raw_metadata` (DB + stream) | `{"rss": {"tags": [...], "feed_title": ..., "guid": ...}}` |

### Error 처리
- 네트워크 timeout (`RSS_COLLECTOR_FETCH_TIMEOUT_SEC=15`) → 해당 source 스킵, 로깅, 다음 진행
- `feedparser.bozo=1` → 가능한 entries 살리고 진행
- 빈 feed → info log, 0건 처리
- `entry.link` 없음 → entry 스킵
- backend 5xx → tenacity 1회 재시도
- Redis enqueue fail → row는 `status="collected"` 유지, 응답 `enqueued_msg_id=None`

### CLI
```
python -m workers.collectors                              # = python -m workers.collectors.__main__
docker compose run --rm worker python -m workers.collectors.rss_collector
```
one-shot. 종합 로그 1줄: `{sources, items_seen, items_enqueued, duplicates, errors}`. always-on loop 없음.

---

## Storage Write Path (Backend Admin API)

### 결정: backend `/api/admin/raw-events` 단일 write boundary
- worker는 backend API 호출만. `publish_pipeline.publish_card`와 대칭.
- worker Dockerfile은 `backend/app/models/`/`services/`를 복사하지 않음 → 직접 DB write 불가.
- 단일 제약 위반 처리, 향후 hook 확장 용이.

### 흐름 (backend 측)
```
POST /api/admin/raw-events  (body: RawEventCreate)
  1) pg_insert(RawEventORM).values(...).on_conflict_do_nothing(index_elements=["content_hash"])
  2) commit
  3) SELECT ... WHERE content_hash=:h  → 기존 row인지 신규 row인지 판정
  4) is_duplicate=True 면: response 200, enqueued_msg_id=None, XADD 미실행
     is_duplicate=False 면:
       a) enqueue_raw_event(RawEvent(stream 5필드))  ← 기존 producer 재사용
       b) UPDATE raw_events SET status='enqueued', enqueued_msg_id=:id WHERE id=:row_id
       c) response 200 with record + is_duplicate=False + enqueued_msg_id
  5) XADD 실패시: status='collected' 유지, enqueued_msg_id=None 반환 (rollback 안 함 — dedup 재시도 안전)
```

### Response
```json
{
  "record": { /* RawEventRecord */ },
  "is_duplicate": false,
  "enqueued_msg_id": "1700000000000-0"
}
```

---

## API 신규 endpoint

| Endpoint | 용도 |
|---|---|
| `POST /api/admin/raw-events` | RawEventCreate idempotent insert + XADD |
| `POST /api/admin/collect-rss-once` | collector run() in-process 트리거 (`asyncio.to_thread`). summary dict 반환. |

`GET /api/admin/raw-events` 는 STEP 008로 연기 (skeleton 최소화).
인증은 STEP 007 범위 외 — `/api/admin` prefix만으로 internal-only 명시 + STEP 008 token 도입 TODO.

---

## Alembic Migration

### `backend/alembic/versions/0002_raw_events.py`
- `revision = "b2c3d4e5f6a7"`, `down_revision = "a1b2c3d4e5f6"`
- `upgrade()`:
  - `op.create_table("raw_events", ...)` 위 컬럼 전부, `PrimaryKeyConstraint("id")`, `UniqueConstraint("content_hash", name="uq_raw_events_content_hash")`
  - `op.execute("CREATE UNIQUE INDEX uq_raw_events_source_external ON raw_events (source_type, external_id) WHERE external_id IS NOT NULL")`
  - `op.execute("CREATE INDEX ix_raw_events_collected_at ON raw_events (collected_at DESC)")`
  - `op.create_index("ix_raw_events_status", ...)`, `ix_raw_events_source_type`
  - `op.execute("CREATE INDEX ix_raw_events_published_at ON raw_events (published_at DESC NULLS LAST)")`
  - `op.execute("CREATE INDEX ix_raw_events_raw_metadata_gin ON raw_events USING gin (raw_metadata jsonb_path_ops)")`
- `downgrade()` 역순.

env.py L19 `from backend.app import models`가 자동 등록 — `backend/app/models/__init__.py`에 `RawEventORM` re-export 필요.

---

## Docker / requirements

### 신규: `requirements/collector.txt`
```
-r base.txt
feedparser==6.0.11
```
Playwright/Selenium 포함된 `crawler.txt`는 미사용(범위 외).

### Dockerfile 변경
- `workers/Dockerfile`: `collector.txt` install 추가
- `backend/Dockerfile`: `collector.txt` install 추가 (in-process `/collect-rss-once` 위해)

### 컴포즈 신규 서비스 — **없음**
one-shot CLI / API 트리거 모델. cron/scheduler는 STEP 008로 연기.

---

## 신규/수정 파일

### 신규 파일

| 경로 | 목적 |
|---|---|
| `backend/app/models/raw_event.py` | `RawEventORM` |
| `backend/app/schemas/raw_events.py` | `RawEventCreate` / `RawEventRecord` / `RawEventCreateResponse` |
| `backend/app/services/raw_event_service.py` | `create_raw_event(session, payload) → RawEventCreateResponse` (pg_insert + on_conflict_do_nothing + XADD + status patch) |
| `backend/alembic/versions/0002_raw_events.py` | 마이그레이션 |
| `workers/collectors/__init__.py` | |
| `workers/collectors/__main__.py` | CLI entry |
| `workers/collectors/rss_collector.py` | `run() → summary dict` |
| `workers/collectors/sources.py` | `DEFAULT_SOURCES`, `get_sources()` |
| `workers/tests/__init__.py` | |
| `workers/tests/test_rss_collector.py` | fixture 기반 unit |
| `tests/fixtures/rss_bbc_min.xml` | 2 entry sample |
| `tests/fixtures/rss_empty.xml` | empty feed |
| `tests/fixtures/rss_malformed.xml` | bozo |
| `tests/fixtures/rss_no_link.xml` | missing link |
| `tests/smoke/test_rss_collector_fixture.py` | file:// fixture → backend → DB/stream → 기존 pipeline 흐름 |
| `tests/smoke/test_rss_collector_live.py` | gated `RUN_RSS_LIVE_SMOKE=1` |
| `requirements/collector.txt` | feedparser 단독 |
| `backend/tests/test_raw_events_api.py` | admin endpoint unit |
| `docs/COLLECTOR_DESIGN.md` | RSS 설계 + 향후 collector 확장 패턴 |
| `docs/DATA_POLICY.md` | 저장 정책 / 저작권 경계 |
| `docs/COMPLIANCE_BOUNDARY.md` | anti-bot/paywall/본문 금지 |
| `plans/007_RSS_COLLECTOR_RAW_EVENTS_PLAN.md` | 본 plan 영구 사본 |
| `plans/007_RSS_COLLECTOR_RAW_EVENTS_REPORT.md` | 실행 보고 |

### 수정 파일

| 경로 | 변경 |
|---|---|
| `backend/app/models/__init__.py` | `from .raw_event import RawEventORM`, `__all__` 갱신 |
| `backend/app/api/admin.py` | `POST /raw-events`, `POST /collect-rss-once` 추가 |
| `backend/app/core/config.py` | `RSS_COLLECTOR_FETCH_TIMEOUT_SEC=15`, `RSS_SOURCES_CONFIG_PATH=""`, `RSS_COLLECTOR_USER_AGENT="event-intelligence/0.7 (+ei)"` 추가. `redacted_env_status()` fields 갱신. |
| `.env.example` | STEP 007 블록 추가 (3개 키 + 안전 기본값) |
| `workers/Dockerfile` | `collector.txt` install |
| `backend/Dockerfile` | `collector.txt` install |
| `docs/EVENT_SCHEMA.md` | `## raw_events Table (STEP 007)` 섹션 추가 |
| `docs/TRD.md` | STEP 007 신규 컴포넌트/환경변수/DB 구성/인프라 섹션 추가 |
| `docs/API_CONTRACT.md` | `/api/admin/raw-events`, `/api/admin/collect-rss-once` 추가 |
| `docs/ARCHITECTURE.md` | L142-144 "MISSING → STEP 007" → "RSS collector → IMPLEMENTED (STEP 007)" + 흐름도 갱신 |
| `docs/COMPATIBILITY_NOTES.md` | STEP 007 섹션 (feedparser 6.0.11, published_parsed UTC 변환, bozo 처리, KR 인코딩) |

---

## 환경 변수

| 키 | 기본값 | 비고 |
|---|---|---|
| `RSS_COLLECTOR_FETCH_TIMEOUT_SEC` | `15` | per-source feedparser fetch timeout |
| `RSS_SOURCES_CONFIG_PATH` | `""` | stub. 비어있으면 `DEFAULT_SOURCES` 사용 |
| `RSS_COLLECTOR_USER_AGENT` | `"event-intelligence/0.7 (+ei)"` | 정중한 UA |
| `RUN_RSS_LIVE_SMOKE` | `""` | 테스트 전용 — `"1"` 이면 live smoke 실행 |

`.env.example`에 STEP 007 블록 추가. `redacted_env_status()` fields 리스트에 추가 (값 출력 금지, 길이만).

---

## 테스트 전략

### Backend unit (`backend/tests/test_raw_events_api.py`)
- `app.dependency_overrides[get_session] = lambda: mock_session` + `patch("backend.app.api.admin.<entry>")` 패턴
- 케이스: insert+XADD / 중복 content_hash → is_duplicate=True+XADD 미실행 / XADD 실패 → enqueued_msg_id=None / minimal payload (external_id NULL) / `collect-rss-once`가 `workers.collectors.rss_collector.run` 호출

### Collector unit (`workers/tests/test_rss_collector.py`)
- fixture XML 파싱 (`feedparser.parse(open(path).read())`)
- 케이스: valid 2 entries / empty / malformed (bozo) / entry no link skip / content_hash 결정성 / summary 변경 시 hash 다름 / `published_parsed=None` → `published_at=None` / `httpx.post` mock으로 payload shape 검증 / `is_duplicate=True` 응답시 재시도 안 함 / 1개 source network 실패가 전체 run 죽이지 않음

### Smoke fixture-mode (네트워크 0)
- `tests/smoke/test_rss_collector_fixture.py`: `monkeypatch`로 `DEFAULT_SOURCES`를 `file://` URI로 치환 → collector 실행 → DB row 확인 → 12s 후 `GET /api/events` 신규 카드 확인

### Smoke live (gated)
- `RUN_RSS_LIVE_SMOKE=1`일 때만 BBC World 1개 source fetch → items_seen ≥ 1 → 1 row insert 확인. 총 wall-clock < 60s.

### 회귀 게이트 (필수 PASS)
- `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_vector_search.py -v`
- `RawEvent` Pydantic schema `git diff a1b2c3d4e5f6 -- backend/app/schemas/events.py` 0 hunks

---

## 실행 순서

### Phase 1 — 정적 점검
```powershell
git status
git log --oneline -5
git worktree list
docker compose -f docker-compose.dev.yml ps
docker compose -f docker-compose.dev.yml config --quiet
```

### Phase 2 — Schemas + Model
1. `backend/app/schemas/raw_events.py` 작성
2. `backend/app/models/raw_event.py` 작성 (`RawEventORM`)
3. `backend/app/models/__init__.py` re-export 갱신
4. Smoke: `python -c "from backend.app.models import RawEventORM; print('ok')"`

### Phase 3 — Alembic migration
1. `backend/alembic/versions/0002_raw_events.py` 작성
2. `docker compose run --rm backend alembic upgrade head` → Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7
3. `docker compose exec postgres psql -U event_user -d event_intel -c "\d raw_events"` 확인
4. `docker compose run --rm backend alembic downgrade -1 && alembic upgrade head` 라운드트립
5. `event_cards`/`comments` 데이터 보존 확인

(volume 삭제 없음 — additive migration만 수행)

### Phase 4 — Backend service + API
1. `backend/app/services/raw_event_service.py`
2. `backend/app/api/admin.py` 라우트 추가
3. `backend/app/core/config.py` env vars + `redacted_env_status` 갱신
4. `.env.example` STEP 007 블록 추가
5. `backend/tests/test_raw_events_api.py` 작성
6. `$env:PYTHONPATH=...; pytest backend/tests/test_raw_events_api.py -v` PASS

### Phase 5 — requirements + Dockerfile
1. `requirements/collector.txt` 작성
2. `workers/Dockerfile` / `backend/Dockerfile` install 추가
3. `docker compose build worker backend`
4. `docker compose up -d` 7컨테이너 healthy
5. `curl http://localhost:8000/health` 확인

### Phase 6 — Collector module
1. `workers/collectors/sources.py`
2. `workers/collectors/rss_collector.py`
3. `workers/collectors/__main__.py`
4. `tests/fixtures/rss_*.xml` 4개
5. `workers/tests/test_rss_collector.py`
6. `pytest workers/tests -v` PASS
7. fixture 기반 one-shot 실행: `docker compose run --rm worker python -m workers.collectors.rss_collector` (sources를 file:// 치환한 환경에서)

### Phase 7 — Smoke + 회귀 게이트
1. `tests/smoke/test_rss_collector_fixture.py` 작성 → PASS
2. **회귀 게이트**: `pytest tests/smoke/test_pipeline.py tests/smoke/test_persistence.py tests/smoke/test_vector_search.py -v` PASS
3. `tests/smoke/test_rss_collector_live.py` 작성 (skipif gated)
4. (옵션) `RUN_RSS_LIVE_SMOKE=1 pytest tests/smoke/test_rss_collector_live.py -v`

### Phase 8 — `/collect-rss-once` 검증
```powershell
curl -X POST http://localhost:8000/api/admin/collect-rss-once
# summary JSON 확인
curl http://localhost:8000/api/admin/jobs   # stream length 증가 확인
```

### Phase 9 — 문서 + plan/report
1. `docs/COLLECTOR_DESIGN.md`, `DATA_POLICY.md`, `COMPLIANCE_BOUNDARY.md` 신규
2. `docs/EVENT_SCHEMA.md`, `TRD.md`, `API_CONTRACT.md`, `ARCHITECTURE.md`, `COMPATIBILITY_NOTES.md` 갱신
3. `plans/007_RSS_COLLECTOR_RAW_EVENTS_PLAN.md` 신규
4. `plans/007_RSS_COLLECTOR_RAW_EVENTS_REPORT.md` 신규

### Phase 10 — Commit
- **Commit A**: `feat(step-007): add rss collector and raw events persistence skeleton`
- **Commit B**: `docs(step-007): collector design + data policy + plan/report snapshot`

`.env`, `.venv`, `node_modules` 포함 금지. `git push` 미실행.

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
- [ ] `backend/app/models/__init__.py`에서 `RawEventORM` re-export
- [ ] `alembic upgrade head` 0001 → 0002 clean
- [ ] `alembic downgrade -1 && upgrade head` roundtrip clean
- [ ] `raw_events` 테이블 + 2개 UNIQUE 제약 + 5개 index 확인
- [ ] `event_cards`/`comments` 기존 데이터 보존
- [ ] `POST /api/admin/raw-events` 중복시 `is_duplicate=true` + XADD 미실행
- [ ] `POST /api/admin/raw-events` XADD 실패시 `enqueued_msg_id=null` + status='collected' 유지
- [ ] `POST /api/admin/collect-rss-once` summary 반환 + 이벤트 루프 블록 안 함
- [ ] `python -m workers.collectors.rss_collector` exit 0 + summary log
- [ ] fixture 기반 collector unit test 전부 PASS
- [ ] `backend/tests/test_raw_events_api.py` PASS
- [ ] `tests/smoke/test_rss_collector_fixture.py` PASS
- [ ] **회귀**: `test_pipeline.py` / `test_persistence.py` / `test_vector_search.py` 0 diff PASS
- [ ] `RawEvent` Pydantic 무변경 (git diff 0 hunks)
- [ ] feedparser는 worker + backend 이미지에만, Playwright/Selenium 미설치
- [ ] 7개 컨테이너 모두 Up/healthy
- [ ] `.env` 실값 미출력
- [ ] 9개 문서 갱신/신규 + plan/report 작성
- [ ] Commit A/B 성공, `.env`/`.venv`/`node_modules` 미포함
- [ ] `git push` 미실행
- [ ] codex sync 완료
- [ ] WARNING / BLOCKED / UNKNOWN 명시
- [ ] STEP 008 제안 포함

---

## 위험 / UNKNOWN

| # | 항목 | 영향 | 완화 |
|---|---|---|---|
| R1 | feedparser 6.0.11 Windows path quirks (file://) | 낮음 | `pathlib.Path(...).as_uri()` 사용. 본 환경은 Linux container 우선 |
| R2 | `content_hash` 충돌: RSS item이 수정 재게시 → 동일 GUID, 다른 본문 → 새 hash | 중간 | `(source_type, external_id)` partial UNIQUE가 catch. 진짜 edit는 새 row(skeleton 허용). STEP 008에서 resolver |
| R3 | `published_parsed=None` 또는 naive | 높음 | `entry.get("published_parsed")` 가드 + `tzinfo=timezone.utc` 강제 |
| R4 | Redis stream payload regression (raw_metadata json.dumps 누락) | 높음 | backend endpoint 내부에서 기존 `enqueue_raw_event()` 함수 재사용 — wire shape 변경 0 |
| R5 | STEP 003-006 smoke 회귀 | 높음 | `RawEvent` Pydantic 동결 + 회귀 게이트 필수 PASS |
| R6 | DB insert 성공 + XADD 실패 split-brain | 중간 | row는 `status='collected'` 잔존. dedup이 재시도 안전. rollback 안 함 |
| R7 | feedparser blocking call이 FastAPI event loop 블록 | 중간 | `/collect-rss-once`는 `await asyncio.to_thread(rss_collector.run)` |
| R8 | URL length > 2048 (rare) | 낮음 | insert 직전 length-cap + warn 로그 |
| R9 | backend 이미지 크기 증가 (feedparser ~150KB) | 낮음 | 허용 |
| R10 | 라이브 RSS 외부 의존 (실패 변동성) | 중간 | 기본 테스트는 fixture-only. live는 `RUN_RSS_LIVE_SMOKE=1` opt-in만 |
| U1 | DB-backed sources 설계 (collector_sources 테이블 스키마) | — | STEP 008+로 연기. `docs/COLLECTOR_DESIGN.md`에 마이그레이션 경로 문서화 |
| U2 | raw_events retention policy (TTL/archival) | — | STEP 008+로 연기 |
| U3 | admin endpoint 인증 (network policy → token) | — | STEP 008+로 연기. TODO 명시 |

---

## 다음 STEP 순서

1. **STEP 008** — agent-worker async 전환 + raw_event_id stream linkage + `raw_events.status` processed/failed 업데이트 + Milvus insert background task + LangSmith tracing 실연결.
2. **STEP 009** — Next.js `/events` 목록 UI + 검색 UI + admin `/api/admin/raw-events` GET + collector_sources 테이블.
3. **STEP 010** — DART API / SEC EDGAR collector 추가 + vector dedup threshold + entity linking LLM 전환.
4. **STEP 011** — Web crawler (Playwright optional) + 본문 처리 (저작권 준수) + 광역 collector 통합.
5. **STEP 012** — KG-RAG / hybrid search (sparse + dense) 도입.
