from __future__ import annotations

"""D-2c — 합성 Event seed + DB target 가드 검증.

두 층:
  1) 단위(DB 무관): db_target 가드(staging/production fail-closed·dev/test 허용·자격증명 미노출)
     + seed 합성 데이터 안전성(example.com·allowlist evidence·투자조언/PII 없음).
  2) live-PG(event_intel_test, skipif): seed → list_events 공개 목록 노출 + get_public_event
     본문 가독성 + **멱등**(재실행 중복 0). live-PG 미연결 시 모듈 skip(미완으로 남김).
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.services import event_timeline_service as svc
from backend.app.tools import seed_event_timeline as seed
from backend.app.tools.db_target import (
    UnsafeWriteTargetError,
    assert_safe_write_target,
    target_db_label,
)

_DEV_URL = "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel"


# ── 단위: DB target 가드 ────────────────────────────────────────────────────────
def test_target_db_label_excludes_credentials():
    label = target_db_label(_DEV_URL)
    assert label == "localhost:5432/event_intel"
    # 자격증명(user/password)은 라벨에 절대 포함 안 됨.
    assert "event_user" not in label and "event_pass" not in label


def test_target_db_label_malformed_returns_placeholder():
    assert target_db_label("::not a url::") == "?"


@pytest.mark.parametrize("env", ["dev", "test"])
def test_assert_safe_write_target_allows_dev_test(env):
    # dev/test 는 허용 — 라벨 반환, raise 없음.
    label = assert_safe_write_target(app_env=env, database_url=_DEV_URL)
    assert label == "localhost:5432/event_intel"


@pytest.mark.parametrize("env", ["staging", "production"])
def test_assert_safe_write_target_blocks_non_dev(env):
    # staging/production 은 명시 허용 없이 거부(allowlist fail-closed).
    with pytest.raises(UnsafeWriteTargetError):
        assert_safe_write_target(app_env=env, database_url=_DEV_URL)


@pytest.mark.parametrize("env", ["prod", "PRODUCTION", "live", "canary", ""])
def test_assert_safe_write_target_blocks_unknown_env(env):
    # allowlist(dev/test) 라 오타·대문자·미지 환경도 fail-closed(denylist 의 fail-open 회귀 차단).
    with pytest.raises(UnsafeWriteTargetError):
        assert_safe_write_target(app_env=env, database_url=_DEV_URL)


def test_assert_safe_write_target_blocks_prod_dbname_even_if_app_env_dev():
    # APP_ENV=dev 로 오설정해도 dbname 이 prod 마커면 거부(APP_ENV 단일 신뢰 회피, 2차 방어).
    prod_url = "postgresql+asyncpg://event_user:event_pass@db:5432/event_intel_prod"
    with pytest.raises(UnsafeWriteTargetError):
        assert_safe_write_target(app_env="dev", database_url=prod_url)
    # 단 명시 opt-in 이면 허용.
    assert assert_safe_write_target(
        app_env="dev", database_url=prod_url, allow_non_dev=True
    ) == "db:5432/event_intel_prod"


@pytest.mark.parametrize("env", ["staging", "production"])
def test_assert_safe_write_target_allows_non_dev_with_override(env):
    # 명시 opt-in(--allow-non-dev-db) 이면 비-dev 도 허용.
    label = assert_safe_write_target(
        app_env=env, database_url=_DEV_URL, allow_non_dev=True
    )
    assert label == "localhost:5432/event_intel"


def test_unsafe_error_message_has_no_credentials():
    try:
        assert_safe_write_target(app_env="production", database_url=_DEV_URL)
    except UnsafeWriteTargetError as exc:
        msg = str(exc)
        assert "event_pass" not in msg and "event_user" not in msg
        assert "production" in msg and "localhost:5432/event_intel" in msg
    else:
        pytest.fail("expected UnsafeWriteTargetError")


# ── 단위: 합성 seed 데이터 안전성 ─────────────────────────────────────────────────
def test_seed_data_is_safe_synthetic():
    assert len(seed._SEED_EVENTS) >= 3
    _ALLOWED = {"url", "source_type", "role", "confidence", "relation", "observed_at"}
    for ev in seed._SEED_EVENTS:
        assert ev.cluster_id.startswith("seed:")  # 안정 멱등키
        assert 2 <= len(ev.updates) <= 4
        for u in ev.updates:
            assert u.delta_summary and len(u.delta_summary) > 10  # 라벨 아닌 자연어 서술
            # 디버그 라벨("conf:reason") 형태가 아님(자연어 본문).
            assert not (":" in u.delta_summary[:6] and u.delta_summary[0].isdigit())
            for e in u.evidence:
                assert set(e.keys()) <= _ALLOWED  # allowlist 키만
                assert e["url"].startswith("https://example.com/")  # 합성 URL


# ── live-PG (event_intel_test) ─────────────────────────────────────────────────
_LIVE_PG_URL = os.environ.get(
    "LIVE_PG_TEST_URL",
    "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test",
)
_EVENT_TABLES = "events, event_updates, cluster_event_map, event_links, event_cards"


def _pg_reachable() -> bool:
    try:
        import psycopg

        dsn = _LIVE_PG_URL.replace("postgresql+asyncpg", "postgresql")
        with psycopg.connect(dsn, connect_timeout=3):
            return True
    except Exception:
        return False


live_pg = pytest.mark.skipif(
    not _pg_reachable(),
    reason="live-PG(event_intel_test) 미연결 — docker compose up -d postgres + alembic upgrade 필요. seed live 검증 미완으로 남김.",
)


@pytest_asyncio.fixture
async def factory():
    eng = create_async_engine(_LIVE_PG_URL)
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_EVENT_TABLES} RESTART IDENTITY CASCADE"))
    try:
        yield async_sessionmaker(eng, expire_on_commit=False)
    finally:
        await eng.dispose()


@live_pg
@pytest.mark.asyncio
async def test_seed_then_listed_in_public_timeline(factory):
    result = await seed.seed_all(factory)
    assert len(result["created"]) == len(seed._SEED_EVENTS)
    assert result["skipped"] == []

    async with factory() as session:
        # map_cluster 매핑 → 공개 목록(list_events)에 전부 노출.
        events = await svc.list_events(session, limit=50, offset=0)
        assert len(events) == len(seed._SEED_EVENTS)
        titles = {e.canonical_title for e in events}
        assert "AI 모델 접근 정책 변경" in titles
        # 결정적 정렬(last_update_at desc) — 가장 최근 last_update 가 선두.
        assert events[0].last_update_at >= events[-1].last_update_at


@live_pg
@pytest.mark.asyncio
async def test_seed_public_event_has_readable_updates(factory):
    await seed.seed_all(factory)
    async with factory() as session:
        events = await svc.list_events(session, limit=50)
        target = next(e for e in events if e.canonical_title == "공공 데이터 API 장애")
        got = await svc.get_public_event(session, target.id)
        assert got is not None
        event, updates = got
        assert len(updates) == 4  # 4개 update
        # observed_at ASC 정렬 + 본문이 사람이 읽을 수 있는 서술.
        assert updates[0].observed_at <= updates[-1].observed_at
        assert "응답하지 않는다" in updates[0].delta_summary
        # evidence allowlist 메타만(전문/PII 없음).
        assert updates[0].evidence[0]["url"].startswith("https://example.com/")


@live_pg
@pytest.mark.asyncio
async def test_seed_is_idempotent(factory):
    first = await seed.seed_all(factory)
    assert len(first["created"]) == len(seed._SEED_EVENTS)
    # 재실행 — 전부 skip(중복 0).
    second = await seed.seed_all(factory)
    assert second["created"] == []
    assert len(second["skipped"]) == len(seed._SEED_EVENTS)

    async with factory() as session:
        # Event 수는 그대로(중복 생성 안 됨).
        n_events = (await session.execute(text("SELECT count(*) FROM events"))).scalar_one()
        assert n_events == len(seed._SEED_EVENTS)
