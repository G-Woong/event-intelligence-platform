from __future__ import annotations

"""S2c event_resolver 순수 라우팅 회귀 — APPEND / HOLD / CREATE + clique 게이트(DB 미접근)."""

from backend.app.services.event_resolver import (
    ACTION_APPEND,
    ACTION_CREATE,
    ACTION_HOLD,
    ACTION_WITHHELD,
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


# ── source-type publish gate (ADR#33, R-SourceTypeFidelityGate) ────────────────────
def test_gate_pure_community_strong_withheld():
    # pure-community 강신호 단독 cross-source → 직접 발행 금지(never_direct_publish).
    d = resolve_routing(
        cluster_id="g1", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("community", "community"),
    )
    assert d.action == ACTION_WITHHELD
    assert d.event_id is None
    assert d.reason == "non_publishable_source_type"


def test_gate_pure_community_weak_withheld():
    d = resolve_routing(
        cluster_id="g2", confidence="possible_duplicate", clique_ok=False,
        member_keys=("a", "b"), weak_only_members=("b",), mapped_event_id=None,
        member_source_types=("community", "community"),
    )
    assert d.action == ACTION_WITHHELD


def test_gate_pure_structured_signal_withheld():
    # 시장/구조화 신호 단독 cross-source → 발행 금지(signal_only_not_article_card, 투자조언 경계).
    d = resolve_routing(
        cluster_id="g3", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("signal", "signal"),
    )
    assert d.action == ACTION_WITHHELD


def test_gate_pure_search_withheld():
    d = resolve_routing(
        cluster_id="g4", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("search", "search"),
    )
    assert d.action == ACTION_WITHHELD


def test_gate_unknown_source_type_fail_closed():
    # 미지 source_type(publishable allowlist 밖)은 fail-closed → 발행 금지.
    d = resolve_routing(
        cluster_id="g5", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("rss", "rss"),
    )
    assert d.action == ACTION_WITHHELD


def test_gate_official_publishes():
    d = resolve_routing(
        cluster_id="g6", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("official", "official"),
    )
    assert d.action == ACTION_CREATE


def test_gate_official_plus_news_publishes():
    d = resolve_routing(
        cluster_id="g7", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
        member_source_types=("official", "article"),
    )
    assert d.action == ACTION_CREATE


def test_gate_news_plus_community_publishes_community_held():
    # community 가 섞여도 article(news) 가 있으면 발행(community 는 corroborator/weak HOLD).
    d = resolve_routing(
        cluster_id="g8", confidence="possible_duplicate", clique_ok=False,
        member_keys=("a", "b"), weak_only_members=("b",), mapped_event_id=None,
        member_source_types=("article", "community"),
    )
    assert d.action == ACTION_CREATE
    assert d.held_members == ("b",)


def test_gate_inactive_when_source_types_empty():
    # 레거시 호출(member_source_types 미제공) → 게이트 비활성(하위호환).
    d = resolve_routing(
        cluster_id="g9", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id=None,
    )
    assert d.action == ACTION_CREATE


def test_gate_not_applied_to_mapped_append():
    # 매핑된 event 의 APPEND 는 게이트 미적용 — community 가 기존 발행 event 에 corroborator 로 append.
    d = resolve_routing(
        cluster_id="g10", confidence="duplicate", clique_ok=True,
        member_keys=("a", "b"), mapped_event_id="evt-1",
        member_source_types=("community", "community"),
    )
    assert d.action == ACTION_APPEND
    assert d.event_id == "evt-1"


def test_publishable_source_type_contract_matches_record_type_mapping():
    # drift 방어(adversarial P2-2): _RECORD_TYPE_TO_SOURCE_TYPE 의 매핑이 _PUBLISHABLE_SOURCE_TYPES 와
    # 정합해야 한다(문자열 계약 결합 — 한쪽만 바뀌면 조용히 과잉/과소 차단). news(article)·official 은
    # 발행 가능, structured/community/search 는 불가. 새 record_type 추가 시 이 단언이 결정을 강제.
    from backend.app.services.event_ingest_pipeline import _RECORD_TYPE_TO_SOURCE_TYPE
    from backend.app.services.event_resolver import _PUBLISHABLE_SOURCE_TYPES

    assert _RECORD_TYPE_TO_SOURCE_TYPE["article_candidate"] in _PUBLISHABLE_SOURCE_TYPES
    assert _RECORD_TYPE_TO_SOURCE_TYPE["official_record"] in _PUBLISHABLE_SOURCE_TYPES
    for rt in ("structured_signal", "community_signal", "search_result"):
        assert _RECORD_TYPE_TO_SOURCE_TYPE[rt] not in _PUBLISHABLE_SOURCE_TYPES
