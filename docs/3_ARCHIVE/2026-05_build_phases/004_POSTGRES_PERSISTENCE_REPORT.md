# STEP 004 — Postgres Persistence Layer 실행 보고서

## ① 무엇을 했는가

### Phase A — requirements / config
- `requirements/serve.txt`에 sqlalchemy==2.0.36, asyncpg==0.30.0, alembic==1.14.0, greenlet==3.1.1, psycopg[binary]==3.2.3 핀 추가
- `backend/app/core/config.py`에 `DATABASE_URL` 필드 추가 + `redacted_env_status` 갱신

### Phase B — SQLAlchemy async 인프라
- `backend/app/db/postgres.py` 재작성: lazy init `create_async_engine` + `async_sessionmaker` + `get_session()` + `ping()`
  - 설계 변경: 모듈 로드 시점이 아닌 첫 사용 시점에 engine 생성 (host asyncpg 미설치 환경 대응)
- `backend/app/models/base.py` 신규 (`DeclarativeBase`)
- `backend/app/models/event.py` 신규 (`EventCardORM`)
- `backend/app/models/comment.py` 신규 (`CommentORM`)
- `backend/app/models/__init__.py` 신규 (모델 등록)
- `backend/app/models/README.md` 갱신

### Phase C — Alembic 구성
- `backend/alembic.ini` 신규
- `backend/alembic/env.py` 신규 (`+asyncpg` → `+psycopg` driver 치환)
- `backend/alembic/script.py.mako` 신규 (표준 템플릿)
- `backend/alembic/versions/0001_initial.py` 신규 (수동 작성):
  - `event_cards` 테이블 + 인덱스 4종 (DESC created_at, theme, GIN sectors, status)
  - `comments` 테이블 + 복합 인덱스 1종

### Phase D — Service layer
- `event_service.py` 재작성: async + SQLAlchemy. `upsert_card`는 `pg_insert(...).on_conflict_do_update()` 사용
- `comment_service.py` 재작성: async + SQLAlchemy

### Phase E — API endpoint async 전환
- `events.py`, `admin.py`, `comments.py`, `themes.py`, `sectors.py`: `async def` + `Depends(get_session)`
- `health.py`: `async def` + `await postgres_db.ping()` (Depends 사용 안 함 — 헬스체크 의미론적 이유)
- `main.py`: `postgres as postgres_db` import 추가
- `schemas/events.py`, `schemas/comments.py`: `datetime.now(timezone.utc)` default_factory

### Phase F — Backend Dockerfile + entrypoint
- `backend/entrypoint.sh` 신규 (LF 보장: Dockerfile에 `sed -i 's/\r$//'` 추가)
- `backend/Dockerfile`: `ENTRYPOINT ["/app/entrypoint.sh"]`로 교체

### Phase G — docker-compose.dev.yml
- `postgres:17-alpine` 서비스 추가 (healthcheck: `pg_isready`)
- `backend`에 `DATABASE_URL` env + `postgres: service_healthy` depends + `start_period: 30s`
- `pg_data:` 볼륨 추가

### Phase H — 테스트
- `backend/tests/test_health.py`: `app.dependency_overrides[get_session]` + `AsyncMock` 패턴으로 6개 테스트 갱신
- `tests/smoke/test_persistence.py` 신규: restart 후 카드 생존 검증

### Phase I — 문서
- `docs/ARCHITECTURE.md`, `docs/TRD.md`, `docs/EVENT_SCHEMA.md`, `docs/API_CONTRACT.md`, `docs/COMPATIBILITY_NOTES.md` 갱신
- `plans/004_POSTGRES_PERSISTENCE_PLAN.md` 신규 (plan 사본)

## ② 무엇을 검증했는가

| 검증 항목 | 결과 |
|---|---|
| Static import (asyncpg 없는 host) | WARNING — lazy init으로 해결 |
| `docker compose config --quiet` | PASS |
| `docker compose build backend` | PASS |
| `docker compose up -d postgres` + healthcheck | PASS (healthy) |
| `docker compose up -d backend worker agent-worker` | PASS |
| backend 로그 `alembic upgrade head` 성공 | PASS — revision a1b2c3d4e5f6 |
| `psql \dt` → event_cards + comments 2개 | PASS |
| `GET /health` → `{redis:ok, milvus:ok, postgres:ok}` | PASS |
| `tests/smoke/test_pipeline.py` (기존 e2e) | PASS — 1 card found |
| `tests/smoke/test_persistence.py` (신규) | PASS — restart 후 카드 유지 |
| `pytest backend/tests -q` (unit) | PASS — 6/6 |
| 컨테이너 전체 상태 | 7개 모두 healthy/running |

## ③ WARNING / BLOCKED / UNKNOWN

### WARNING
- **host asyncpg 미설치**: `.venv`에 asyncpg 없음. `postgres.py`를 lazy init으로 설계 변경하여 unit test는 host에서도 통과. Docker 내부에서는 정상 작동.
  - 계획서 주의 사항에 명시된 예상 상황 ("asyncpg가 host에 없을 수 있으므로").
- **MILVUS**: `milvus:ok` 아닌 `milvus:disconnected` (기존 동작 유지). STEP 003부터 유지된 상태.

### BLOCKED
- 없음.

### UNKNOWN
- 없음.

## STEP 005 후보

| 항목 | 우선순위 |
|---|---|
| `raw_events` 테이블 + worker DB 저장 | Medium |
| `agent_runs` / `agent_run_steps` 테이블 + LangGraph 실행 로그 | Medium |
| normalize_event / deduplicate 실제 로직 (SHA-256 hash 중복 탐지) | High |
| 실제 crawler 1종 (RSS or sitemap) | High |
| Milvus embedding insert/search 실호출 | Medium |
| OpenAI provider 활성화 (비용 가드 + 토큰 한도) | Low |
| LangSmith tracing 활성화 | Low |
| Next.js `/events` 목록 UI | Low |
