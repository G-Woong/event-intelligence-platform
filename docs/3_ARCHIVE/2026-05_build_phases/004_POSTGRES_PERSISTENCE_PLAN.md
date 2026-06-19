# STEP 004 — Postgres Persistence Layer (Plan)

본 plan의 전문은 `plans/repo-sunny-barto.md`에 있습니다.

## 요약

- **목표**: in-memory event_service/comment_service → PostgreSQL 영속화
- **테이블**: `event_cards`, `comments` (2개)
- **Migration**: Alembic (`backend/alembic/`) + `backend/entrypoint.sh`
- **Async 전략**: SQLAlchemy 2.x async + asyncpg. 모든 API endpoint `async def`.
- **검증 골든 패스**: `test_persistence.py` — backend restart 후 카드 유지

## Phase 목록

| Phase | 내용 |
|---|---|
| A | requirements/serve.txt + config.py DATABASE_URL |
| B | SQLAlchemy async engine + SessionLocal + ORM 모델 3종 |
| C | Alembic ini + env.py + versions/0001_initial.py |
| D | event_service / comment_service async 재작성 |
| E | 6개 API endpoint async 전환 + health postgres 필드 |
| F | backend/entrypoint.sh + Dockerfile ENTRYPOINT |
| G | docker-compose.dev.yml postgres 서비스 + backend depends |
| H | test_health.py dependency_overrides + test_persistence.py |
| I | 문서 5종 갱신 |
| J | 검증 (static → compose config → build → up → migration → smoke) |
