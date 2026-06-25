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
_EVENT_TABLES = "events, event_updates, cluster_event_map, event_links, event_identity_map, event_identity_candidate, event_identity_adjudication, event_cards"


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
    # ADR#35 fail-closed: source-type gate 가 publishable 없으면 WITHHELD → 합성 candidate 도 명시 source_type.
    base = dict(
        canonical_title=title, observed_at=observed, delta_summary="update",
        evidence=({"source_type": "article", "relation": "primary"},),
    )
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
    # updates[0]=genesis(@T2, _cand 기본 evidence=article primary), updates[1]=APPEND(@T3, dirty→sanitize).
    assert updates[0].evidence == [{"source_type": "article", "relation": "primary"}]   # genesis 기본
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


async def test_live_primary_authority_official_over_community(session):
    # ADR#34 primary-authority: community 가 첫 member 라도 official 이 Event 대표(canonical_title), 실 DB.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    acc = "0001193125-26-000777"
    recs = [
        _rec(record_type="community_signal", source_id="hn",
             source_url_or_evidence=f"https://forum.example.com/t/{acc}",
             title_or_label="HN discussion thread", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence=f"https://sec.gov/{acc}-index.htm",
             title_or_label="SEC official filing title", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 1 and summary.withheld_source_type == 0
    title = (await session.execute(text("SELECT canonical_title FROM events LIMIT 1"))).scalar_one()
    assert title == "SEC official filing title"          # community 아님 — official 대표


async def test_live_weak_primary_community_core_weak_official_withheld(session):
    # ADR#36 core-policy: 강신호 core(community via official_id) + weak official → WITHHELD(실 DB 영속 0).
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    acc = "0001193125-26-000333"
    recs = [
        _rec(record_type="community_signal", source_id="hn",
             source_url_or_evidence=f"https://hn.example.com/{acc}",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="reddit",
             source_url_or_evidence=f"https://reddit.example.com/{acc}",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec",
             source_url_or_evidence="https://sec.gov/unrelated-doc",
             title_or_label="Cloud outage hits region", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1   # weak publishable 로 발행 안 함
    assert await _count(session, "events") == 0
    assert await _count(session, "event_updates") == 0


async def test_live_weak_cluster_news_community_withheld(session):
    # ADR#37 weak-cluster gate: 약신호 news+community(다른 canonical·유사 제목) → WITHHELD(실 DB 영속 0).
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    recs = [
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/q1",
             title_or_label="Port strike halts container traffic", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="community_signal", source_id="hn", canonical_url="https://news.ycombinator.com/q",
             title_or_label="Port strike halts container traffic", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 0 and summary.withheld_source_type == 1
    assert await _count(session, "events") == 0


async def test_live_weak_cluster_news_news_publishes(session):
    # ADR#37: 약신호 news+news(전원 publishable) → 발행(실 DB 1 Event). ADR#29 검증 흐름 보존.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    recs = [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/r1",
             title_or_label="Coastal refinery fire forces evacuation", published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/r2",
             title_or_label="Coastal refinery fire forces evacuation nearby", published_at_or_observed_at="2025-06-02"),
    ]
    summary = await ingest_records_to_events(session, recs, enabled=True)
    assert summary.created == 1 and summary.withheld_source_type == 0
    # 약신호라 weak_only news 1건은 held degenerate(possible_link)로 분리 보류 → events=1 primary + 1 held.
    assert summary.held_member_links == 1
    assert await _count(session, "events") == 2


# ── held 승격 (ADR#38) ─────────────────────────────────────────────────────────
_HP_T = "Reactor scram at coastal nuclear plant"
_ACC_A = "0001193125-26-000111"
_ACC_B = "0001193125-26-000222"


def _held_batch1(title=_HP_T):
    # 강신호 news core(accA, 다른 canonical) + official 약신호 title-link → CREATE P(news), official held.
    return [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/p1",
             source_url_or_evidence=f"https://ap.com/Archives/{_ACC_A}", title_or_label=title,
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/p2",
             source_url_or_evidence=f"https://reuters.com/Archives/{_ACC_A}", title_or_label=title,
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="official_record", source_id="sec", canonical_url="https://sec.gov/o-doc",
             title_or_label=title, published_at_or_observed_at="2025-06-02"),
    ]


def _held_batch2_official(title):
    # official(batch1 과 같은 canonical=같은 key) 재등장 + official2 강신호(accB).
    return [
        _rec(record_type="official_record", source_id="sec", canonical_url="https://sec.gov/o-doc",
             source_url_or_evidence=f"https://sec.gov/Archives/{_ACC_B}", title_or_label=title,
             published_at_or_observed_at="2025-06-03"),
        _rec(record_type="official_record", source_id="sec2", canonical_url="https://sec.gov/o-doc2",
             source_url_or_evidence=f"https://sec.gov/data/{_ACC_B}", title_or_label=title,
             published_at_or_observed_at="2025-06-03"),
    ]


async def test_live_held_promotion_same_title_appends_to_parent(session):
    # ADR#38: 약신호로 held 된 official 이 나중에 강신호로 재등장 + 제목 동일 → **새 중복 Event 대신 parent APPEND**.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    s1 = await ingest_records_to_events(session, _held_batch1(), enabled=True)
    assert s1.created == 1 and s1.held_member_links == 1          # P + official held
    assert await _count(session, "events") == 2                  # P + held degenerate
    s2 = await ingest_records_to_events(session, _held_batch2_official(_HP_T), enabled=True)
    assert s2.created == 0 and s2.appended == 1                  # 중복 Event 0 — parent 로 승격 APPEND
    assert await _count(session, "events") == 2                  # 새 Event 없음(여전히 P + held)


async def test_live_held_promotion_different_title_creates_independent(session):
    # ADR#38 false-merge 방어: held official 재등장 강신호지만 **제목 무관** → parent 병합 안 함, 독립 Event CREATE.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    s1 = await ingest_records_to_events(session, _held_batch1(), enabled=True)
    assert s1.created == 1 and await _count(session, "events") == 2
    s2 = await ingest_records_to_events(
        session, _held_batch2_official("Unrelated harbor crane maintenance notice"), enabled=True
    )
    assert s2.created == 1 and s2.appended == 0                  # 독립 Event(병합 안 함)
    assert await _count(session, "events") == 3                  # P + held + Q(독립)


async def test_live_held_promotion_idempotent_on_reprocess(session):
    # ADR#38: 승격(parent APPEND) 후 같은 batch2 재처리 → cluster_id→parent 매핑으로 멱등(중복 APPEND/Event 0).
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events

    await ingest_records_to_events(session, _held_batch1(), enabled=True)
    await ingest_records_to_events(session, _held_batch2_official(_HP_T), enabled=True)
    n_events = await _count(session, "events")
    n_updates = await _count(session, "event_updates")
    s3 = await ingest_records_to_events(session, _held_batch2_official(_HP_T), enabled=True)
    assert s3.created == 0                                       # 재처리 → 새 Event 0
    assert await _count(session, "events") == n_events          # Event 수 불변(멱등)
    # 같은 cluster_id 가 mapped → APPEND(append-only 관측은 1행 늘 수 있으나 새 Event/held 중복 0)
    assert await _count(session, "event_updates") >= n_updates


# ── cross-batch event identity (ADR#40, R-CrossBatchEventIdentity) ──────────────
from dataclasses import dataclass as _dataclass


@_dataclass(frozen=True)
class _IdCluster:
    """cluster_id 를 명시 제어해 identity 층을 격리 검증하는 cluster-like(duck-typed)."""
    cluster_id: str
    duplicate_group: tuple = ()
    confidence: str = "duplicate"
    clique_ok: bool = True
    weak_only_members: tuple = ()


def _id_cand(observed, identity_keys, title="호르무즈 해협 긴장"):
    return ResolvedCandidate(
        canonical_title=title, observed_at=observed, delta_summary="update",
        evidence=({"source_type": "article", "relation": "primary"},),
        core_source_types=("article",), identity_keys=identity_keys,
    )


async def test_live_cross_batch_same_identity_appends_not_new_event(session):
    # ADR#40: batch1 이 identity anchor K 를 claim → batch2 가 **다른 cluster_id** 지만 같은 anchor K 를
    # 가지면 새 Event 가 아니라 기존 Event 로 APPEND(같은 사건 분열 0 = UNDER-merge 방지).
    c1 = _IdCluster(cluster_id="xcluster:b1", duplicate_group=("canon:K", "canon:o1"))
    r1 = await pipe.resolve_and_apply_cluster(session, c1, candidate=_id_cand(_T2, ("canon:K",)))
    assert r1.action == ACTION_CREATE
    assert await _count(session, "events") == 1
    assert await _count(session, "event_identity_map") == 1     # anchor K claimed by E1

    c2 = _IdCluster(cluster_id="xcluster:b2", duplicate_group=("canon:K", "canon:o2"))
    r2 = await pipe.resolve_and_apply_cluster(session, c2, candidate=_id_cand(_T3, ("canon:K",)))
    assert r2.action == ACTION_APPEND
    assert r2.event_id == r1.event_id                           # 같은 Event 로 수렴
    assert await _count(session, "events") == 1                 # 분열 0


async def test_live_cross_batch_different_identity_creates_new(session):
    # ADR#40 false-merge 방어: 공유 anchor 없으면(다른 사건) 독립 CREATE — 무차별 병합 금지.
    c1 = _IdCluster(cluster_id="xcluster:b1", duplicate_group=("canon:K1",))
    await pipe.resolve_and_apply_cluster(session, c1, candidate=_id_cand(_T2, ("canon:K1",)))
    c2 = _IdCluster(cluster_id="xcluster:b2", duplicate_group=("canon:K2",))
    r2 = await pipe.resolve_and_apply_cluster(
        session, c2, candidate=_id_cand(_T3, ("canon:K2",), title="전혀 다른 사건")
    )
    assert r2.action == ACTION_CREATE
    assert await _count(session, "events") == 2                 # 서로 다른 사건 분리 유지


async def test_live_cross_batch_ambiguous_identity_does_not_merge(session):
    # ADR#40 보수: 한 cluster 가 서로 다른 두 기존 Event 의 anchor 를 동시에 가지면(모호) 자동 병합 안 함
    # (둘을 잘못 합치지 않는다 — CREATE; 향후 HOLD_REVIEW 는 이월).
    c1 = _IdCluster(cluster_id="xcluster:b1", duplicate_group=("canon:A",))
    await pipe.resolve_and_apply_cluster(session, c1, candidate=_id_cand(_T2, ("canon:A",), title="사건 A"))
    c2 = _IdCluster(cluster_id="xcluster:b2", duplicate_group=("canon:B",))
    await pipe.resolve_and_apply_cluster(session, c2, candidate=_id_cand(_T2, ("canon:B",), title="사건 B"))
    assert await _count(session, "events") == 2
    c3 = _IdCluster(cluster_id="xcluster:b3", duplicate_group=("canon:A", "canon:B"))
    r3 = await pipe.resolve_and_apply_cluster(
        session, c3, candidate=_id_cand(_T3, ("canon:A", "canon:B"), title="A·B 브릿지")
    )
    assert r3.action == ACTION_CREATE                           # 모호 → 자동 병합 안 함
    assert await _count(session, "events") == 3


async def test_live_cross_batch_identity_idempotent(session):
    # 같은 batch2 재처리 → cluster_id 매핑·identity 모두 멱등(새 Event 0).
    c1 = _IdCluster(cluster_id="xcluster:b1", duplicate_group=("canon:K",))
    await pipe.resolve_and_apply_cluster(session, c1, candidate=_id_cand(_T2, ("canon:K",)))
    c2 = _IdCluster(cluster_id="xcluster:b2", duplicate_group=("canon:K",))
    await pipe.resolve_and_apply_cluster(session, c2, candidate=_id_cand(_T3, ("canon:K",)))
    n = await _count(session, "events")
    await pipe.resolve_and_apply_cluster(session, c2, candidate=_id_cand(_T3, ("canon:K",)))
    assert await _count(session, "events") == n                 # 멱등(분열/중복 0)


def _xb_batch1():
    # 강신호 news cluster(ap+reuters via ACC_A), 둘 다 canonical → core identity anchor 2개 claim.
    return [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/x1",
             source_url_or_evidence=f"https://ap.com/Archives/{_ACC_A}", title_or_label="Reactor event",
             published_at_or_observed_at="2025-06-02"),
        _rec(record_type="article_candidate", source_id="reuters", canonical_url="https://reuters.com/x2",
             source_url_or_evidence=f"https://reuters.com/Archives/{_ACC_A}", title_or_label="Reactor event",
             published_at_or_observed_at="2025-06-02"),
    ]


def _xb_batch2():
    # ap 재등장(같은 canonical=같은 anchor) + 새 cnn(다른 canonical) via ACC_B → 다른 cluster.
    return [
        _rec(record_type="article_candidate", source_id="ap", canonical_url="https://ap.com/x1",
             source_url_or_evidence=f"https://ap.com/data/{_ACC_B}", title_or_label="Reactor event",
             published_at_or_observed_at="2025-06-03"),
        _rec(record_type="article_candidate", source_id="cnn", canonical_url="https://cnn.com/x3",
             source_url_or_evidence=f"https://cnn.com/data/{_ACC_B}", title_or_label="Reactor event",
             published_at_or_observed_at="2025-06-03"),
    ]


async def test_live_cross_batch_ingest_shared_article_no_split(session):
    # ADR#40 E2E: 같은 기사(ap, 동일 canonical)가 다음 배치에서 새 기사(cnn)와 다른 cluster 로 묶여도
    # identity anchor 로 기존 Event 에 APPEND → 같은 사건이 배치마다 분열되지 않음.
    from backend.app.services.event_ingest_pipeline import ingest_records_to_events
    s1 = await ingest_records_to_events(session, _xb_batch1(), enabled=True)
    assert s1.created == 1 and await _count(session, "events") == 1
    s2 = await ingest_records_to_events(session, _xb_batch2(), enabled=True)
    assert s2.created == 0 and s2.appended == 1                 # 새 Event 0·기존 APPEND(분열 방지)
    assert await _count(session, "events") == 1


async def test_live_catalog_source_type_withheld(session):
    # R-SourceCatalogFidelity(ADR#40): catalog source_type 은 비-publishable → 단독 cross-source WITHHELD.
    c = _IdCluster(cluster_id="xcluster:cat", duplicate_group=("canon:cat1", "canon:cat2"))
    cand = ResolvedCandidate(
        canonical_title="어떤 영화 메타", observed_at=_T2, delta_summary="x",
        evidence=({"source_type": "catalog", "relation": "primary"},),
        core_source_types=("catalog", "catalog"),
    )
    res = await pipe.resolve_and_apply_cluster(session, c, candidate=cand)
    assert res.action == "WITHHELD"                            # catalog 메타는 official Event 로 발행 안 됨
    assert await _count(session, "events") == 0


# ── deterministic semantic cross-batch identity 후보 (ADR#41) ────────────────────
def _sem_cand(observed, fingerprints, title="연준 기준금리 인상 결정", source_types=("article",)):
    return ResolvedCandidate(
        canonical_title=title, observed_at=observed, delta_summary="update",
        evidence=({"source_type": source_types[0], "relation": "primary"},),
        core_source_types=source_types, semantic_fingerprints=fingerprints,
    )


async def test_live_semantic_candidate_links_not_merges(session):
    # ADR#41(scenario 30): 공유 strong anchor 없이 같은 semantic fingerprint → **병합 아님**,
    # event_links(possible) 후보 링크(분열을 표면화하되 false-merge 0). 실제 병합은 semantic adjudicator 이월.
    c1 = _IdCluster(cluster_id="xcluster:s1", duplicate_group=("canon:a",))
    r1 = await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:F",)))
    assert r1.action == ACTION_CREATE
    assert await _count(session, "event_identity_candidate") == 1   # E1 이 fingerprint F claim
    c2 = _IdCluster(cluster_id="xcluster:s2", duplicate_group=("canon:b",))
    r2 = await pipe.resolve_and_apply_cluster(
        session, c2, candidate=_sem_cand(_T3, ("sem:F",), title="연준 금리 인상")
    )
    assert r2.action == ACTION_CREATE                               # 독립 Event(자동 병합 0)
    assert await _count(session, "events") == 2                     # E1 + E2 (false-merge surface 0)
    links = (await session.execute(text(
        "SELECT status, reason, event_id::text, linked_event_id::text FROM event_links"
    ))).all()
    assert len(links) == 1
    assert links[0][0] == "possible" and links[0][1] == "semantic_cross_batch_candidate"
    assert links[0][2] == r2.event_id and links[0][3] == r1.event_id   # E2 → E1 후보 링크


async def test_live_semantic_ambiguous_no_link(session):
    # ADR#41(scenario 31): 한 cluster fingerprints 가 서로 다른 두 Event 를 가리키면(모호) → 링크 안 함, 독립 CREATE.
    c1 = _IdCluster(cluster_id="xcluster:s1", duplicate_group=("canon:a",))
    await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:F1",), title="사건 A 보도 묶음"))
    c2 = _IdCluster(cluster_id="xcluster:s2", duplicate_group=("canon:b",))
    await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T2, ("sem:F2",), title="사건 B 보도 묶음"))
    assert await _count(session, "events") == 2
    c3 = _IdCluster(cluster_id="xcluster:s3", duplicate_group=("canon:c",))
    r3 = await pipe.resolve_and_apply_cluster(
        session, c3, candidate=_sem_cand(_T3, ("sem:F1", "sem:F2"), title="A·B 양쪽 언급")
    )
    assert r3.action == ACTION_CREATE and await _count(session, "events") == 3
    sem = (await session.execute(text(
        "SELECT count(*) FROM event_links WHERE reason='semantic_cross_batch_candidate'"
    ))).scalar_one()
    assert sem == 0                                                 # 모호 → 후보 링크 0


async def test_live_semantic_no_match_creates_independent(session):
    # ADR#41(scenario 33 회귀): 후보 없는 fingerprint → 독립 CREATE·링크 0(정상 신규, 오링크 0).
    c1 = _IdCluster(cluster_id="xcluster:s1", duplicate_group=("canon:a",))
    await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:F",)))
    c2 = _IdCluster(cluster_id="xcluster:s2", duplicate_group=("canon:b",))
    r2 = await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T3, ("sem:G",), title="다른 사건"))
    assert r2.action == ACTION_CREATE and await _count(session, "events") == 2
    assert await _count(session, "event_links") == 0


async def test_live_semantic_non_publishable_withheld_no_claim_no_link(session):
    # source role 우선(ADR#33/#41, scenario 32): 비-publishable(community) candidate 는 fingerprint 가 있어도
    # WITHHELD → 새 Event 0·fingerprint claim 0·링크 0(미발행 사건에 cross-batch 동일성 부여 금지).
    c0 = _IdCluster(cluster_id="xcluster:pub", duplicate_group=("canon:a",))
    await pipe.resolve_and_apply_cluster(session, c0, candidate=_sem_cand(_T2, ("sem:F",)))   # E1 claims F
    c1 = _IdCluster(cluster_id="xcluster:com", duplicate_group=("canon:c1", "canon:c2"))
    r1 = await pipe.resolve_and_apply_cluster(
        session, c1, candidate=_sem_cand(_T3, ("sem:F",), title="커뮤니티만", source_types=("community",))
    )
    assert r1.action == "WITHHELD"
    assert await _count(session, "events") == 1                    # 새 Event 0(WITHHELD)
    assert await _count(session, "event_identity_candidate") == 1  # community 는 claim 0(E1 것만 유지)
    assert await _count(session, "event_links") == 0               # 미발행 → 링크 0


# ── semantic identity adjudicator shadow/eval (ADR#42) ──────────────────────────
from backend.app.services import semantic_identity_adjudicator as adjmod


async def _make_semantic_link(session, title="연준 기준금리 인상 결정 발표"):
    # ADR#41 경로로 cross-batch semantic 후보 link 1개 생성(다른 cluster·같은 fingerprint·publishable).
    c1 = _IdCluster(cluster_id="xcluster:adj1", duplicate_group=("canon:a",))
    r1 = await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:F",), title=title))
    c2 = _IdCluster(cluster_id="xcluster:adj2", duplicate_group=("canon:b",))
    r2 = await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T3, ("sem:F",), title=title))
    return r1.event_id, r2.event_id


async def test_live_adjudicator_consumes_link_and_persists_status(session):
    # ADR#42(scenario 23·24): semantic 후보 link 를 소비해 status 산출·영속(소비처 #1). Event 불변.
    await _make_semantic_link(session)
    assert await _count(session, "event_links") == 1
    events_before = await _count(session, "events")
    report = await adjmod.generate_shadow_adjudication_report(session)
    assert report["total"] == 1 and report["auto_merged"] == 0
    assert await _count(session, "events") == events_before              # Event count 불변(merge 0)
    assert await _count(session, "event_identity_adjudication") == 1      # status 영속(소비처 생성)
    st = (await session.execute(text("SELECT status FROM event_identity_adjudication"))).scalar_one()
    assert st == "likely_same_event"   # 같은 token-set·근접 시점·publishable → 결정론 likely_same


async def test_live_adjudicator_no_merge_event_count_unchanged(session):
    # ADR#42(scenario 25): adjudication 이 events/cluster_event_map/event_updates 를 변경하지 않는다(shadow).
    await _make_semantic_link(session)
    before_e = await _count(session, "events")
    before_m = await _count(session, "cluster_event_map")
    before_u = await _count(session, "event_updates")
    await adjmod.adjudicate_semantic_links(session)
    assert await _count(session, "events") == before_e                   # 자동 병합 0
    assert await _count(session, "cluster_event_map") == before_m
    assert await _count(session, "event_updates") == before_u            # append 0(genesis 그대로)


async def test_live_adjudicator_idempotent_no_duplicate_row(session):
    # ADR#42(scenario 26): 재실행 → link_id PK upsert 로 중복 row 0.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    n = await _count(session, "event_identity_adjudication")
    await adjmod.adjudicate_semantic_links(session)
    assert await _count(session, "event_identity_adjudication") == n == 1


async def test_live_adjudicator_no_links_empty_report(session):
    # semantic link 0 → report total 0·adjudication 0(빈 입력 안전·영속 0).
    report = await adjmod.generate_shadow_adjudication_report(session)
    assert report["total"] == 0
    assert await _count(session, "event_identity_adjudication") == 0


async def test_live_adjudicator_ambiguous_multiple_candidates(session):
    # candidate Event 하나가 서로 다른 기존 Event 2개와 semantic link → 모호(ambiguous). 자동 병합 0.
    # 세 Event 를 각각 다른 fingerprint 로 CREATE(genesis article evidence 보유)한 뒤, 한 candidate(E3)가
    # E1·E2 양쪽과 possible 링크를 갖도록 직접 구성(모호 상황). 직접 create_event 는 evidence 가 없어
    # fail-closed insufficient 가 되므로 publishable genesis 가 있는 CREATE 경로 Event 를 쓴다.
    # 세 Event 모두 유사 제목(같은 token-set) — 현실적 모호 상황: 한 candidate(E3)가 같은 사건 후보 2개
    # (E1·E2)와 동시 link. fingerprint 는 테스트 격리를 위해 다르게 줘 자동 병합/자동 link 를 방지(직접 구성).
    title = "연준 기준금리 인상 결정 발표"
    c1 = _IdCluster(cluster_id="xcluster:m1", duplicate_group=("canon:a",))
    r1 = await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:F1",), title=title))
    c2 = _IdCluster(cluster_id="xcluster:m2", duplicate_group=("canon:b",))
    r2 = await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T2, ("sem:F2",), title=title))
    c3 = _IdCluster(cluster_id="xcluster:m3", duplicate_group=("canon:c",))
    r3 = await pipe.resolve_and_apply_cluster(session, c3, candidate=_sem_cand(_T3, ("sem:F3",), title=title))
    await svc.hold_link(session, event_id=r3.event_id, linked_event_id=r1.event_id, reason=adjmod.SEMANTIC_LINK_REASON)
    await svc.hold_link(session, event_id=r3.event_id, linked_event_id=r2.event_id, reason=adjmod.SEMANTIC_LINK_REASON)
    before_e = await _count(session, "events")
    results = await adjmod.adjudicate_semantic_links(session)
    assert len(results) == 2 and all(r.status == "ambiguous" for r in results)   # 다중 후보 → 모두 ambiguous
    assert await _count(session, "events") == before_e                   # 자동 병합 0


# ── identity eval pair export — adjudication 소비처 (ADR#43) ──────────────────────
from backend.app.tools import export_identity_eval_pairs as exmod


async def test_live_export_adjudication_pairs_no_pii(session):
    # ADR#43(scenario 43·27·29): adjudication 행 → human-labeling 워크시트(소비처). raw body/PII 0·Event 불변.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    before_e = await _count(session, "events")
    rows = await exmod.collect_adjudication_eval_pairs(session)
    assert len(rows) == 1
    exmod._assert_no_pii(rows)                              # allowlist 키만(body/PII 차단)
    r = rows[0]
    assert set(r) <= exmod._WORKSHEET_KEYS
    assert "body" not in r and "content" not in r and "author" not in r
    assert r["label"] == "unlabeled"                       # 사람이 gold 채움(워크시트≠gold)
    assert r["predicted_status"] in (
        "likely_same_event", "ambiguous", "likely_different_event", "insufficient_features")
    assert r["title_left"] and r["title_right"]
    assert await _count(session, "events") == before_e     # read-only(자동 병합 0)


async def test_live_export_backlog_summary(session):
    # ADR#43(scenario 44·25): backlog 분포 report(internal 소비처).
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    rows = await exmod.collect_adjudication_eval_pairs(session)
    summary = exmod.summarize_adjudication_backlog(rows)
    assert summary["total"] == 1 and summary["auto_merged"] == 0
    assert sum(summary["by_status"].values()) == 1


async def test_live_export_no_links_empty(session):
    # adjudication 0 → 워크시트 0(빈 입력 안전).
    rows = await exmod.collect_adjudication_eval_pairs(session)
    assert rows == []


async def test_live_export_roundtrip_to_jsonl(session, tmp_path):
    # ADR#43(scenario 26·28): 워크시트 JSONL 기록(deterministic·no-PII 검증 통과)·Event 불변.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    before_e = await _count(session, "events")
    rows = await exmod.collect_adjudication_eval_pairs(session)
    n = exmod.write_worksheet_jsonl(rows, tmp_path / "worksheet.jsonl")
    assert n == 1 and (tmp_path / "worksheet.jsonl").exists()
    assert await _count(session, "events") == before_e     # export 는 Event 불변


# ── identity human-labeled gold workflow — worksheet→gold roundtrip (ADR#44) ─────────
from backend.app.services import identity_human_labeling as hlmod


async def _export_and_promote_gold(session):
    # ADR#44 라이브 경로: semantic link → adjudication → 워크시트 export → 사람이 gold 로 승격(시뮬).
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    rows = await exmod.collect_adjudication_eval_pairs(session)
    gold_rows = [
        hlmod.promote_worksheet_to_gold(
            r, label="same_event", reviewed_by="sample_reviewer",
            reviewed_at="2026-06-24T18:00:00Z", review_status="gold",
            label_confidence="high", dataset_source=hlmod.SOURCE_LIVE,
        )
        for r in rows
    ]
    return rows, gold_rows


async def test_live_export_promote_gold_import_validate(session, tmp_path):
    # ADR#44(scenario 46·47): 워크시트 → gold 승격 → 기록·검증·로드. gold workflow 가 Event 불변.
    _ws, gold_rows = await _export_and_promote_gold(session)
    after_link_e = await _count(session, "events")   # ADR#41 link 경로가 만든 Event(정상). 이후 불변 기준.
    assert len(gold_rows) == 1
    p = tmp_path / "gold.jsonl"
    assert hlmod.write_gold_jsonl(gold_rows, p) == 1
    loaded = hlmod.load_gold_pairs(p)
    assert len(loaded) == 1 and loaded[0].review_status == "gold"
    assert loaded[0].dataset_source == hlmod.SOURCE_LIVE     # live-derived marker 보존
    assert await _count(session, "events") == after_link_e   # gold 기록/로드는 Event 불변(병합 0)


async def test_live_gold_report_no_merge_and_readiness_off(session):
    # ADR#44(scenario 48·49): live-derived gold report — readiness False·자동 병합 OFF·Event 불변.
    _ws, gold_rows = await _export_and_promote_gold(session)
    after_link_e = await _count(session, "events")
    pairs = [hlmod.GoldPair(
        pair_id=r["pair_id"], label=r["label"], language=r["language"],
        source_type_left=r["source_type_left"], source_type_right=r["source_type_right"],
        title_left=r["title_left"], title_right=r["title_right"],
        observed_at_left=r["observed_at_left"], observed_at_right=r["observed_at_right"],
        reviewed_by=r["reviewed_by"], reviewed_at=r["reviewed_at"],
        review_status=r["review_status"], label_confidence=r["label_confidence"],
        dataset_source=r["dataset_source"], risk_tags=tuple(r.get("risk_tags", [])),
    ) for r in gold_rows]
    rep = hlmod.generate_gold_eval_report(pairs)
    assert rep["auto_merged"] == 0
    mr = rep["merge_readiness"]
    assert mr["live_sample_ok"] is False           # 1행 << floor(200)
    assert mr["merge_ready"] is False and mr["auto_merge_enabled"] is False
    assert await _count(session, "events") == after_link_e   # report 산출은 Event 불변


async def test_live_gold_roundtrip_idempotent(session, tmp_path):
    # ADR#44(scenario 50): 같은 export→promote→write 재실행 → 같은 gold 파일(결정론)·Event 불변.
    _ws, gold_rows = await _export_and_promote_gold(session)
    after_link_e = await _count(session, "events")
    p = tmp_path / "gold.jsonl"
    hlmod.write_gold_jsonl(gold_rows, p)
    t1 = p.read_text(encoding="utf-8")
    hlmod.write_gold_jsonl(gold_rows, p)
    assert t1 == p.read_text(encoding="utf-8")
    assert await _count(session, "events") == after_link_e


# ── reviewer agreement protocol — worksheet→multi-reviewer→resolved gold (ADR#45) ────
async def _export_and_build_reviewer_labels(session, *, second_label=None):
    # ADR#45 라이브 경로: 워크시트 → 2 reviewer 가 라벨(동일=agreed; 다르면 conflict 시뮬).
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    rows = await exmod.collect_adjudication_eval_pairs(session)
    labels = []
    for r in rows:
        for rid, lab, at in (("reviewer-a", "same_event", "2026-06-24T18:00:00Z"),
                             ("reviewer-b", second_label or "same_event", "2026-06-24T18:05:00Z")):
            labels.append(hlmod.ReviewerLabel(
                pair_id=r["pair_id"], reviewer_id=rid, review_round=1, label=lab,
                label_confidence="high", reviewed_at=at, language=r["language"],
                source_type_left=r["source_type_left"], source_type_right=r["source_type_right"],
                title_left=r["title_left"], title_right=r["title_right"],
                observed_at_left=r["observed_at_left"], observed_at_right=r["observed_at_right"],
                dataset_source=hlmod.SOURCE_LIVE,
            ))
    return labels


async def test_live_reviewer_agreement_resolves_gold(session):
    # ADR#45(scenario 48·49): 2 reviewer 합의 → resolved gold·agreement report. Event 불변.
    labels = await _export_and_build_reviewer_labels(session)
    after_link_e = await _count(session, "events")
    res = hlmod.resolve_gold_from_reviewers(labels)
    assert len(res) == 1 and res[0].agreement_status == hlmod.AGREE_AGREED
    assert res[0].review_status == hlmod.REVIEW_GOLD
    rep = hlmod.generate_labeling_protocol_report(labels)
    assert rep["resolved_gold_count"] == 1 and rep["conflict_count"] == 0
    assert rep["auto_merged"] == 0
    assert await _count(session, "events") == after_link_e


async def test_live_reviewer_conflict_no_auto_gold(session):
    # ADR#45(scenario 51): reviewer 불일치 → conflict(자동 gold 금지)·Event 불변.
    labels = await _export_and_build_reviewer_labels(session, second_label="different_event")
    after_link_e = await _count(session, "events")
    res = hlmod.resolve_gold_from_reviewers(labels)
    assert res[0].agreement_status == hlmod.AGREE_CONFLICT
    assert res[0].review_status == hlmod.REVIEW_NEEDS    # 자동 gold 금지
    assert hlmod.resolved_to_gold_pairs(res) == []        # gold 0
    assert await _count(session, "events") == after_link_e


async def test_live_reviewer_protocol_merge_readiness_false(session):
    # ADR#45(scenario 50): protocol report merge readiness False·auto-merge OFF·Event 불변.
    labels = await _export_and_build_reviewer_labels(session)
    after_link_e = await _count(session, "events")
    rep = hlmod.generate_labeling_protocol_report(labels)
    gm = rep["gold_metrics"]
    assert gm is not None
    assert gm["merge_readiness"]["merge_ready"] is False
    assert gm["merge_readiness"]["auto_merge_enabled"] is False
    assert await _count(session, "events") == after_link_e


async def test_live_reviewer_resolution_idempotent(session):
    # ADR#45(scenario 52): 같은 label 재resolve → 같은 결과(결정론)·Event 불변.
    labels = await _export_and_build_reviewer_labels(session)
    after_link_e = await _count(session, "events")
    a = hlmod.generate_labeling_protocol_report(labels)
    b = hlmod.generate_labeling_protocol_report(labels)
    assert a == b
    assert await _count(session, "events") == after_link_e


# ── live-derived labeling packet + sampling report (ADR#46) ──────────────────────────
async def _live_worksheet(session):
    # ADR#46 라이브 경로: semantic link → adjudication → 워크시트 export(소비처). packet 입력.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    return await exmod.collect_adjudication_eval_pairs(session)


async def test_live_packet_build_validate_no_verdict(session):
    # ADR#46(scenario 47·48): live 워크시트 → packet build·validate. predicted_status 차폐·Event 불변.
    rows = await _live_worksheet(session)
    after_link_e = await _count(session, "events")
    assert len(rows) == 1
    items = hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    assert len(items) == 2                                   # 1 pair × 2 reviewer
    dicts = [hlmod.packet_item_to_dict(it) for it in items]
    hlmod.validate_labeling_packet(dicts)                    # allowlist/verdict/enum 통과
    for d in dicts:
        assert "predicted_status" not in d and "score" not in d and "reason" not in d and "label" not in d
        assert d["pair_id"] == str(rows[0]["pair_id"])
    assert await _count(session, "events") == after_link_e   # packet 생성은 Event 불변(자동 병합 0)


async def test_live_packet_sampling_report(session):
    # ADR#46(scenario 49): live 워크시트 sampling report — selected/deficit/floor·Event 불변.
    rows = await _live_worksheet(session)
    after_link_e = await _count(session, "events")
    items = hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    rep = hlmod.summarize_packet_sampling(rows, packet_items=items)
    assert rep["total_candidates"] == 1 and rep["selected_count"] == 1
    assert rep["reviewer_assignment_count"] == 2
    assert rep["auto_merged"] == 0
    # live 후보 1개 << floor → deficit 정직 노출(평균에 숨기지 않음).
    assert rep["floor_check"]["positive_deficit"] > 0 or rep["floor_check"]["negative_deficit"] > 0
    assert rep["unclassified"] == 0
    assert await _count(session, "events") == after_link_e


async def test_live_packet_reviewer_roundtrip_no_auto_merge(session):
    # ADR#46(scenario 50): packet → reviewer label(2명 합의) → resolved gold·merge readiness False·Event 불변.
    rows = await _live_worksheet(session)
    after_link_e = await _count(session, "events")
    items = hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    labels = [
        hlmod.ReviewerLabel(
            pair_id=it.pair_id, reviewer_id=it.reviewer_id, review_round=it.review_round,
            label="same_event", label_confidence="high", reviewed_at="2026-06-24T18:00:00Z",
            language=it.language, source_type_left=it.source_type_left, source_type_right=it.source_type_right,
            title_left=it.title_left, title_right=it.title_right,
            observed_at_left=it.observed_at_left, observed_at_right=it.observed_at_right,
            dataset_source=hlmod.SOURCE_LIVE,
        )
        for it in items
    ]
    rep = hlmod.generate_labeling_protocol_report(labels)
    assert rep["resolved_gold_count"] == 1 and rep["conflict_count"] == 0
    assert rep["gold_metrics"]["merge_readiness"]["merge_ready"] is False
    assert rep["gold_metrics"]["merge_readiness"]["auto_merge_enabled"] is False
    assert rep["auto_merged"] == 0
    assert await _count(session, "events") == after_link_e


async def test_live_packet_conflict_to_adjudication_queue(session):
    # ADR#46(scenario 51): packet → reviewer 불일치 → conflict → adjudication queue(자동 gold 금지)·Event 불변.
    rows = await _live_worksheet(session)
    after_link_e = await _count(session, "events")
    items = hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    labels = []
    for it, lab in zip(items, ("same_event", "different_event")):
        labels.append(hlmod.ReviewerLabel(
            pair_id=it.pair_id, reviewer_id=it.reviewer_id, review_round=it.review_round,
            label=lab, label_confidence="high", reviewed_at="2026-06-24T18:00:00Z",
            language=it.language, source_type_left=it.source_type_left, source_type_right=it.source_type_right,
            title_left=it.title_left, title_right=it.title_right,
            observed_at_left=it.observed_at_left, observed_at_right=it.observed_at_right,
            dataset_source=hlmod.SOURCE_LIVE,
        ))
    resolved = hlmod.resolve_gold_from_reviewers(labels)
    assert resolved[0].agreement_status == hlmod.AGREE_CONFLICT
    q = hlmod.adjudication_queue_from_resolved(resolved)
    assert len(q) == 1 and q[0]["needs_human_adjudication"] is True
    assert hlmod.resolved_to_gold_pairs(resolved) == []      # conflict → gold 0
    assert await _count(session, "events") == after_link_e


async def test_live_packet_idempotent_and_event_unchanged(session):
    # ADR#46(scenario 52·53): 같은 워크시트 재build → 같은 packet(결정론)·Event 불변.
    rows = await _live_worksheet(session)
    after_link_e = await _count(session, "events")
    a = [hlmod.packet_item_to_dict(it)
         for it in hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])]
    b = [hlmod.packet_item_to_dict(it)
         for it in hlmod.build_labeling_packet(rows, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])]
    assert a == b
    assert await _count(session, "events") == after_link_e


# ── live-derived labeling packet pilot tool (ADR#47) ─────────────────────────────────
import tempfile

from backend.app.tools import build_live_identity_labeling_packet as livemod


async def test_live_tool_no_candidates_empty_report(session):
    # ADR#47(scenario 1·7): semantic link 0 → report 전부 0·exclusion 0·Event 불변(정직한 빈 백로그).
    before_e = await _count(session, "events")
    rep = await livemod.generate_live_packet_report(
        session, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    assert rep["total_candidate_links"] == 0 and rep["total_adjudications"] == 0
    assert rep["eligible_for_packet"] == 0 and rep["selected_count"] == 0
    assert rep["live_selected_count"] == 0 and rep["reviewer_assignment_count"] == 0
    assert rep["exclusion_reasons"][livemod.EXCL_LINK_NO_ADJUDICATION] == 0
    assert rep["auto_merge_enabled"] is False
    assert rep["event_count_before"] == rep["event_count_after"] == before_e


async def test_live_tool_backlog_probe_link_without_adjudication(session):
    # ADR#47(scenario 1·4): semantic link 1 있으나 adjudication 미실행(stage ③ 미배선) →
    # eligible 0·exclusion semantic_link_without_adjudication=1(왜 0 인지 표면화). Event 불변.
    await _make_semantic_link(session)
    before_e = await _count(session, "events")
    rows, backlog = await livemod.collect_live_identity_candidates(session)
    assert rows == []
    assert backlog["total_candidate_links"] == 1
    assert backlog["total_adjudications"] == 0
    assert backlog["eligible_for_packet"] == 0
    assert backlog["exclusion_reasons"][livemod.EXCL_LINK_NO_ADJUDICATION] == 1
    assert await _count(session, "events") == before_e          # read-only


async def test_live_tool_packet_report_eligible_live_selected(session):
    # ADR#47(scenario 2·3·8·9): semantic link + adjudication → eligible 1·live_selected 1(실 파이프라인 유래·
    # synthetic 아님)·selected 1·Event 불변·자동 병합 0.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    before_e = await _count(session, "events")
    rep = await livemod.generate_live_packet_report(
        session, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    assert rep["total_candidate_links"] == 1 and rep["total_adjudications"] == 1
    assert rep["eligible_for_packet"] == 1
    assert rep["selected_count"] == 1
    assert rep["live_selected_count"] == 1                       # live-derived(synthetic 0)
    assert rep["live_vs_synthetic"][hlmod.SOURCE_LIVE] == 1
    assert rep["reviewer_assignment_count"] == 2                 # 1 pair × 2 reviewer
    assert rep["unclassified_count"] == 0
    assert rep["selection_method"] == hlmod.SELECTION_BUCKET_HASH
    assert rep["auto_merge_enabled"] is False
    assert rep["event_count_before"] == rep["event_count_after"] == before_e
    # live 후보 1 << floor → deficit 정직 노출.
    assert rep["floor_check"]["live_deficit"] > 0


async def test_live_tool_write_jsonl_roundtrip_event_unchanged(session):
    # ADR#47(scenario 17): live packet → JSONL(internal artifact·validate 통과)·Event 불변.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    before_e = await _count(session, "events")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "live_packet.jsonl")
        n = await livemod.write_live_labeling_packet_jsonl(
            session, path, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
        assert n == 2                                            # 1 pair × 2 reviewer
        import json as _json
        lines = [l for l in open(path, encoding="utf-8").read().splitlines() if l]
        assert len(lines) == 2
        dicts = [_json.loads(l) for l in lines]
        hlmod.validate_labeling_packet(dicts)                   # verdict/allowlist/enum 통과
        for dct in dicts:
            assert "predicted_status" not in dct and "score" not in dct
    assert await _count(session, "events") == before_e


async def test_live_tool_report_idempotent_event_unchanged(session):
    # ADR#47(scenario 18): 같은 백로그 재실행 → 같은 report(결정론)·Event 불변.
    await _make_semantic_link(session)
    await adjmod.adjudicate_semantic_links(session)
    before_e = await _count(session, "events")
    a = await livemod.generate_live_packet_report(
        session, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    b = await livemod.generate_live_packet_report(
        session, packet_id="pkt-live", reviewers=["reviewer-a", "reviewer-b"])
    assert a == b
    assert await _count(session, "events") == before_e


# ── stage③ shadow adjudication operational wiring + migration readiness (ADR#48) ────
from backend.app.services.event_ingest_pipeline import ingest_records_to_events
from backend.app.tools import identity_backlog_readiness as rdymod

# 배치 내부=같은 canonical 강신호 2건(단일 Event), 배치 간=canonical 다르게(공유 anchor 없음·fingerprint만 공유).
# 제목/날짜는 cross_source_dedup.semantic_identity_fingerprint 가 fingerprint 를 만드는 영어 강신호(검증된 형태).
_ADJ_TITLE = "Federal Reserve raises benchmark interest rates today"


def _sem_ingest_batch(canonical, *, title=_ADJ_TITLE, date="2026-06-24", s1="cnn", s2="npr"):
    return [
        _rec(source_id=s1, canonical_url=canonical, title_or_label=title, published_at_or_observed_at=date),
        _rec(source_id=s2, canonical_url=canonical, title_or_label=title, published_at_or_observed_at=date),
    ]


async def test_live_stage3_wiring_auto_adjudicates(session):
    # ADR#48(scenario 7·8): ingest(adjudicate_semantic=True) 가 배치 후 stage③ 를 자동 실행 → adjudication 누적
    # (수동 adjudicate 호출 0). events 분열 표면화(병합 0).
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://wire/x1"), enabled=True, adjudicate_semantic=True)
    s2 = await ingest_records_to_events(
        session, _sem_ingest_batch("https://cnn/y"), enabled=True, adjudicate_semantic=True)
    assert await _count(session, "events") == 2                        # 분열 표면화(자동 병합 0)
    assert await _count(session, "event_links") == 1                   # ② semantic 후보 link
    assert await _count(session, "event_identity_adjudication") == 1   # ③ 자동 누적(운영 배선)
    assert s2.adjudications == 1


async def test_live_stage3_wiring_off_no_adjudication(session):
    # ADR#48(scenario 14): adjudicate_semantic=False → link 은 생기되 ③ 미실행(게이트 입증).
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://wire/x1"), enabled=True, adjudicate_semantic=False)
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://cnn/y"), enabled=True, adjudicate_semantic=False)
    assert await _count(session, "event_links") == 1                   # ② link 은 생성
    assert await _count(session, "event_identity_adjudication") == 0   # ③ 미실행(off)


async def test_live_stage3_idempotent_and_no_merge(session):
    # ADR#48(scenario 11·12·46·47): 재실행 → stage③ upsert 멱등·events/cmap 불변(자동 병합 0).
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://wire/x1"), enabled=True, adjudicate_semantic=True)
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://cnn/y"), enabled=True, adjudicate_semantic=True)
    e = await _count(session, "events")
    cm = await _count(session, "cluster_event_map")
    await ingest_records_to_events(   # 재실행(같은 cluster_id mapped → APPEND) + stage③ 재실행
        session, _sem_ingest_batch("https://cnn/y"), enabled=True, adjudicate_semantic=True)
    assert await _count(session, "event_identity_adjudication") == 1   # 멱등(link_id PK upsert)
    assert await _count(session, "events") == e == 2                   # stage③ 자동 병합 0
    assert await _count(session, "cluster_event_map") == cm


async def test_live_ingest_to_packet_e2e_operational_backlog(session):
    # ADR#48(scenario 15·16·17): ingest(adjudicate_semantic=True) → 운영 백로그 → live packet eligible>0
    # **수동 adjudicate 호출 없이**(R-LiveIdentityBacklog 부분진전 입증). Event 불변.
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://wire/x1"), enabled=True, adjudicate_semantic=True)
    await ingest_records_to_events(
        session, _sem_ingest_batch("https://cnn/y"), enabled=True, adjudicate_semantic=True)
    before_e = await _count(session, "events")
    rep = await livemod.generate_live_packet_report(
        session, packet_id="pkt-ops", reviewers=["reviewer-a", "reviewer-b"])
    assert rep["total_adjudications"] == 1
    assert rep["eligible_for_packet"] == 1
    assert rep["live_selected_count"] == 1            # 운영 loop 유래(synthetic/수동 아님)
    assert rep["reviewer_assignment_count"] == 2
    assert rep["exclusion_reasons"][livemod.EXCL_LINK_NO_ADJUDICATION] == 0   # ③ 자동 실행됨 → 미배선 0
    assert rep["auto_merge_enabled"] is False
    assert rep["event_count_before"] == rep["event_count_after"] == before_e


async def test_live_migration_readiness_test_db_on_head(session):
    # ADR#48(scenario 1~6·48): test DB(event_intel_test)=HEAD → on_head·ready_for_stage3·non-destructive.
    rep = await rdymod.operational_db_readiness(session, db_name="event_intel_test")
    assert rep["on_head"] is True
    assert rep["behind_count"] == 0
    assert rep["ready_for_stage3"] is True
    assert rep["destructive_risk"] is False
    assert rep["tables_present"]["event_identity_adjudication"] is True
    assert rep["expected_head"] == "c9d0e1f2a3b4"


# ── incremental / no-cluster backfill adjudication (ADR#49) ─────────────────────────
from backend.app.tools import backfill_semantic_adjudications as bfmod


async def _make_two_semantic_links(session):
    # 2개 독립 semantic link(서로 다른 fingerprint·제목) → incremental limit/backfill 테스트용. 4 Event·2 link.
    for fp, title, ca, cb in (
        ("sem:G1", "연준 기준금리 인상 결정 발표", "g1a", "g1b"),
        ("sem:G2", "호르무즈 해협 유조선 나포 사건 발생", "g2a", "g2b"),
    ):
        c1 = _IdCluster(cluster_id=f"xc:{ca}", duplicate_group=(f"canon:{ca}",))
        await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, (fp,), title=title))
        c2 = _IdCluster(cluster_id=f"xc:{cb}", duplicate_group=(f"canon:{cb}",))
        await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T3, (fp,), title=title))


async def test_live_incremental_only_unadjudicated_skips_done(session):
    # ADR#49(scenario 1·2·4): only_unadjudicated → 미판정 link 만 처리·재실행 시 판정된 link skip(전수 재판정 회피·멱등).
    await _make_semantic_link(session)
    assert await _count(session, "event_links") == 1
    r1 = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True)
    assert len(r1) == 1 and await _count(session, "event_identity_adjudication") == 1
    r2 = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True)
    assert len(r2) == 0                                   # 이미 판정 → skip(O(N) 회피)
    assert await _count(session, "event_identity_adjudication") == 1


async def test_live_incremental_limit_bounded_chunk(session):
    # ADR#49(scenario 3·5·43): limit → 1회 chunk 상한·나머지는 다음 호출(결정론 bounded backfill).
    await _make_two_semantic_links(session)
    assert await _count(session, "event_links") == 2
    r1 = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True, limit=1)
    assert len(r1) == 1 and await _count(session, "event_identity_adjudication") == 1
    r2 = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True, limit=1)
    assert len(r2) == 1 and await _count(session, "event_identity_adjudication") == 2
    r3 = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True, limit=1)
    assert len(r3) == 0                                   # pending 0


async def test_live_backfill_tool_dry_run_then_persist(session):
    # ADR#49(scenario 13·14·45·46·47): backfill dry-run(영속 0·규모만) → persist(pending 감소)·Event 불변·멱등.
    await _make_semantic_link(session)
    before_e = await _count(session, "events")
    dry = await bfmod.backfill_semantic_adjudications(session, dry_run=True)
    assert dry["pending_before"] == 1 and dry["processed"] == 1
    assert dry["pending_after"] == 1                      # dry-run → 영속 0
    assert await _count(session, "event_identity_adjudication") == 0
    run = await bfmod.backfill_semantic_adjudications(session, dry_run=False)
    assert run["pending_before"] == 1 and run["processed"] == 1 and run["pending_after"] == 0
    assert run["auto_merge_enabled"] is False
    assert await _count(session, "event_identity_adjudication") == 1
    assert await _count(session, "events") == before_e == run["event_count_after"]
    rerun = await bfmod.backfill_semantic_adjudications(session, dry_run=False)
    assert rerun["processed"] == 0 and rerun["pending_before"] == 0   # 멱등(pending 0)


async def test_live_no_cluster_batch_backfills_pending(session):
    # ADR#49(scenario 9·11·44): semantic link 존재(미판정) + 클러스터 0 배치(adjudicate on) → no-cluster backfill 실행.
    await _make_semantic_link(session)                   # link 1·adjudication 0
    before_e = await _count(session, "events")
    summary = await ingest_records_to_events(session, [], enabled=True, adjudicate_semantic=True)
    assert summary.clusters_total == 0
    assert summary.adjudications == 1                     # 클러스터 0 이어도 pending backfill(early-return 제거)
    assert await _count(session, "event_identity_adjudication") == 1
    assert await _count(session, "events") == before_e    # 자동 병합 0


async def test_live_no_cluster_no_pending_noop(session):
    # ADR#49(scenario 10): 클러스터 0 + pending 0 → no-op(adjudication 0·Event 불변).
    summary = await ingest_records_to_events(session, [], enabled=True, adjudicate_semantic=True)
    assert summary.clusters_total == 0 and summary.adjudications == 0
    assert await _count(session, "event_identity_adjudication") == 0


async def test_live_backfill_packet_exclusion_decreases(session):
    # ADR#49(scenario 13~16): pending link → packet exclusion 1·eligible 0 → backfill → exclusion 0·eligible 1.
    await _make_semantic_link(session)                   # link 1·adjudication 0(pending)
    before_e = await _count(session, "events")
    _rows0, backlog0 = await livemod.collect_live_identity_candidates(session)
    assert backlog0["eligible_for_packet"] == 0
    assert backlog0["exclusion_reasons"][livemod.EXCL_LINK_NO_ADJUDICATION] == 1
    await bfmod.backfill_semantic_adjudications(session, dry_run=False)
    _rows1, backlog1 = await livemod.collect_live_identity_candidates(session)
    assert backlog1["eligible_for_packet"] == 1
    assert backlog1["exclusion_reasons"][livemod.EXCL_LINK_NO_ADJUDICATION] == 0   # 감소
    assert await _count(session, "events") == before_e    # 자동 병합 0


async def test_live_incremental_ambiguity_preserved_partial_preadjudicated(session):
    # ADR#49(adversarial MEDIUM 회귀 가드): incremental 모드에서도 ambiguity 정확. 한 candidate(E3)가 2 Event
    # (E1·E2)와 link(모호), 그 중 1개를 먼저 판정한 뒤 only_unadjudicated 로 나머지를 판정해도 **여전히 ambiguous**
    # — cand_targets(모호성 map)는 incremental 필터 **전** 전체 link 로 산출(순서 의존 안전 속성을 잠금).
    title = "연준 기준금리 인상 결정 발표"
    c1 = _IdCluster(cluster_id="xc:amb1", duplicate_group=("canon:amb1",))
    r1 = await pipe.resolve_and_apply_cluster(session, c1, candidate=_sem_cand(_T2, ("sem:A1",), title=title))
    c2 = _IdCluster(cluster_id="xc:amb2", duplicate_group=("canon:amb2",))
    r2 = await pipe.resolve_and_apply_cluster(session, c2, candidate=_sem_cand(_T2, ("sem:A2",), title=title))
    c3 = _IdCluster(cluster_id="xc:amb3", duplicate_group=("canon:amb3",))
    r3 = await pipe.resolve_and_apply_cluster(session, c3, candidate=_sem_cand(_T3, ("sem:A3",), title=title))
    await svc.hold_link(session, event_id=r3.event_id, linked_event_id=r1.event_id, reason=adjmod.SEMANTIC_LINK_REASON)
    await svc.hold_link(session, event_id=r3.event_id, linked_event_id=r2.event_id, reason=adjmod.SEMANTIC_LINK_REASON)
    assert await _count(session, "event_links") == 2
    # 1개만 먼저 판정(limit=1) — 이미 ambiguous.
    first = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True, limit=1)
    assert len(first) == 1 and first[0].status == "ambiguous"
    # 나머지를 incremental 로 판정 → **여전히 ambiguous**(전체 cand_targets 기준·필터가 모호성 오염 안 함).
    rest = await adjmod.adjudicate_semantic_links(session, only_unadjudicated=True)
    assert len(rest) == 1 and rest[0].status == "ambiguous"
    assert await _count(session, "event_identity_adjudication") == 2


# ── keyset cursor / concurrency / deploy checklist (ADR#50) ─────────────────────────
async def test_live_keyset_after_link_id_cursor_skips(session):
    # ADR#50(scenario 5): after_link_id keyset → cursor **초과** link 만 처리(페이지네이션). 모호성도 정확.
    await _make_two_semantic_links(session)
    ordered = await adjmod.adjudicate_semantic_links(session, persist=False)   # id asc·영속 0
    assert len(ordered) == 2
    r = await adjmod.adjudicate_semantic_links(session, after_link_id=ordered[0].link_id)
    assert len(r) == 1 and r[0].link_id == ordered[1].link_id    # 첫 link 는 cursor 로 skip
    assert await _count(session, "event_identity_adjudication") == 1


async def test_live_backfill_cursor_report_and_no_lock_overclaim(session):
    # ADR#50(scenario 12·13): report 통일(after_link_id·next_cursor·full_scan·idempotent_persist)·lock 과대주장 0.
    await _make_two_semantic_links(session)
    bounded = await bfmod.backfill_semantic_adjudications(session, limit=1, dry_run=True)
    assert bounded["full_scan"] is False                  # limit → bounded run
    assert bounded["after_link_id"] is None and bounded["idempotent_persist"] is True
    assert "lock" not in bounded and "locked" not in bounded   # lock 안전 과대주장 안 함(멱등만 주장)
    full = await bfmod.backfill_semantic_adjudications(session, dry_run=True)
    assert full["full_scan"] is True                      # limit/cursor 없음 → 전체 scan 경고 플래그
    assert full["processed"] == 2 and full["pending_after"] == full["pending_before"]  # dry-run
    assert full["next_cursor"] is not None                # 다음 페이지 진행 cursor


async def test_live_backfill_interleaved_sessions_duplicate_persist_safe(engine):
    # ADR#50(scenario 11·adversarial HIGH③ 정직화): 2 link·서로 다른 세션의 backfill 을 교차 실행 → link_id PK
    # upsert 로 **중복행 0**(데이터 안전)·자동 병합 0. **정직 경계**: asyncio.gather 는 협조적 교차(OS-병렬 race
    # 아님)라 이 테스트는 "중복-persist 멱등(PK upsert) + 양쪽 ORDER BY id asc 동일 잠금순서"를 입증할 뿐,
    # OS-병렬 race/deadlock 을 stress-test 하지 않는다(중복 work 회피=단일 runner/disjoint cursor 권고·미구현).
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s0:
        await _make_two_semantic_links(s0)               # 2 link(다중 row upsert 교차)
        before_e = await _count(s0, "events")

    async def _bf():
        async with maker() as s:
            return await bfmod.backfill_semantic_adjudications(s, dry_run=False)

    await asyncio.gather(_bf(), _bf())                    # 교차 — 같은 2 pending link
    async with maker() as s2:
        assert await _count(s2, "event_identity_adjudication") == 2   # 중복행 0(link 당 1·PK upsert)
        assert await _count(s2, "events") == before_e                 # 자동 병합 0


async def test_live_deploy_checklist_from_real_readiness(session):
    # ADR#50(scenario 14·15): 실 readiness probe(test DB=head) → deploy checklist(backup 필수·executed False·실명령).
    r = await rdymod.operational_db_readiness(session, db_name="event_intel_test")
    c = rdymod.build_operational_deploy_checklist(r)
    assert c["target_revision"] == "c9d0e1f2a3b4"
    assert c["backup_required"] is True and c["executed"] is False
    assert c["ready_for_stage3"] is True                  # test DB head
    names = {s["name"] for s in c["steps"]}
    assert {"backup", "upgrade", "post_upgrade_readiness", "backfill_dry_run",
            "backfill_limited_persist", "rollback_if_needed"} <= names


# ── created_at cursor / preflight gate (ADR#51) ──────────────────────────────────────
async def test_live_cursor_mode_created_at_orders_oldest_first(session):
    # ADR#51(scenario 17): cursor_mode='created_at' → 시간순(오래된 백로그 우선). created_at 을 id 역순으로
    # 설정해 created_at 순서 ≠ id 순서임을 입증(id=UUIDv4 byte 순서와 독립).
    await _make_two_semantic_links(session)
    by_id = await adjmod.adjudicate_semantic_links(session, persist=False, cursor_mode="id")
    assert len(by_id) == 2
    lo, hi = by_id[0].link_id, by_id[1].link_id            # id(byte) 오름차순: lo < hi
    # 큰 id(hi)=더 오래된 시각·작은 id(lo)=더 최근 → created_at 순서는 [hi, lo](id 와 반대).
    await session.execute(text("UPDATE event_links SET created_at = '2026-01-01T00:00:00+00:00' WHERE id::text = :i"), {"i": hi})
    await session.execute(text("UPDATE event_links SET created_at = '2026-06-01T00:00:00+00:00' WHERE id::text = :i"), {"i": lo})
    await session.commit()
    by_ca = await adjmod.adjudicate_semantic_links(session, persist=False, cursor_mode="created_at")
    assert [r.link_id for r in by_ca] == [hi, lo]          # 오래된(hi) 먼저 — id 순서와 반대
    assert by_ca[0].link_created_at < by_ca[1].link_created_at


async def test_live_cursor_mode_created_at_composite_resume(session):
    # ADR#51(scenario 14·17): (after_created_at, after_link_id) 복합 cursor → 시간순 다음 페이지(정확 resumable·중복 0).
    await _make_two_semantic_links(session)
    page1 = await adjmod.adjudicate_semantic_links(session, persist=False, cursor_mode="created_at", limit=1)
    assert len(page1) == 1
    page2 = await adjmod.adjudicate_semantic_links(
        session, persist=False, cursor_mode="created_at", limit=1,
        after_created_at=page1[0].link_created_at, after_link_id=page1[0].link_id)
    assert len(page2) == 1 and page2[0].link_id != page1[0].link_id   # 다음 페이지(중복 0)
    page3 = await adjmod.adjudicate_semantic_links(
        session, persist=False, cursor_mode="created_at", limit=1,
        after_created_at=page2[0].link_created_at, after_link_id=page2[0].link_id)
    assert page3 == []                                     # 2 link 소진


async def test_live_backfill_created_at_cursor_report(session):
    # ADR#51(scenario 12·17): created_at cursor_mode report — cursor_mode·next_created_at·full_scan.
    await _make_two_semantic_links(session)
    rep = await bfmod.backfill_semantic_adjudications(session, cursor_mode="created_at", limit=1, dry_run=True)
    assert rep["cursor_mode"] == "created_at" and rep["full_scan"] is False and rep["processed"] == 1
    assert rep["next_created_at"] is not None and rep["next_cursor"] is not None
    assert rep["pending_after"] == rep["pending_before"]   # dry-run(영속 0)


async def test_live_backfill_preflight_flag_off_blocks_persist(session, monkeypatch):
    # ADR#51(scenario 4): readiness OK(test DB head) + flag off + persist 요청 → block 'flag'·persist 0.
    await _make_semantic_link(session)
    monkeypatch.setattr(bfmod.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", False)
    out = await bfmod.run_backfill_with_preflight(session, dry_run=False)
    assert out["ran"] is False and out["block"] == "flag"
    assert out["preflight"]["ready_for_stage3"] is True    # 테이블은 준비(head)
    assert await _count(session, "event_identity_adjudication") == 0   # persist 안 됨


async def test_live_backfill_preflight_flag_on_persists(session, monkeypatch):
    # ADR#51(scenario 5): readiness OK + flag on + persist → ran·persist·Event 불변(자동 병합 0).
    await _make_semantic_link(session)
    monkeypatch.setattr(bfmod.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", True)
    before_e = await _count(session, "events")
    out = await bfmod.run_backfill_with_preflight(session, dry_run=False)
    assert out["ran"] is True and out["block"] is None and out["report"]["processed"] == 1
    assert await _count(session, "event_identity_adjudication") == 1
    assert await _count(session, "events") == before_e


async def test_live_backfill_preflight_dry_run_allowed_when_flag_off(session, monkeypatch):
    # ADR#51(scenario 2·10): dry-run 은 flag off 여도 허용(read-only)·persist 0.
    await _make_semantic_link(session)
    monkeypatch.setattr(bfmod.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", False)
    out = await bfmod.run_backfill_with_preflight(session, dry_run=True)
    assert out["ran"] is True and out["report"]["dry_run"] is True
    assert await _count(session, "event_identity_adjudication") == 0


async def test_live_backfill_preflight_allow_flag_off_persists(session, monkeypatch):
    # ADR#51(scenario 4): flag off 여도 allow_flag_off 명시 우회 → persist.
    await _make_semantic_link(session)
    monkeypatch.setattr(bfmod.settings, "EVENT_SEMANTIC_ADJUDICATION_ENABLED", False)
    out = await bfmod.run_backfill_with_preflight(session, dry_run=False, allow_flag_off=True)
    assert out["ran"] is True
    assert await _count(session, "event_identity_adjudication") == 1


async def test_live_cursor_mode_created_at_tie_break_resume(session):
    # ADR#51(adversarial MEDIUM): **동일 created_at** link 들에서 복합 cursor 의 tie-break 분기
    # and_(created_at==cur, id>after_link_id) 를 강제로 타며 resume 중복/skip 0 입증(별도 txn 이라 created_at 이
    # 다른 composite_resume 테스트가 못 타는 경로). 두 link 의 created_at 을 같게 설정.
    await _make_two_semantic_links(session)
    await session.execute(text(
        "UPDATE event_links SET created_at = '2026-03-01T00:00:00+00:00' "
        "WHERE status='possible' AND reason=:r"), {"r": adjmod.SEMANTIC_LINK_REASON})
    await session.commit()
    p1 = await adjmod.adjudicate_semantic_links(session, persist=False, cursor_mode="created_at", limit=1)
    assert len(p1) == 1
    p2 = await adjmod.adjudicate_semantic_links(
        session, persist=False, cursor_mode="created_at", limit=1,
        after_created_at=p1[0].link_created_at, after_link_id=p1[0].link_id)
    assert len(p2) == 1 and p2[0].link_id != p1[0].link_id   # 동일 created_at → id tie-break 진행(중복 0)
    assert p1[0].link_created_at == p2[0].link_created_at     # 같은 시각(tie-break 분기 입증)
    p3 = await adjmod.adjudicate_semantic_links(
        session, persist=False, cursor_mode="created_at", limit=1,
        after_created_at=p2[0].link_created_at, after_link_id=p2[0].link_id)
    assert p3 == []                                          # 소진(skip/중복 0)


async def test_live_preflight_blocks_when_adjudication_table_absent(engine):
    # ADR#51(adversarial MEDIUM): adjudication 테이블 부재(운영 DB 0003 형상)에서 preflight 가 쿼리 크래시 없이
    # block='readiness' 로 안전 차단하는지 **실 DB** 로 입증. DROP 은 트랜잭션 내(PG DDL transactional)·rollback 복원.
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("DROP TABLE event_identity_adjudication"))   # 같은 txn 내 information_schema 부재
        out = await bfmod.run_backfill_with_preflight(s, dry_run=True)    # dry-run 도 차단(hard gate·크래시 방지)
        assert out["ran"] is False and out["block"] == "readiness"
        assert out["preflight"]["ready_for_stage3"] is False
        await s.rollback()                                               # 테이블 복원(다음 테스트 보호)


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
