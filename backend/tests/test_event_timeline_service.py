from __future__ import annotations

"""S2d event_timeline_service CRUD 영속층 회귀 (ADR#19 / SPEC §21.1).

DB 미연결(기존 backend 테스트 관례): AsyncMock 세션으로 영속 동작의 **구조**(어떤 테이블에
INSERT/UPDATE 가 가는가, append-only 인가, 쌍방향 정합 강제·방어 헬퍼)를 검증한다 — 실 Postgres
가 이 SQL 을 수용하는지는 범위 밖(measurement gate=mock 기반).
"""

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Delete, Insert, Update

from backend.app.schemas.events import Event, EventUpdate
from backend.app.services import event_timeline_service as svc
from backend.app.services.event_timeline_service import (
    ApplyResult,
    ResolvedCandidate,
    _coerce_uuid,
    _coerce_uuid_or_none,
    _ensure_aware,
    _sanitize_evidence,
    _sanitize_source_refs,
)
from backend.app.services.event_resolver import (
    ACTION_APPEND,
    ACTION_CREATE,
    ACTION_HOLD,
    EventRoutingDecision,
)


def _params(stmt):
    """postgresql dialect 로 컴파일해 bound params(컬럼→값) 추출."""
    return stmt.compile(dialect=postgresql.dialect()).params


def _cand(**kw) -> ResolvedCandidate:
    base = dict(
        canonical_title="호르무즈 해협 긴장 고조",
        observed_at=datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc),
    )
    base.update(kw)
    return ResolvedCandidate(**base)


def _stmt_targets(session: AsyncMock) -> list[tuple[str, str]]:
    """session.execute 에 넘어간 DML 들의 (종류, 테이블명) 목록."""
    targets: list[tuple[str, str]] = []
    for call in session.execute.call_args_list:
        stmt = call.args[0]
        if isinstance(stmt, Insert):
            targets.append(("insert", stmt.table.name))
        elif isinstance(stmt, Update):
            targets.append(("update", stmt.table.name))
        elif isinstance(stmt, Delete):
            targets.append(("delete", stmt.table.name))
        else:
            targets.append(("other", type(stmt).__name__))
    return targets


# ── 방어 헬퍼(tz / UUID / 전문·PII) ─────────────────────────────────────────────
def test_coerce_uuid_accepts_str_and_uuid():
    u = uuid.uuid4()
    assert _coerce_uuid(u) == u
    assert _coerce_uuid(str(u)) == u


def test_coerce_uuid_rejects_garbage():
    with pytest.raises(ValueError):
        _coerce_uuid("not-a-uuid")
    assert _coerce_uuid_or_none("not-a-uuid") is None
    assert _coerce_uuid_or_none(None) is None


def test_ensure_aware_attaches_utc_to_naive():
    naive = datetime(2026, 6, 18, 8, 0)
    aware = _ensure_aware(naive)
    assert aware.tzinfo is not None
    assert aware.utcoffset().total_seconds() == 0
    # 이미 aware 면 그대로.
    already = datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc)
    assert _ensure_aware(already) == already


def test_sanitize_evidence_drops_full_body_and_pii_keys():
    items = [
        {
            "url": "https://reuters.com/x",
            "source_type": "news",
            "relation": "supports",
            "confidence": 0.85,
            "body": "B" * 5000,          # 전문 본문 → 폐기(allowlist 밖)
            "author_email": "a@b.com",   # 임의 PII 키 → 폐기
            "raw_text": "...long...",     # 전문 → 폐기
        }
    ]
    out = _sanitize_evidence(items)
    assert out == [
        {
            "url": "https://reuters.com/x",
            "source_type": "news",
            "relation": "supports",
            "confidence": 0.85,
        }
    ]
    assert "body" not in out[0] and "author_email" not in out[0] and "raw_text" not in out[0]


def test_sanitize_evidence_rejects_oversized_url_value():
    # allowlist 키여도 본문 길이 문자열 값은 거부(전문 미저장).
    out = _sanitize_evidence([{"url": "x" * 5000}])
    assert out == []
    # legacy str degrade: 정상 길이 url 은 {"url": ...} 로.
    assert _sanitize_evidence(["https://bbc.com/x"]) == [{"url": "https://bbc.com/x"}]
    assert _sanitize_evidence(["y" * 5000]) == []


def test_sanitize_evidence_drops_nonscalar_allowlist_values():
    # A-6 교정: allowlist 키여도 값이 非scalar(중첩 dict/list)면 폐기 — 본문/PII 은닉 차단.
    out = _sanitize_evidence([{
        "url": "https://x.com/a",
        "confidence": 0.9,
        "role": {"nested": "B" * 5000, "pii": "a@b.com"},  # dict 값 → 폐기
        "relation": ["supports", "context"],               # list 값 → 폐기
    }])
    assert out == [{"url": "https://x.com/a", "confidence": 0.9}]


def test_sanitize_source_refs_keeps_short_ids_only():
    assert _sanitize_source_refs(["raw-001", "raw-002"]) == ["raw-001", "raw-002"]
    # 본문 길이는 ref 가 아니다 → 폐기.
    assert _sanitize_source_refs(["z" * 5000]) == []


# ── create_event ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_create_event_inserts_events_row():
    session = AsyncMock()
    eid = await svc.create_event(session, candidate=_cand())
    assert uuid.UUID(eid)  # 유효 UUID 반환
    assert _stmt_targets(session) == [("insert", "events")]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_event_defends_naive_datetime():
    session = AsyncMock()
    # tz-naive observed_at 이 들어와도 죽지 않는다(UTC 부착).
    await svc.create_event(session, candidate=_cand(observed_at=datetime(2026, 6, 18, 8, 0)))
    stmt = session.execute.call_args_list[0].args[0]
    params = _params(stmt)
    assert params["first_seen_at"].tzinfo is not None


# ── append_update (append-only) ─────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_append_update_is_append_only():
    session = AsyncMock()
    await svc.append_update(session, event_id=str(uuid.uuid4()), candidate=_cand(delta_summary="유가 +4% 반응"))
    targets = _stmt_targets(session)
    # event_updates 에는 INSERT 만, events 에는 메타 UPDATE — event_updates 를 UPDATE/DELETE 하지 않는다.
    assert ("insert", "event_updates") in targets
    assert ("update", "events") in targets
    assert ("update", "event_updates") not in targets
    assert ("delete", "event_updates") not in targets
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_update_does_not_overwrite_existing_updates():
    # 두 번 append → event_updates INSERT 가 두 번(덮어쓰기 0). 각 호출은 새 id.
    session = AsyncMock()
    eid = str(uuid.uuid4())
    id1 = await svc.append_update(session, event_id=eid, candidate=_cand(delta_summary="1"))
    id2 = await svc.append_update(session, event_id=eid, candidate=_cand(delta_summary="2"))
    assert id1 != id2
    inserts = [t for t in _stmt_targets(session) if t == ("insert", "event_updates")]
    assert len(inserts) == 2


@pytest.mark.asyncio
async def test_append_update_sanitizes_evidence_and_source_refs():
    session = AsyncMock()
    await svc.append_update(
        session,
        event_id=str(uuid.uuid4()),
        candidate=_cand(
            evidence=({"url": "https://r.com/x", "relation": "supports", "body": "B" * 5000},),
            source_refs=("raw-001", "C" * 5000),
        ),
    )
    ins = next(c.args[0] for c in session.execute.call_args_list if isinstance(c.args[0], Insert))
    params = _params(ins)
    assert params["evidence"] == [{"url": "https://r.com/x", "relation": "supports"}]
    assert params["source_refs"] == ["raw-001"]


@pytest.mark.asyncio
async def test_append_update_accepts_uuid_and_str_event_id():
    session = AsyncMock()
    u = uuid.uuid4()
    await svc.append_update(session, event_id=u, candidate=_cand())        # UUID
    await svc.append_update(session, event_id=str(u), candidate=_cand())   # str
    # 둘 다 같은 event_id 로 정규화(경계 방어).
    inserts = [c.args[0] for c in session.execute.call_args_list if isinstance(c.args[0], Insert)]
    assert _params(inserts[0])["event_id"] == _params(inserts[1])["event_id"] == u


# ── get_event ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_event_returns_event_and_updates():
    eid = uuid.uuid4()
    event_row = SimpleNamespace(
        id=eid, canonical_title="t", status="active",
        first_seen_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        last_update_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        heat=0.0, domains=["energy"], tags=[], primary_entity_ids=[], snapshot_card_id=None,
    )
    upd_row = SimpleNamespace(
        id=uuid.uuid4(), event_id=eid, observed_at=datetime(2026, 6, 18, tzinfo=timezone.utc),
        delta_summary="d", evidence=[], added_domains=[], source_refs=[], heat_delta=0.1,
    )
    res_event = SimpleNamespace(scalar_one_or_none=lambda: event_row)
    res_updates = SimpleNamespace(scalars=lambda: [upd_row])
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[res_event, res_updates])

    out = await svc.get_event(session, str(eid))
    assert out is not None
    ev, updates = out
    assert isinstance(ev, Event) and ev.id == str(eid) and ev.domains == ["energy"]
    assert len(updates) == 1 and isinstance(updates[0], EventUpdate)


@pytest.mark.asyncio
async def test_get_event_missing_returns_none():
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: None))
    assert await svc.get_event(session, str(uuid.uuid4())) is None
    # 잘못된 id 도 graceful None(쿼리조차 안 함).
    assert await svc.get_event(session, "not-a-uuid") is None


# ── set_snapshot (is_snapshot_bidirectional 강제) ────────────────────────────────
@pytest.mark.asyncio
async def test_set_snapshot_sets_both_sides_bidirectional():
    eid, cid = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock()
    # 실행 순서: ① pre card.event_id(None=미연결) ② update card ③ update event
    #           ④ 재조회 card.event_id(=eid) ⑤ 재조회 event.snapshot_card_id(=cid).
    session.execute = AsyncMock(side_effect=[
        SimpleNamespace(scalar_one_or_none=lambda: None),  # ① pre card.event_id
        None,                                              # ② update event_cards
        None,                                              # ③ update events
        SimpleNamespace(scalar_one_or_none=lambda: eid),   # ④ actual card.event_id
        SimpleNamespace(scalar_one_or_none=lambda: cid),   # ⑤ actual event.snapshot_card_id
    ])
    await svc.set_snapshot(session, event_id=str(eid), card_id=str(cid))
    targets = _stmt_targets(session)
    assert ("update", "event_cards") in targets  # card.event_id ← eid
    assert ("update", "events") in targets        # event.snapshot_card_id ← cid
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_set_snapshot_rejects_card_owned_by_other_event():
    # is_snapshot_bidirectional 실패 케이스 차단: 카드가 다른 event 에 묶여 있으면 거부.
    eid, cid, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: other))
    with pytest.raises(ValueError, match="different event"):
        await svc.set_snapshot(session, event_id=str(eid), card_id=str(cid))
    session.commit.assert_not_awaited()  # 거부 시 영속 안 함.


@pytest.mark.asyncio
async def test_set_snapshot_raises_when_event_missing_real_invariant():
    # A-1 교정 입증: 단언이 trivially-true 가 아니라 **실제 영속값**을 검증한다.
    # event 가 없어 UPDATE 0행 → 재조회 snapshot_card_id=None → 양방향 불성립 → raise(commit 안 함).
    eid, cid = uuid.uuid4(), uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[
        SimpleNamespace(scalar_one_or_none=lambda: None),  # ① pre card.event_id
        None,                                              # ② update event_cards
        None,                                              # ③ update events(0행)
        SimpleNamespace(scalar_one_or_none=lambda: None),  # ④ actual card.event_id=None
        SimpleNamespace(scalar_one_or_none=lambda: None),  # ⑤ actual event.snapshot_card_id=None
    ])
    with pytest.raises(ValueError, match="not bidirectional"):
        await svc.set_snapshot(session, event_id=str(eid), card_id=str(cid))
    session.commit.assert_not_awaited()


# ── cluster_event_map 조회/기록 ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_map_cluster_writes_and_preserves_single_source():
    eid = uuid.uuid4()
    session = AsyncMock()
    # insert(on_conflict_do_nothing) → 이후 get_cluster_event 가 영속값 반환.
    session.execute = AsyncMock(side_effect=[
        None,  # insert cluster_event_map
        SimpleNamespace(scalar_one_or_none=lambda: eid),  # get_cluster_event select
    ])
    out = await svc.map_cluster(session, cluster_id="xcluster:k1", event_id=str(eid))
    assert out == str(eid)
    assert ("insert", "cluster_event_map") in _stmt_targets(session)


@pytest.mark.asyncio
async def test_get_cluster_event_reads_mapping():
    eid = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=SimpleNamespace(scalar_one_or_none=lambda: eid))
    assert await svc.get_cluster_event(session, "xcluster:k1") == str(eid)


# ── hold_link (event_links possible) ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_hold_link_inserts_possible_event_link():
    session = AsyncMock()
    lid = await svc.hold_link(
        session, event_id=str(uuid.uuid4()), linked_event_id=str(uuid.uuid4()), reason="weak"
    )
    assert uuid.UUID(lid)
    ins = next(c.args[0] for c in session.execute.call_args_list if isinstance(c.args[0], Insert))
    assert ins.table.name == "event_links"
    assert _params(ins)["status"] == "possible"


# ── apply_routing: resolver 결정 → 영속 ──────────────────────────────────────────
@pytest.mark.asyncio
async def test_apply_routing_create_makes_event_and_maps_cluster():
    decision = EventRoutingDecision("c1", ACTION_CREATE, None, "new_event_strong_clique", ())
    with patch.object(svc, "get_cluster_event", new=AsyncMock(return_value=None)) as m_get, \
         patch.object(svc, "create_event", new=AsyncMock(return_value="evt-new")) as m_create, \
         patch.object(svc, "map_cluster", new=AsyncMock(return_value="evt-new")) as m_map, \
         patch.object(svc, "append_update", new=AsyncMock()) as m_append, \
         patch.object(svc, "hold_link", new=AsyncMock()) as m_hold:
        session = AsyncMock()
        res = await svc.apply_routing(session, decision, candidate=_cand())
    assert isinstance(res, ApplyResult) and res.action == ACTION_CREATE and res.event_id == "evt-new"
    m_get.assert_awaited_once()  # CREATE 는 먼저 매핑 조회(orphan 가드).
    m_create.assert_awaited_once_with(session, candidate=_cand_eq(), commit=False)
    m_map.assert_awaited_once_with(session, cluster_id="c1", event_id="evt-new", commit=False)
    m_append.assert_not_awaited()
    m_hold.assert_not_awaited()
    session.commit.assert_awaited_once()  # 단일 원자 커밋.


@pytest.mark.asyncio
async def test_apply_routing_create_degrades_to_append_when_already_mapped():
    # A-4 orphan 가드: cluster 가 이미 매핑됐으면(재실행) 새 event 생성 안 하고 기존으로 append.
    decision = EventRoutingDecision("c1", ACTION_CREATE, None, "new_event_strong_clique", ())
    with patch.object(svc, "get_cluster_event", new=AsyncMock(return_value="evt-existing")), \
         patch.object(svc, "create_event", new=AsyncMock()) as m_create, \
         patch.object(svc, "map_cluster", new=AsyncMock()) as m_map, \
         patch.object(svc, "append_update", new=AsyncMock(return_value="upd-1")) as m_append:
        session = AsyncMock()
        res = await svc.apply_routing(session, decision, candidate=_cand())
    assert res.event_id == "evt-existing"
    m_create.assert_not_awaited()   # orphan event 생성 회피.
    m_map.assert_not_awaited()
    m_append.assert_awaited_once_with(session, event_id="evt-existing", candidate=_cand_eq(), commit=False)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_routing_append_appends_update_not_new_event():
    decision = EventRoutingDecision("c2", ACTION_APPEND, "evt-1", "strong_clique_append", ())
    with patch.object(svc, "get_cluster_event", new=AsyncMock()) as m_get, \
         patch.object(svc, "create_event", new=AsyncMock()) as m_create, \
         patch.object(svc, "append_update", new=AsyncMock(return_value="upd-1")) as m_append, \
         patch.object(svc, "hold_link", new=AsyncMock()) as m_hold:
        session = AsyncMock()
        res = await svc.apply_routing(session, decision, candidate=_cand())
    assert res.action == ACTION_APPEND and res.event_id == "evt-1"
    m_append.assert_awaited_once_with(session, event_id="evt-1", candidate=_cand_eq(), commit=False)
    m_create.assert_not_awaited()  # 새 카드/이벤트 생성 안 함(append!).
    m_get.assert_not_awaited()     # APPEND 는 매핑 조회 불필요.
    m_hold.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_routing_hold_does_not_merge_but_records_links():
    # HOLD: append 0(오병합 금지) + held_members 는 degenerate held event + event_links(possible).
    decision = EventRoutingDecision(
        "c3", ACTION_HOLD, "evt-1", "weak_signal_possible_link", ("a", "b")
    )
    with patch.object(svc, "create_event", new=AsyncMock(side_effect=["held-a", "held-b"])) as m_create, \
         patch.object(svc, "append_update", new=AsyncMock()) as m_append, \
         patch.object(svc, "hold_link", new=AsyncMock(side_effect=["lnk-a", "lnk-b"])) as m_hold:
        session = AsyncMock()
        res = await svc.apply_routing(session, decision, candidate=_cand())
    m_append.assert_not_awaited()  # 자동병합 금지.
    assert m_create.await_count == 2  # held member 2개 materialize.
    assert m_hold.await_count == 2
    assert res.held_event_ids == ["held-a", "held-b"]
    assert res.link_ids == ["lnk-a", "lnk-b"]
    # 보류 링크는 held event → primary(evt-1) 방향, possible.
    for call in m_hold.call_args_list:
        assert call.kwargs["linked_event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_apply_routing_append_with_weak_hold_appends_core_and_holds_weak():
    # 강신호 core APPEND + 약신호 멤버 HOLD(R-FalseMerge: transitive 흡수 차단).
    decision = EventRoutingDecision(
        "c4", ACTION_APPEND, "evt-1", "strong_core_append_weak_hold", ("c",)
    )
    with patch.object(svc, "create_event", new=AsyncMock(return_value="held-c")) as m_create, \
         patch.object(svc, "append_update", new=AsyncMock()) as m_append, \
         patch.object(svc, "hold_link", new=AsyncMock(return_value="lnk-c")) as m_hold:
        session = AsyncMock()
        res = await svc.apply_routing(session, decision, candidate=_cand())
    m_append.assert_awaited_once()           # core 는 append.
    assert m_create.await_count == 1         # 약신호 c 만 held.
    assert m_hold.await_count == 1
    assert res.held_event_ids == ["held-c"]


def _cand_eq():
    """apply_routing 이 candidate 를 그대로 전달하는지 비교용(frozen dataclass 동치)."""
    return _cand()


# ── alembic revision chain 무결성 (0001→0005, 텍스트 — 실DB 미연결 대체검증) ──────
# import 하지 않는다: pytest sys.path 에서 backend/alembic 가 설치 alembic 을 가려
# `from alembic import op` 가 깨진다. revision/down_revision 만 텍스트로 읽어 체인을 잇는다.
def test_migration_revision_chain_is_contiguous_0001_to_0005():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    files = sorted(p for p in versions.glob("000*.py") if p.name != "__init__.py")
    assert [p.name for p in files] == [
        "0001_initial.py",
        "0002_raw_events.py",
        "0003_raw_events_event_card_link.py",
        "0004_event_timeline.py",
        "0005_event_resolution.py",
    ]

    rev_re = re.compile(r'^revision:\s*str\s*=\s*"([^"]+)"', re.M)
    down_re = re.compile(r'^down_revision:\s*[^=]*=\s*(None|"([^"]+)")', re.M)
    revs, downs = [], []
    for p in files:
        text = p.read_text(encoding="utf-8")
        revs.append(rev_re.search(text).group(1))
        m = down_re.search(text)
        downs.append(None if m.group(1) == "None" else m.group(2))

    # 첫 migration 은 base(None), 이후 각 down_revision 은 직전 revision 을 가리킨다(선형 체인, 분기 0).
    assert downs[0] is None
    for i in range(1, len(files)):
        assert downs[i] == revs[i - 1], f"{files[i].name} down_revision 이 체인 단절"
    assert len(set(revs)) == len(revs)  # revision 중복 없음.
