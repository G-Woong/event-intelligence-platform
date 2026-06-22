from __future__ import annotations

"""S2c event_resolver 순수 라우팅 회귀 — APPEND / HOLD / CREATE + clique 게이트(DB 미접근)."""

from backend.app.services.event_resolver import (
    ACTION_APPEND,
    ACTION_CREATE,
    ACTION_HOLD,
    resolve_routing,
)


def test_mapped_strong_clique_appends():
    d = resolve_routing(
        cluster_id="c1", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id="evt-1",
    )
    assert d.action == ACTION_APPEND
    assert d.event_id == "evt-1"
    assert d.held_members == ()


def test_mapped_strong_non_clique_appends_core_holds_weak():
    # clique 미달: 강신호 core는 APPEND, 약신호-only 멤버는 분리 HOLD(R-FalseMerge).
    d = resolve_routing(
        cluster_id="c2", confidence="duplicate", clique_ok=False,
        member_keys=("a", "b", "c"), weak_only_members=("c",), mapped_event_id="evt-1",
    )
    assert d.action == ACTION_APPEND
    assert d.event_id == "evt-1"
    assert d.held_members == ("c",)


def test_mapped_weak_holds_as_possible_link():
    d = resolve_routing(
        cluster_id="c3", confidence="possible_duplicate", clique_ok=False,
        member_keys=("a", "b"), weak_only_members=("a", "b"), mapped_event_id="evt-1",
    )
    assert d.action == ACTION_HOLD
    assert d.event_id == "evt-1"
    assert set(d.held_members) == {"a", "b"}


def test_unmapped_strong_clique_creates():
    d = resolve_routing(
        cluster_id="c4", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
    )
    assert d.action == ACTION_CREATE
    assert d.event_id is None
    assert d.held_members == ()


def test_unmapped_strong_non_clique_creates_core_holds_weak():
    d = resolve_routing(
        cluster_id="c5", confidence="duplicate", clique_ok=False,
        member_keys=("a", "b", "c"), weak_only_members=("c",), mapped_event_id=None,
    )
    assert d.action == ACTION_CREATE
    assert d.held_members == ("c",)


def test_unmapped_weak_creates_low_confidence():
    d = resolve_routing(
        cluster_id="c6", confidence="possible_duplicate", clique_ok=False,
        member_keys=("a", "b"), weak_only_members=("a", "b"), mapped_event_id=None,
    )
    assert d.action == ACTION_CREATE
    assert d.reason == "new_event_low_confidence"


def test_confidence_value_contract_matches_dedup():
    # N3: resolver의 _CONF_DUPLICATE는 cross_source_dedup.CONF_DUPLICATE와 동일해야 한다
    # (import 없이 문자열 계약으로 결합 → 한쪽이 바뀌면 조용히 깨지는 drift 방지).
    from ingestion.orchestration.cross_source_dedup import CONF_DUPLICATE
    from backend.app.services.event_resolver import _CONF_DUPLICATE

    assert _CONF_DUPLICATE == CONF_DUPLICATE


def test_decision_is_deterministic():
    kwargs = dict(
        cluster_id="c7", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id="evt-9",
    )
    assert resolve_routing(**kwargs) == resolve_routing(**kwargs)
