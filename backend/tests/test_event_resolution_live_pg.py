from __future__ import annotations

"""S2e live-PostgreSQL E2E — 실 dedup → resolver → apply_routing 을 **실제 Postgres**로 검증.

in-memory fake session(test_event_resolution_pipeline)과 달리 실 DB 의 FK·unique·on_conflict·
transaction·rollback·GREATEST/LEAST·timestamptz 를 실제로 실행한다. 가장 중요한 것: **2-세션 동시
CREATE race**(fake/mock 으로는 입증 불가)를 실 Postgres unique 제약 + rollback 으로 입증한다.

연결 대상: **disposable 테스트 DB**(event_intel_test) — 운영/개발 DB(event_intel) 미오염. 각 테스트
전에 Event 테이블 TRUNCATE(격리). live-PG 미연결 환경(CI 등)에서는 모듈 전체 graceful **skip**
(fake/metadata 로 대체하지 않는다 — live-PG 검증은 미완으로 남긴다).

URL: 환경변수 LIVE_PG_TEST_URL 우선, 없으면 fixture 가 명시 구성(.env secret 비의존).

⚠️ **직렬 실행 전용(adversarial A-2):** 단일 공유 test DB 를 TRUNCATE 격리하므로 pytest-xdist 병렬
워커(`-n>1`)에서는 워커 간 간섭으로 flaky. CI 결선 시 live-PG 모듈은 `-p no:xdist`(직렬) 또는
DB-per-worker 격리가 필요(ADR#21 후속). 현재 단일 워커 실행 기준 green.
"""

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from ingestion.orchestration.cross_source_dedup import cluster_records

from backend.app.services import event_resolution_pipeline as pipe
from backend.app.services import event_timeline_service as svc
from backend.app.services.event_resolver import ACTION_APPEND, ACTION_CREATE
from backend.app.services.event_timeline_service import ResolvedCandidate

_LIVE_PG_URL = os.environ.get(
    "LIVE_PG_TEST_URL",
    "postgresql+asyncpg://event_user:event_pass@localhost:5432/event_intel_test",
)
_EVENT_TABLES = "events, event_updates, cluster_event_map, event_links, event_cards"


def _pg_reachable() -> bool:
    """psycopg(sync)로 빠르게 도달성만 확인 — 수집 시점 async 회피, 미연결 시 모듈 skip."""
    try:
        import psycopg

        dsn = _LIVE_PG_URL.replace("postgresql+asyncpg", "postgresql")
        with psycopg.connect(dsn, connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _pg_reachable(),
    reason="live-PG(event_intel_test) 미연결 — docker compose up -d postgres + alembic upgrade 필요. live-PG 검증 미완으로 남김.",
)

_T1 = datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc)
_T2 = datetime(2026, 6, 18, 11, 0, tzinfo=timezone.utc)
_T3 = datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc)


def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "bbc",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


def _cand(title="호르무즈 해협 긴장", observed=_T2, **kw):
    base = dict(canonical_title=title, observed_at=observed, delta_summary="update")
    base.update(kw)
    return ResolvedCandidate(**base)


def _strong_cluster():
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label="Hormuz tanker seized"),
        _rec(source_id="bbc", canonical_url="https://wire/x", title_or_label="Hormuz tanker seized"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1 and clusters[0].confidence == "duplicate" and clusters[0].clique_ok
    return clusters[0]


# ── fixtures (실 Postgres, disposable, 테스트별 격리) ──────────────────────────────
@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(_LIVE_PG_URL)
    # 각 테스트 전 Event 테이블 격리(운영 DB 아님 — disposable test DB).
    async with eng.begin() as conn:
        await conn.execute(text(f"TRUNCATE {_EVENT_TABLES} RESTART IDENTITY CASCADE"))
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s


async def _count(session, table: str) -> int:
    return (await session.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()


async def _first_event_id(session) -> str:
    return str((await session.execute(text("SELECT id FROM events LIMIT 1"))).scalar_one())


# ── migration/schema 적용 확인 ────────────────────────────────────────────────────
async def test_live_migration_schema_present(session):
    # alembic 0001~0005 적용된 실 DB 형상 확인(sanity).
    rows = (await session.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename IN "
        "('events','event_updates','cluster_event_map','event_links','event_cards')"
    ))).scalars().all()
    assert set(rows) == {"events", "event_updates", "cluster_event_map", "event_links", "event_cards"}


# ── CREATE / APPEND / HOLD 실 DB ──────────────────────────────────────────────────
async def test_live_first_cluster_creates_event_and_maps(session):
    c = _strong_cluster()
    res = await pipe.resolve_and_apply_cluster(session, c, candidate=_cand())
    assert res.action == ACTION_CREATE
    assert await _count(session, "events") == 1
    assert await _count(session, "cluster_event_map") == 1
    assert await _count(session, "event_updates") == 1   # CREATE 는 genesis update 1행(생성 근거, ADR#31)


async def test_live_second_report_appends_not_new_event(session):
    c = _strong_cluster()
    r1 = await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    r2 = await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T3, delta_summary="유가 +4%"))
    assert r1.action == ACTION_CREATE and r2.action == ACTION_APPEND
    assert r2.event_id == r1.event_id
    assert await _count(session, "events") == 1          # 새 Event 남발 0
    assert await _count(session, "event_updates") == 2   # genesis(CREATE) + append


async def test_live_rerun_idempotent(session):
    c = _strong_cluster()
    for obs in (_T2, _T3, _T3):
        await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=obs))
    assert await _count(session, "events") == 1
    assert await _count(session, "cluster_event_map") == 1
    assert await _count(session, "event_updates") == 3   # genesis(CREATE) + 2·3번째 append


async def test_live_transitive_weak_member_held_not_merged(session):
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
    ]
    c = cluster_records(recs)[0]
    assert c.clique_ok is False and len(c.weak_only_members) == 1
    res = await pipe.resolve_and_apply_cluster(session, c, candidate=_cand())
    assert res.action == ACTION_CREATE
    assert await _count(session, "events") == 2          # core + degenerate held(blog)
    assert await _count(session, "event_updates") == 1   # core genesis 1행(자동병합 0 — blog 미흡수)
    links = (await session.execute(text(
        "SELECT status, linked_event_id::text FROM event_links"
    ))).all()
    assert len(links) == 1 and links[0][0] == "possible"
    assert links[0][1] == res.event_id                   # held → primary(core)


# ── FSD 단조성 (실 GREATEST/LEAST) ────────────────────────────────────────────────
async def test_live_fsd_first_seen_pulled_earlier(session):
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))  # CREATE @T2
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T1))  # APPEND @T1(이른)
    ev, updates = await svc.get_event(session, await _first_event_id(session))
    assert ev.first_seen_at == _T1     # 실 LEAST 로 과거로 당김
    assert ev.last_update_at == _T2    # 실 GREATEST 로 후퇴 안 함
    assert len(updates) == 2           # genesis(@T2) + 이른 보도 append(@T1)


async def test_live_last_update_monotonic_forward(session):
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T3))
    ev, _ = await svc.get_event(session, await _first_event_id(session))
    assert ev.last_update_at == _T3
    assert ev.first_seen_at == _T2     # 미래로 밀리지 않음


# ── evidence/source_refs sanitize (실 JSONB) ──────────────────────────────────────
async def test_live_evidence_source_refs_sanitized(session):
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(
        observed=_T3,
        evidence=({"url": "https://reuters/x", "relation": "supports", "body": "B" * 5000,
                   "author_email": "a@b.com", "nested": {"k": "v"}},),
        source_refs=("raw-001", "C" * 5000),
    ))
    _, updates = await svc.get_event(session, await _first_event_id(session))
    # updates[0]=genesis(@T2, _cand 기본 evidence 없음), updates[1]=APPEND(@T3, dirty→sanitize 대상).
    assert updates[0].evidence == []                                                   # genesis: evidence 없음
    assert updates[1].evidence == [{"url": "https://reuters/x", "relation": "supports"}]
    assert updates[1].source_refs == ["raw-001"]


# ── append-only / tz / UUID 방어 (실 DB) ──────────────────────────────────────────
async def test_live_append_only_rows_accumulate(session):
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T3))
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T3))
    # append-only: update 행이 누적(덮어쓰기 0). 각 행 고유 id.
    ids = (await session.execute(text("SELECT id FROM event_updates"))).scalars().all()
    assert len(ids) == 3 and len(set(ids)) == 3   # genesis(CREATE) + 2 append, 각 행 고유 id


async def test_live_tz_naive_defended_and_stored_aware(session):
    # tz-naive observed_at 이 들어와도 죽지 않고 timestamptz 로 aware 저장.
    eid = await svc.create_event(session, candidate=_cand(observed=datetime(2026, 6, 18, 8, 0)))
    ev, _ = await svc.get_event(session, eid)
    assert ev.first_seen_at.tzinfo is not None
    assert ev.first_seen_at.utcoffset().total_seconds() == 0


async def test_live_uuid_str_boundary(session):
    # event_id 를 str 로 넘겨도 실 uuid 컬럼에 정상 append.
    eid = await svc.create_event(session, candidate=_cand(observed=_T2))
    uid = await svc.append_update(session, event_id=str(eid), candidate=_cand(observed=_T3))
    assert uuid.UUID(uid)
    _, updates = await svc.get_event(session, eid)
    assert len(updates) == 1


# ── set_snapshot 쌍방향 정합 (실 DB, event_cards FK) ──────────────────────────────
async def test_live_set_snapshot_bidirectional_and_reject_steal(session):
    eid = await svc.create_event(session, candidate=_cand(observed=_T2))
    cid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO event_cards (id, title, summary, theme, impact_path, status, "
        "sectors, entities, evidence, confidence_score, created_at, updated_at) "
        "VALUES (:id,'t','s','geopolitics','',  'published','[]','[]','[]',0.5, now(), now())"
    ).bindparams(id=cid))
    await session.commit()
    # 정상 쌍방향 세팅.
    await svc.set_snapshot(session, event_id=eid, card_id=str(cid))
    card_eid = (await session.execute(text("SELECT event_id::text FROM event_cards WHERE id=:c").bindparams(c=cid))).scalar_one()
    ev_cid = (await session.execute(text("SELECT snapshot_card_id::text FROM events WHERE id=:e").bindparams(e=uuid.UUID(eid)))).scalar_one()
    assert card_eid == eid and ev_cid == str(cid)
    # 다른 event 가 같은 카드를 훔치려 하면 거부.
    other = await svc.create_event(session, candidate=_cand(observed=_T3))
    with pytest.raises(ValueError, match="different event"):
        await svc.set_snapshot(session, event_id=other, card_id=str(cid))


# ── FK RESTRICT (0006, ADR#20 DB 레벨 감사 보호) ──────────────────────────────────
async def test_live_all_event_fks_are_restrict(session):
    # 0006 회귀 고정(adversarial A-3/B-1): events.id 를 참조하는 FK **4개 전부** confdeltype='r'(RESTRICT).
    # constraint 이름이 틀려도 통과하던 간접 검증의 사각을 직접 카탈로그 조회로 닫는다.
    # confdeltype 은 Postgres "char" 타입 → asyncpg 가 bytes 로 반환. 디코드 후 비교.
    rows = (await session.execute(text(
        "SELECT conname, confdeltype::text FROM pg_constraint "
        "WHERE contype='f' AND confrelid='events'::regclass "
        "AND conrelid::regclass::text IN ('event_updates','cluster_event_map','event_links')"
    ))).all()
    assert {r[0]: r[1] for r in rows} == {
        "event_updates_event_id_fkey": "r",
        "cluster_event_map_event_id_fkey": "r",
        "event_links_event_id_fkey": "r",
        "event_links_linked_event_id_fkey": "r",
    }
    # events.snapshot_card_id 는 SET NULL(n) 유지 — 카드 삭제 시 포인터만 비움(감사 손실 아님).
    snap = (await session.execute(text(
        "SELECT confdeltype::text FROM pg_constraint WHERE conname='events_snapshot_card_id_fkey'"
    ))).scalar_one()
    assert snap == "n"


async def test_live_fk_restrict_blocks_event_delete_with_history(session):
    # 0006: 감사 이력(event_updates)·라우팅(cluster_event_map)이 있는 Event 는 DB 가 삭제 차단(RESTRICT).
    from sqlalchemy.exc import IntegrityError

    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T3))
    eid = await _first_event_id(session)
    with pytest.raises(IntegrityError):   # RESTRICT 위반 → cascade 삭제 차단
        await session.execute(text("DELETE FROM events WHERE id=:e").bindparams(e=uuid.UUID(eid)))
    await session.rollback()
    # 감사 이력은 보존됨(삭제 안 됨).
    assert await _count(session, "events") == 1
    assert await _count(session, "event_updates") == 2   # genesis(CREATE@T2) + append(@T3)


# ── ★ 2-세션 동시 CREATE race (실 Postgres unique + rollback) ★ ────────────────────
async def test_live_concurrent_create_no_orphan(engine):
    # fake/mock 으로 입증 불가했던 핵심: 동일 cluster 가 2개 세션에서 거의 동시에 CREATE.
    # 실 Postgres unique(cluster_event_map PK) + apply_routing rollback 으로 최종 Event 1·orphan 0.
    c = _strong_cluster()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def route(observed):
        async with maker() as s:
            return await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=observed))

    r1, r2 = await asyncio.gather(route(_T2), route(_T3))

    # 검증용 별도 세션.
    async with maker() as s:
        assert await _count(s, "events") == 1            # 최종 Event 1개(orphan 0)
        assert await _count(s, "cluster_event_map") == 1  # 매핑 1개
        # 두 라우팅 모두 같은 (승자) event 로 수렴.
        assert r1.event_id == r2.event_id
        # event_updates: 승자 genesis(1) + 패자 degrade append(1) — 중복/누락 없음.
        assert await _count(s, "event_updates") == 2


# ── C live wiring: 수집 후보 records → Event 영속(실 DB) ────────────────────────────
async def test_live_candidate_records_create_then_append(session):
    # 상용 핵심을 실 DB 로: 수집 후보(records) → cross_source_dedup → resolver → events.
    # 같은 사건 2번째 배치가 새 Event 가 아니라 기존 Event 에 append.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
    ]
    s1 = await ingest_records_to_events(session, recs, enabled=True)
    assert s1.enabled is True and s1.created == 1 and s1.appended == 0
    assert await _count(session, "events") == 1
    assert await _count(session, "cluster_event_map") == 1
    assert await _count(session, "event_updates") == 1      # CREATE 는 genesis update 1행(생성 근거)
    # genesis 가 디버그 라벨이 아니라 build_delta_summary 자연어인지(실 파이프라인 → genesis 영속).
    genesis_summary = (await session.execute(text(
        "SELECT delta_summary FROM event_updates"))).scalar_one()
    assert "사건" in genesis_summary and ":" not in genesis_summary  # 예 "뉴스 보도가 동일 식별자로 확인된 사건입니다."

    s2 = await ingest_records_to_events(session, recs, enabled=True)
    assert s2.created == 0 and s2.appended == 1
    assert await _count(session, "events") == 1             # Event 남발 0
    assert await _count(session, "event_updates") == 2      # genesis + 2번째 배치 append
    # evidence 가 실 JSONB 로 sanitize 되어 영속됐는지(allowlist scalar 만).
    ev = (await session.execute(text(
        "SELECT evidence FROM event_updates LIMIT 1"))).scalar_one()
    for item in ev:
        assert set(item).issubset({"url", "source_type", "role", "confidence", "relation", "observed_at"})


async def test_live_flag_off_no_persistence(session):
    # flag off → DB 미접근(영속 0). 기존 event_cards 경로만 동작하는 계약을 실 DB 로 확인.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=False)
    assert summary.enabled is False
    assert await _count(session, "events") == 0
    assert await _count(session, "event_updates") == 0


# ── source-type publish gate (ADR#33, R-SourceTypeFidelityGate) — 실 DB ─────────────
async def test_live_gate_pure_community_withheld(session):
    # pure-community cross-source(동일 canonical_url 강신호) → 발행 금지(실 DB events/updates/map 0).
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    recs = [
        _rec(record_type="community_signal", source_id="hn", canonical_url="https://ex.com/p",
             title_or_label="Show X", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="reddit", canonical_url="https://ex.com/p",
             title_or_label="X on ex.com", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert await _count(session, "events") == 0
    assert await _count(session, "event_updates") == 0
    assert await _count(session, "cluster_event_map") == 0


async def test_live_gate_official_news_publishes(session):
    # official+news(동일 official_id) → 발행(실 DB). evidence 에 official source_type 보존.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    acc = "0001193125-26-000123"
    recs = [
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence=f"https://sec.gov/{acc}-index.htm",
             title_or_label="Acme 8-K", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters",
             source_url_or_evidence=f"https://reuters.com/acme-{acc}",
             canonical_url=f"https://reuters.com/acme-{acc}",
             title_or_label="Acme deal per SEC filing", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 1 and summary.withheld_source_type == 0
    assert await _count(session, "events") == 1
    ev = (await session.execute(text("SELECT evidence FROM event_updates LIMIT 1"))).scalar_one()
    stypes = {item.get("source_type") for item in ev}
    assert "official" in stypes


async def test_live_failed_cluster_isolated_other_persists(session):
    # 실 DB 로 후보 단위 격리 입증(adversarial D): 한 클러스터 실패의 rollback 이 다른 클러스터의
    # commit 된 영속을 훼손하지 않는다(fake 가 아닌 실 Postgres commit/rollback).
    from backend.app.services.event_ingest_pipeline import (
        build_record_index,
        candidate_from_cluster,
        ingest_records_to_events,
    )

    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="A story", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="A story", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="afp", canonical_url="https://other/y",
             title_or_label="B story", published_at_or_observed_at="2025-06-03"),
        _rec(source_id="dpa", canonical_url="https://other/y",
             title_or_label="B story", published_at_or_observed_at="2025-06-03"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 2
    fail_id = clusters[0].cluster_id
    index = build_record_index(recs)

    def _cf(c):
        if c.cluster_id == fail_id:
            raise ValueError("injected cluster failure")
        return candidate_from_cluster(c, index)

    summary = await ingest_records_to_events(session, recs, enabled=True, candidate_for=_cf)
    assert summary.failed == 1 and summary.created == 1     # 하나 실패 격리, 하나 영속
    assert await _count(session, "events") == 1            # 실패 클러스터 영속 0(rollback)
    assert await _count(session, "cluster_event_map") == 1  # 성공 클러스터만 매핑됨


# ── D-1 운영 결선: orchestration sink → Event 영속(실 DB) ───────────────────────────
def test_live_d1_orchestration_sink_persists_event():
    # D-1 결선의 핵심 sink(make_orchestration_event_sink)를 **실 DB factory**로 구동해, 운영 자동
    # 경로가 실제로 Event 를 쌓는지 입증한다. sink 는 sync 경계(asyncio.run 내부) — 운영 호출 형태
    # 그대로. NullPool 로 호출(loop)당 커넥션 격리. 주의: settings.DATABASE_URL(dev DB)이 아니라
    # disposable 테스트 DB(_LIVE_PG_URL)에 바인딩(운영/개발 DB 미오염).
    from sqlalchemy.pool import NullPool

    from backend.app.services.event_ingest_pipeline import make_orchestration_event_sink

    async def _truncate():
        eng = create_async_engine(_LIVE_PG_URL, poolclass=NullPool)
        async with eng.begin() as c:
            await c.execute(text(f"TRUNCATE {_EVENT_TABLES} RESTART IDENTITY CASCADE"))
        await eng.dispose()

    async def _counts():
        eng = create_async_engine(_LIVE_PG_URL, poolclass=NullPool)
        async with eng.connect() as c:
            ev = (await c.execute(text("SELECT count(*) FROM events"))).scalar_one()
            up = (await c.execute(text("SELECT count(*) FROM event_updates"))).scalar_one()
        await eng.dispose()
        return ev, up

    asyncio.run(_truncate())
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="bbc", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized", published_at_or_observed_at="2025-06-02"),
    ]
    engine = create_async_engine(_LIVE_PG_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    sink = make_orchestration_event_sink(factory, enabled=True)

    s1 = sink(recs)                        # sync sink → asyncio.run 내부(운영 호출 형태)
    assert s1["enabled"] is True and s1["created"] == 1 and s1["appended"] == 0
    s2 = sink(recs)                        # 같은 사건 2번째 배치 → APPEND(새 Event 0)
    assert s2["created"] == 0 and s2["appended"] == 1
    asyncio.run(engine.dispose())

    ev, up = asyncio.run(_counts())
    assert ev == 1 and up == 2             # Event 1 + genesis(CREATE) + 2번째 배치 append


# ── D-2a Event 타임라인 read API (실 DB list/get) ──────────────────────────────────
async def test_live_list_events_returns_mapped_event(session):
    # 강신호 CREATE → list_events 가 매핑된 실 주제를 노출(canonical_title=후보 title).
    from backend.app.services import event_timeline_service as tl

    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand(observed=_T2))
    listed = await tl.list_events(session)
    assert len(listed) == 1 and listed[0].canonical_title == "호르무즈 해협 긴장"
    # 단건 조회도 동작(event + updates).
    res = await tl.get_event(session, listed[0].id)
    assert res is not None and res[0].id == listed[0].id


async def test_live_list_events_excludes_held_degenerate(session):
    # transitive 약신호 → core(mapped) + held degenerate(unmapped, title=raw member key).
    # list_events 는 cluster_event_map 매핑분만 → held degenerate 제외(공개 목록 품질/안전).
    from backend.app.services import event_timeline_service as tl

    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
    ]
    c = cluster_records(recs)[0]
    assert c.clique_ok is False and len(c.weak_only_members) == 1
    await pipe.resolve_and_apply_cluster(session, c, candidate=_cand())
    assert await _count(session, "events") == 2          # core(mapped) + held degenerate(unmapped)
    listed = await tl.list_events(session)
    assert len(listed) == 1                              # held degenerate 제외(매핑분만)
    assert listed[0].canonical_title == "호르무즈 해협 긴장"  # raw member key 아님

    # 단건 공개 조회(get_public_event)도 매핑 게이트 강제: core 는 노출, held degenerate id 는 None.
    core_id = listed[0].id
    assert await tl.get_public_event(session, core_id) is not None
    held_id = (await session.execute(text(
        "SELECT id::text FROM events WHERE id::text <> :c"
    ).bindparams(c=core_id))).scalar_one()
    assert await tl.get_public_event(session, held_id) is None   # held degenerate 단건 우회 차단
    assert await tl.get_event(session, held_id) is not None      # 내부 get_event 는 그대로(게이트 없음)
