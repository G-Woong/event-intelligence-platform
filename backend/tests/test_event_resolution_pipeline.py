from __future__ import annotations

"""S2e 통합 E2E — 실 cross_source_dedup → event_resolver → apply_routing 영속 (ADR#19/#20).

검증 수단(정직 명시): **in-memory fake session**(실 Postgres 아님). fake 는 apply_routing 이
발행하는 statement(events/event_updates/event_links/cluster_event_map insert·events FSD update·
cluster_event_map/events/event_updates select)를 in-memory dict 로 해석해 **상태 전이**(CREATE→
cluster_event_map 매핑→2번째 보도 APPEND)를 실제로 재현한다. dedup·resolver·apply_routing 은
**실제 코드**가 돈다. 실 DB migration/FK/concurrency 의 런타임 동작은 범위 밖(live-PG E2E 이월) —
동시성 rollback 은 별도 mock 단위로 검증한다.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert, Update
from sqlalchemy.sql.selectable import Select

from ingestion.orchestration.cross_source_dedup import cluster_records

from backend.app.services import event_resolution_pipeline as pipe
from backend.app.services import event_timeline_service as svc
from backend.app.services.event_resolver import ACTION_APPEND, ACTION_CREATE, ACTION_HOLD
from backend.app.services.event_timeline_service import ResolvedCandidate


def _params(stmt):
    return stmt.compile(dialect=postgresql.dialect()).params


def _rec(**kw):
    base = {
        "record_type": "article_candidate", "source_id": "bbc",
        "title_or_label": None, "source_url_or_evidence": None, "canonical_url": None,
        "published_at_or_observed_at": None, "body_state_or_signal": "present",
    }
    base.update(kw)
    return base


# ── in-memory fake session ───────────────────────────────────────────────────────
class _Result:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._scalar

    def scalars(self):
        return list(self._rows)


class _FakeSession:
    """apply_routing 이 쓰는 statement 만 해석하는 최소 in-memory 세션(실 DB 아님)."""

    def __init__(self):
        self.events: dict[str, SimpleNamespace] = {}
        self.updates: list[SimpleNamespace] = []
        self.cmap: dict[str, uuid.UUID] = {}
        self.links: list[SimpleNamespace] = []
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, stmt):
        if isinstance(stmt, Insert):
            return self._insert(stmt)
        if isinstance(stmt, Update):
            return self._update(stmt)
        if isinstance(stmt, Select):
            return self._select(stmt)
        raise NotImplementedError(f"unexpected statement: {type(stmt).__name__}")

    def _insert(self, stmt):
        table = stmt.table.name
        p = _params(stmt)
        if table == "events":
            self.events[str(p["id"])] = SimpleNamespace(snapshot_card_id=None, **p)
        elif table == "event_updates":
            self.updates.append(SimpleNamespace(**p))
        elif table == "cluster_event_map":
            if p["cluster_id"] not in self.cmap:   # on_conflict_do_nothing
                self.cmap[p["cluster_id"]] = p["event_id"]
        elif table == "event_links":
            self.links.append(SimpleNamespace(**p))
        else:
            raise NotImplementedError(f"insert {table}")
        return _Result()

    def _update(self, stmt):
        if stmt.table.name != "events":
            raise NotImplementedError(f"update {stmt.table.name}")
        p = _params(stmt)
        eid = str(stmt.whereclause.right.value)
        observed = next(v for v in p.values() if isinstance(v, datetime))
        row = self.events.get(eid)
        if row is not None:  # event 부재면 0행(set_snapshot 의 존재성 검증과 동일)
            row.first_seen_at = min(row.first_seen_at, observed)
            row.last_update_at = max(row.last_update_at, observed)
        return _Result()

    def _select(self, stmt):
        entity = stmt.column_descriptions[0]["entity"]
        table = entity.__tablename__
        where_val = stmt.whereclause.right.value if stmt.whereclause is not None else None
        if table == "cluster_event_map":
            return _Result(scalar=self.cmap.get(where_val))
        if table == "events":
            return _Result(scalar=self.events.get(str(where_val)))
        if table == "event_updates":
            rows = sorted(
                (u for u in self.updates if str(u.event_id) == str(where_val)),
                key=lambda u: u.observed_at,
            )
            return _Result(rows=rows)
        if table == "event_cards":
            return _Result(scalar=None)
        raise NotImplementedError(f"select {table}")


_T2 = datetime(2026, 6, 18, 11, 0, tzinfo=timezone.utc)
_T1 = datetime(2026, 6, 18, 8, 0, tzinfo=timezone.utc)   # 더 이른 후속 보도(FSD)
_T3 = datetime(2026, 6, 18, 14, 0, tzinfo=timezone.utc)


def _cand(title="호르무즈 해협 긴장", observed=_T2, **kw):
    base = dict(canonical_title=title, observed_at=observed, delta_summary="update")
    base.update(kw)
    return ResolvedCandidate(**base)


def _strong_cluster():
    # 같은 canonical_url → 강신호 duplicate clique(ap+bbc).
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label="Hormuz tanker seized"),
        _rec(source_id="bbc", canonical_url="https://wire/x", title_or_label="Hormuz tanker seized"),
    ]
    clusters = cluster_records(recs)
    assert len(clusters) == 1 and clusters[0].confidence == "duplicate" and clusters[0].clique_ok
    return clusters[0]


# ── 실 dedup → resolver → apply_routing 통합 ──────────────────────────────────────
@pytest.mark.asyncio
async def test_first_cluster_creates_event_and_maps():
    s = _FakeSession()
    c = _strong_cluster()
    res = await pipe.resolve_and_apply_cluster(s, c, candidate=_cand())
    assert res.action == ACTION_CREATE
    assert len(s.events) == 1                       # 새 Event 1개
    assert s.cmap[c.cluster_id] is not None         # cluster_event_map 매핑됨
    assert len(s.updates) == 1                      # CREATE 는 genesis update 1행(생성 근거, ADR#31)
    assert s.updates[0].delta_summary == "update"   # candidate 의 delta_summary 가 genesis 로 영속
    assert s.commits == 1                           # 단일 원자 커밋


@pytest.mark.asyncio
async def test_second_report_appends_not_new_event():
    # 상용 핵심: 같은 사건의 2번째 보도가 **새 카드/Event 가 아니라 기존 Event 에 append**.
    s = _FakeSession()
    c = _strong_cluster()
    r1 = await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T2))
    r2 = await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T3, delta_summary="유가 +4%"))
    assert r1.action == ACTION_CREATE and r2.action == ACTION_APPEND
    assert r2.event_id == r1.event_id               # 같은 Event
    assert len(s.events) == 1                       # 새 Event 남발 0
    assert len(s.updates) == 2                       # genesis(CREATE) + append(2번째 보도)
    assert s.updates[0].delta_summary == "update"    # genesis(첫 보도, 생성 근거)
    assert s.updates[1].delta_summary == "유가 +4%"   # 2번째 보도 append


@pytest.mark.asyncio
async def test_rerun_same_cluster_idempotent():
    # 동일 cluster 재실행 → 중복 Event 생성 금지(append 누적, 멱등).
    s = _FakeSession()
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T3))
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T3))
    assert len(s.events) == 1            # Event 1개 유지
    assert len(s.cmap) == 1              # 매핑 1개
    assert len(s.updates) == 3           # genesis(CREATE) + 2·3번째 보도 append(Event/매핑은 멱등)


@pytest.mark.asyncio
async def test_transitive_weak_member_held_not_merged():
    # R-FalseMerge E2E: ap+reuters 강신호 + blog 약신호-only → blog 자동병합 금지(event_links possible).
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
        _rec(source_id="blog", canonical_url="https://blog/z",
             title_or_label="Hormuz tanker seized by navy", published_at_or_observed_at="2025-06-02"),
    ]
    c = cluster_records(recs)[0]
    assert c.confidence == "duplicate" and c.clique_ok is False and len(c.weak_only_members) == 1
    s = _FakeSession()
    res = await pipe.resolve_and_apply_cluster(s, c, candidate=_cand())
    assert res.action == ACTION_CREATE                  # 강신호 core 는 새 Event
    assert len(s.events) == 2                            # core Event + degenerate held(blog)
    assert len(s.links) == 1                             # blog 는 event_links(possible) 보류
    assert s.links[0].status == "possible"
    assert str(s.links[0].linked_event_id) == res.event_id   # held → primary(core)
    # blog 가 core 의 update 로 흡수되지 않음(자동병합 0) — core 의 update 는 genesis 1행뿐.
    assert len(s.updates) == 1                           # core 의 genesis(생성 근거)만; blog 미흡수


@pytest.mark.asyncio
async def test_two_strong_components_bridged_by_weak_both_held():
    # 두 강성분(ap-reuters / afp-dpa)이 약신호로만 브릿지 → 비-primary 성분 보류(clique 미달).
    title = "hormuz strait tanker seized by navy"
    recs = [
        _rec(source_id="ap", canonical_url="https://wire/x", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="reuters", canonical_url="https://wire/x", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="afp", canonical_url="https://other/y", title_or_label=title, published_at_or_observed_at="2025-06-02"),
        _rec(source_id="dpa", canonical_url="https://other/y", title_or_label=title, published_at_or_observed_at="2025-06-02"),
    ]
    c = cluster_records(recs)[0]
    assert len(c.weak_only_members) == 2
    s = _FakeSession()
    res = await pipe.resolve_and_apply_cluster(s, c, candidate=_cand())
    assert res.action == ACTION_CREATE
    assert len(s.links) == 2                             # 비-primary 강성분 2건 보류
    assert all(l.status == "possible" for l in s.links)


# ── FSD 단조성 ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_fsd_first_seen_pulled_earlier_only():
    s = _FakeSession()
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T2))   # CREATE @T2
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T1))   # APPEND @T1(이른 보도)
    out = await svc.get_event(s, list(s.events.keys())[0])
    ev, updates = out
    assert ev.first_seen_at == _T1     # 과거로 당겨짐
    assert ev.last_update_at == _T2    # last_update 는 더 이른 보도로 후퇴하지 않음
    assert len(updates) == 2           # genesis(@T2) + 이른 보도 append(@T1)


@pytest.mark.asyncio
async def test_last_update_monotonic_forward():
    s = _FakeSession()
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T3))   # 더 미래
    ev, _ = await svc.get_event(s, list(s.events.keys())[0])
    assert ev.last_update_at == _T3
    assert ev.first_seen_at == _T2     # first_seen 은 미래로 밀리지 않음


# ── evidence/source_refs sanitize 가 파이프라인 통과 후에도 유지 ───────────────────
@pytest.mark.asyncio
async def test_evidence_and_source_refs_sanitized_through_pipeline():
    s = _FakeSession()
    c = _strong_cluster()
    await pipe.resolve_and_apply_cluster(s, c, candidate=_cand(observed=_T2))
    await pipe.resolve_and_apply_cluster(
        s, c,
        candidate=_cand(
            observed=_T3,
            evidence=(
                {"url": "https://reuters/x", "relation": "supports", "body": "B" * 5000,
                 "author_email": "a@b.com", "nested": {"k": "v"}},
            ),
            source_refs=("raw-001", "C" * 5000),
        ),
    )
    stored = s.updates[-1]
    # 전문 본문·PII 키·중첩 dict 폐기, allowlist scalar 만.
    assert stored.evidence == [{"url": "https://reuters/x", "relation": "supports"}]
    # 과대 ref(본문 위장) 폐기, 짧은 식별자만.
    assert stored.source_refs == ["raw-001"]


# ── 동시성: 교차-tx CREATE 패배 rollback(별도 mock 단위 — live-PG 아님) ──────────────
@pytest.mark.asyncio
async def test_concurrent_create_loser_rolls_back_no_orphan():
    # apply_routing CREATE: get-first None → create_event(우리 event) → map_cluster 가 **다른**
    # event(동시 승자)를 반환 → 우리 orphan 폐기(rollback) + 승자로 append degrade. orphan 0.
    from backend.app.services.event_resolver import EventRoutingDecision

    decision = EventRoutingDecision("c-race", ACTION_CREATE, None, "new_event_strong_clique", ())
    session = AsyncMock()
    with patch.object(svc, "get_cluster_event", new=AsyncMock(return_value=None)), \
         patch.object(svc, "create_event", new=AsyncMock(return_value="evt-mine")) as m_create, \
         patch.object(svc, "map_cluster", new=AsyncMock(return_value="evt-winner")) as m_map, \
         patch.object(svc, "append_update", new=AsyncMock(return_value="upd-1")) as m_append:
        res = await svc.apply_routing(session, decision, candidate=_cand())
    m_create.assert_awaited_once()                 # 우리 event 생성 시도
    m_map.assert_awaited_once()                    # 매핑 시도 → 패배(evt-winner)
    session.rollback.assert_awaited_once()         # orphan 폐기
    m_append.assert_awaited_once_with(session, event_id="evt-winner", candidate=_cand(), commit=False)
    assert res.event_id == "evt-winner"            # 승자로 수렴(orphan 0)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_create_loss_with_held_members_links_to_winner():
    # adversarial A-1: CREATE 패배 + held_members 결합 경로(resolver new_event_strong_core_weak_hold).
    # rollback 후 held 는 **승자(mapped)** 에 링크돼야 한다(orphan held 0, 자기 패배 event 에 매달리지 않음).
    from backend.app.services.event_resolver import EventRoutingDecision

    decision = EventRoutingDecision(
        "c-race", ACTION_CREATE, None, "new_event_strong_core_weak_hold", ("blog",)
    )
    session = AsyncMock()
    with patch.object(svc, "get_cluster_event", new=AsyncMock(return_value=None)), \
         patch.object(svc, "create_event", new=AsyncMock(side_effect=["evt-mine", "held-blog"])) as m_create, \
         patch.object(svc, "map_cluster", new=AsyncMock(return_value="evt-winner")) as m_map, \
         patch.object(svc, "append_update", new=AsyncMock(return_value="upd-1")) as m_append, \
         patch.object(svc, "hold_link", new=AsyncMock(return_value="lnk-1")) as m_hold:
        res = await svc.apply_routing(session, decision, candidate=_cand())
    session.rollback.assert_awaited_once()              # 우리 orphan 폐기
    assert res.event_id == "evt-winner"                 # 승자로 수렴
    assert m_create.await_count == 2                    # evt-mine(폐기) + held-blog
    m_hold.assert_awaited_once()
    assert m_hold.call_args.kwargs["linked_event_id"] == "evt-winner"   # held → 승자
    assert res.held_event_ids == ["held-blog"]
    session.commit.assert_awaited_once()


# ── 배치 진입점 resolve_and_apply_clusters ────────────────────────────────────────
@pytest.mark.asyncio
async def test_batch_pipeline_routes_each_cluster():
    s = _FakeSession()
    c = _strong_cluster()
    results = await pipe.resolve_and_apply_clusters(s, [c], candidate_for=lambda _c: _cand())
    assert len(results) == 1 and results[0].action == ACTION_CREATE
    assert len(s.events) == 1
