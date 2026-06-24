from __future__ import annotations

"""Semantic identity adjudicator shadow/eval 단위 (ADR#42, R-SemanticIdentityAdjudicator).

순수 분류 로직(build_adjudication_features/classify/adjudicate/summarize)을 EventView 로 검증.
DB orchestration(adjudicate_semantic_links·persist·idempotent·Event count 불변)은 live-PG 에서.
**핵심 계약**: 어떤 status 도 Event 자동 병합을 의미하지 않는다(shadow). source role guard·fail-closed.
"""

from datetime import datetime, timezone

from backend.app.services.semantic_identity_adjudicator import (
    ADJ_AMBIGUOUS,
    ADJ_INSUFFICIENT,
    ADJ_LIKELY_DIFFERENT,
    ADJ_LIKELY_SAME,
    AdjudicationResult,
    EventView,
    adjudicate,
    build_adjudication_features,
    classify_identity_candidate,
    summarize_adjudication,
)

_D = datetime(2026, 6, 24, 10, tzinfo=timezone.utc)
_T = "Federal Reserve raises benchmark interest rates today"


def _ev(eid, title=_T, types=("article",), first=_D):
    return EventView(eid, title, first, types)


def _classify(cand, existing, multiple=False):
    f = build_adjudication_features(cand, existing, multiple_candidates=multiple)
    return classify_identity_candidate(f)


# ── 1. exact fingerprint(같은 token-set·근접 시점·publishable) → likely_same ──────────
def test_exact_fingerprint_likely_same_event():
    status, score, reason = _classify(_ev("a"), _ev("b", types=("official",)))
    assert status == ADJ_LIKELY_SAME and score > 0
    assert reason == "high_sim_near_date_publishable"


# ── 2. generic 제목(유의미 토큰 < 4) → insufficient ──────────────────────────────────
def test_generic_title_insufficient():
    status, _, reason = _classify(_ev("a", title="Market update news"), _ev("b", title="Market update news"))
    assert status == ADJ_INSUFFICIENT and reason == "generic_title"


# ── 3. 먼 날짜 → likely_different ──────────────────────────────────────────────────
def test_far_date_likely_different():
    far = datetime(2026, 7, 15, tzinfo=timezone.utc)
    status, _, reason = _classify(_ev("a"), _ev("b", first=far))
    assert status == ADJ_LIKELY_DIFFERENT and reason == "far_date_distance"


# ── 4·5. 비-publishable/불호환 source_type → non-merge(insufficient) ─────────────────
def test_community_only_insufficient_non_merge():
    status, _, reason = _classify(_ev("a", types=("community",)), _ev("b", types=("community",)))
    assert status == ADJ_INSUFFICIENT and reason == "non_publishable_role"


def test_market_only_insufficient_non_merge():
    status, _, reason = _classify(_ev("a", types=("signal",)), _ev("b", types=("article",)))
    assert status == ADJ_INSUFFICIENT and reason == "non_publishable_role"


# ── 6·7. catalog → non-merge ────────────────────────────────────────────────────
def test_catalog_only_insufficient_non_merge():
    status, _, reason = _classify(_ev("a", types=("catalog",)), _ev("b", types=("article",)))
    assert status == ADJ_INSUFFICIENT and reason == "non_publishable_role"


# ── 8. unknown source_type → fail-closed insufficient ───────────────────────────────
def test_unknown_source_type_fail_closed():
    status, _, reason = _classify(_ev("a", types=("weird_type",)), _ev("b", types=("article",)))
    assert status == ADJ_INSUFFICIENT and reason == "unknown_source_type_fail_closed"


def test_empty_source_type_fail_closed():
    status, _, reason = _classify(_ev("a", types=()), _ev("b", types=("article",)))
    assert status == ADJ_INSUFFICIENT and reason == "unknown_source_type_fail_closed"


# ── 9. 다중 후보(candidate 가 서로 다른 기존 Event 다수와 link) → ambiguous ────────────
def test_multiple_candidates_ambiguous():
    status, _, reason = _classify(_ev("a"), _ev("b"), multiple=True)
    assert status == ADJ_AMBIGUOUS and reason == "multiple_candidate_links"


# ── borderline(중간 유사도·중간 날짜) → ambiguous ──────────────────────────────────
def test_borderline_ambiguous():
    # 제목 일부만 겹침(Jaccard 0<x<0.8)·근접 시점 → borderline ambiguous(같은 사건 단정 금지).
    a = _ev("a", title="Federal Reserve raises benchmark interest rates today decision")
    b = _ev("b", title="Federal Reserve cuts something unrelated entirely separately maybe")
    status, _, reason = _classify(a, b)
    assert status == ADJ_AMBIGUOUS and reason == "borderline"


def test_no_title_overlap_insufficient():
    a = _ev("a", title="Apple unveils new flagship device today")
    b = _ev("b", title="Federal Reserve raises benchmark interest rates")
    status, _, reason = _classify(a, b)
    assert status == ADJ_INSUFFICIENT and reason == "no_title_signal"


# ── 한국어 경로 (adversarial 4: likely_same 한국어 동작 단위 검증) ────────────────────
_KT = "연준 기준금리 인상 결정 발표 오늘"   # 6 어절 토큰(≥4)


def test_korean_high_overlap_likely_same():
    # 같은 한국어 token-set·근접 시점·publishable → likely_same(한국어 likely_same 경로 잠금).
    status, score, reason = _classify(_ev("a", title=_KT), _ev("b", title=_KT, types=("official",)))
    assert status == ADJ_LIKELY_SAME and score > 0


def test_korean_partial_overlap_ambiguous():
    # 한국어 부분 겹침(Jaccard 0<x<0.8)·근접 시점 → borderline(같은 사건 단정 금지; 결정론 경계).
    b = "연준 기준금리 동결 결정 우려 시장"   # 일부만 겹침(연준·기준금리·결정)
    status, _, reason = _classify(_ev("a", title=_KT), _ev("b", title=b))
    assert status == ADJ_AMBIGUOUS and reason == "borderline"


def test_multiple_candidates_precedes_no_title_signal():
    # adversarial 3a: 다중 후보는 제목 겹침이 없어도(no_title_signal) **ambiguous 로 우선 보존**.
    a = _ev("a", title="Apple unveils new flagship device today")
    b = _ev("b", title="Federal Reserve raises benchmark interest rates")   # 토큰 겹침 0
    status, _, reason = classify_identity_candidate(
        build_adjudication_features(a, b, multiple_candidates=True)
    )
    assert status == ADJ_AMBIGUOUS and reason == "multiple_candidate_links"


# ── 10. likely_same report 생성 — 자동 병합/Event count 감소 없음(구조) ───────────────
def test_summarize_reports_no_auto_merge_and_language():
    results = [
        adjudicate(_ev("a"), _ev("b", types=("official",)), link_id="l1", multiple_candidates=False),
        adjudicate(_ev("c"), _ev("d"), link_id="l2", multiple_candidates=True),
        adjudicate(_ev("e", title=_KT), _ev("f", title=_KT), link_id="l3", multiple_candidates=False),
    ]
    summary = summarize_adjudication(results)
    assert summary["total"] == 3
    assert summary["by_status"][ADJ_LIKELY_SAME] == 2   # 영어1 + 한국어1
    assert summary["by_status"][ADJ_AMBIGUOUS] == 1
    assert summary["auto_merged"] == 0   # shadow — 자동 병합 0(중복 Event count 미감소)
    assert summary["by_language"]["latin"] == 2 and summary["by_language"]["ko"] == 1   # language_hint 소비


# ── 11. 결정론(같은 입력 → 같은 status/score) — idempotency 의 순수 기반 ───────────────
def test_classification_deterministic():
    r1 = adjudicate(_ev("a"), _ev("b", types=("official",)), link_id="l1", multiple_candidates=False)
    r2 = adjudicate(_ev("a"), _ev("b", types=("official",)), link_id="l1", multiple_candidates=False)
    assert (r1.status, r1.score, r1.reason) == (r2.status, r2.score, r2.reason)


def test_semantic_score_hook_present_but_optional():
    # future embedding/LLM hook(semantic_score) slot 은 기본 None(현재 deterministic only — provider 미배선).
    f = build_adjudication_features(_ev("a"), _ev("b"), multiple_candidates=False)
    assert f.semantic_score is None


# ── adjudicator 는 Event 변경 API 를 import 하지 않는다(구조적 no-merge 보장) ─────────────
def test_adjudicator_does_not_import_event_mutation():
    import backend.app.services.semantic_identity_adjudicator as mod
    src = open(mod.__file__, encoding="utf-8").read()
    # create_event/append_update/map_cluster/hold_link 등 Event 변경 호출을 쓰지 않음(read + adjudication write only).
    for forbidden in ("create_event", "append_update(", "map_cluster(", "apply_routing"):
        assert forbidden not in src, f"adjudicator must not mutate events: {forbidden}"
