"""ADR#85 — window-honoring source readiness tests (offline·network 0·secret 0).

date-fidelity 후보 평가·권고 adapter·source role guard 보존·이 턴 미배선을 잠근다.
"""
from __future__ import annotations

from backend.app.tools.window_honoring_source_readiness import (
    build_window_honoring_source_readiness,
)


def test_readiness_ready_and_recommends_federal_register():
    out = build_window_honoring_source_readiness()
    assert out["window_honoring_source_readiness_ready"] is True
    assert out["candidate_count"] == 3
    assert out["recommended_adapter"] == "federal_register"
    assert out["next_adapter_for_adr86"] == "federal_register"


def test_federal_register_is_cleanest_window_honoring_candidate():
    out = build_window_honoring_source_readiness()
    fr = next(r for r in out["candidates"] if r["source_id"] == "federal_register")
    assert fr["source_role"] == "official"
    # 미검증 source 에 'high' 단정 금지(adversarial MEDIUM-3) — 문서 근거나 실 호출 미검증.
    assert fr["date_filter_confidence"] == "documented_unverified"
    assert fr["key_free"] is True
    assert fr["recommended_for_adr86_adapter"] is True
    # official×news 는 role-bridge 정책이 필요 — 자동 pairing 금지(ADR#86).
    assert fr["cross_source_pairing_with_news"] == "role_bridge_required"


def test_gdelt_flagged_rate_fragile_and_aggregator_attribution():
    out = build_window_honoring_source_readiness()
    g = next(r for r in out["candidates"] if r["source_id"] == "gdelt")
    assert g["rate_limit_risk"] == "high"
    assert g["canonical_attribution_risk"] == "high"
    assert g["recommended_for_adr86_adapter"] is False
    assert g["cross_source_pairing_with_news"] == "aggregator_contamination_risk"


def test_source_role_guard_preserved_only_publishable_roles():
    out = build_window_honoring_source_readiness()
    assert out["source_role_guard_preserved"] is True
    # 어떤 후보도 community/market/catalog/search anchor 로 승격되지 않는다.
    assert all(r["source_role"] in ("official", "news") for r in out["candidates"])
    assert all(r["anchor_eligible"] for r in out["candidates"])


def test_federal_register_adapter_now_wired_adr86():
    out = build_window_honoring_source_readiness()
    assert out["adapter_wired_this_turn"] is True   # ADR#86: FR adapter 실배선(ADR#85 spec-only → wired).
    fr = next(r for r in out["candidates"] if r["source_id"] == "federal_register")
    assert fr["adapter_status"] == "wired"
    # wired ≠ live date-honoring 검증 — confidence 는 여전히 documented_unverified(live smoke 가 별도 verify).
    assert fr["date_filter_confidence"] == "documented_unverified"


def test_boundaries_support_not_truth():
    out = build_window_honoring_source_readiness()
    assert out["readiness_is_acquisition_support_not_truth"] is True
    assert out["search_url_candidate_as_truth"] is False
    assert out["merge_allowed"] is False
    assert out["llm_invoked"] is False
    assert out["db_write"] is False
    assert out["secret_values_exposed"] is False


def test_wired_context_marks_guardian_nyt_under_experiment():
    out = build_window_honoring_source_readiness()
    ctx = {c["source_id"]: c for c in out["wired_context"]}
    assert ctx["guardian"]["date_filter_confidence"] == "under_control_experiment"
    assert ctx["nyt"]["date_filter_confidence"] == "under_control_experiment"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
