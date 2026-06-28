"""ADR#81 — provider breadth + named seed + KO path orchestrator 테스트
(§13: live off/on·breadth·named seed·KO·frontier·no merge/LLM/DB·PII·source role guard).

base_result 주입으로 결정론(discrete base 재실행 0) + 실 통합 1건(live_query=False·network 0)."""
from __future__ import annotations

import json

from backend.app.schemas.internal_ops import InternalOpsProviderBreadthFrontier
from backend.app.tools.r1_provider_breadth_acquisition import (
    LIVE_BLOCKED_NO_OPT_IN,
    run_provider_breadth_named_seed_ko_path,
)


def _base(**over):
    """최소 dry discrete base_result(orchestrator 가 읽는 필드만)."""
    base = {
        "actual_input_rechecked": True, "actual_contact_evidence_found": False,
        "actual_returned_labels_found": False, "actual_input_status": "no_actual_input",
        "targeted_live_query_executed": False, "live_call_count": 0, "providers_used": [],
        "comparison_pair_count": 0, "max_live_recall_probe_score": 0.0,
        "live_pairs_newly_routed_by_probe": 0,
        "live_recall_lift_status": "live_blocked_by_rate_or_opt_in",
        "discrete_event_seed_selected": "fomc_decision",
        "production_candidate_status": "blocked_no_live_opt_in",
        "production_candidate_batch_ready": False, "production_frozen_pair_count": 0,
        "candidate_provenance": "none", "blocked_reason": "blocked_no_live_opt_in",
        "community_reaction_layer_contract_ready": True,
        "production_gold_count": 0, "current_r1_gap": 200,
        "score_exposed": False, "rationale_exposed": False, "predicted_status_exposed": False,
        "raw_pii_exposed": False, "merge_allowed": False, "db_write": False,
        "llm_invoked": False, "embedding_invoked": False,
        "block_reasons": ["not_opted_in"], "next_actions": ["existing_next"],
    }
    base.update(over)
    return base


def test_operation_and_breadth_wired():
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    assert out["operation_name"] == "provider_breadth_named_seed_ko_path"
    assert out["provider_breadth_inventory_ready"] is True
    # 실 registry 57 = 9 카테고리(분석 §2).
    assert out["query_capable_publishable_count"] == 7
    assert out["feed_only_publishable_count"] == 7
    assert out["official_source_count"] == 5
    assert out["search_url_candidate_count"] == 4
    assert out["ko_official_news_count"] == 6
    assert out["community_reaction_only_count"] == 9
    assert out["market_signal_only_count"] == 6
    assert out["catalog_enrichment_only_count"] == 9
    assert out["unknown_quarantine_count"] == 4
    assert out["anchor_eligible_count"] == 25
    assert out["source_role_guard_preserved"] is True


def test_live_off_blocked_no_opt_in():
    """§7: live 미승인 → executed False · blocked_no_live_opt_in · ask_for_bounded_live_run_approval."""
    out = run_provider_breadth_named_seed_ko_path(base_result=_base(), live_query=False)
    assert out["live_query_approved"] is False
    assert out["live_query_executed"] is False
    assert out["live_run_status"] == LIVE_BLOCKED_NO_OPT_IN
    assert LIVE_BLOCKED_NO_OPT_IN in out["block_reasons"]
    assert any("ask_for_bounded_live_run_approval" in a for a in out["next_actions"])


def test_named_seed_selected_is_named_single_event():
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    assert out["named_single_event_seed_bank_ready"] is True
    assert out["named_seed_count"] >= 2
    assert out["broad_seed_rejected_count"] >= 5
    sel = out["selected_seed_for_next_live_run"]
    assert sel is not None
    assert sel["accepted"] is True
    assert sel["live_run_allowed_if_approved"] is True


def test_ko_path_wired():
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    assert out["ko_source_path_ready"] is True
    assert out["ko_tokenization_risk_recorded"] is True
    assert out["ko_tokenization_risk"]["has_korean_morphological_analysis"] is False
    assert out["ko_floor_solved"] is False
    assert out["naver_adapter_status"]["implemented"] is True


def test_frontier_sanitized_and_schema_constructs():
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    fr = out["internal_ops_provider_breadth_frontier"]
    # required copy(§10).
    for copy in ("Provider breadth is acquisition support, not truth",
                 "Named seed is candidate generation, not same-event proof",
                 "Community reaction is not an event anchor",
                 "Production gold remains 0 until human labels are returned",
                 "R2~R7 remain No-Go"):
        assert copy in fr["required_copy"]
    # forbidden 키 부재(same_event truth/per-pair score/rationale/predicted_status/raw body/PII/secret).
    for forbidden in ("score", "rationale", "predicted_status", "raw_body", "same_event_truth",
                      "reviewer_name", "email", "secret"):
        assert forbidden not in fr
    # 스키마 화이트리스트 통과(구조적 미노출).
    m = InternalOpsProviderBreadthFrontier(**fr)
    assert m.contract == "InternalOpsProviderBreadthFrontier"
    assert m.seed_type == "named_single_event"
    assert m.live_recall_lift_status == "live_blocked_by_rate_or_opt_in"
    assert m.r2_r7_no_go is True


def test_no_merge_llm_db_public_iu_gold():
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    assert out["merge_allowed"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["db_write"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["public_truth_exposed"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["actual_sending_performed"] is False
    assert out["production_gold_count"] == 0
    assert out["r2_r7_no_go"] is True


def test_pii_safe_no_forbidden_keys_anywhere():
    """전체 출력에 forbidden exact-key 없음(_assert_pii_safe 통과 + 직렬화 확인)."""
    out = run_provider_breadth_named_seed_ko_path(base_result=_base())
    blob = json.dumps(out, ensure_ascii=False, default=str)
    # bare per-pair score/ rationale 키가 어떤 depth 에도 없어야(요약 aggregate 만).
    assert '"score":' not in blob
    assert '"rationale":' not in blob
    assert '"predicted_status":' not in blob
    assert '"raw_body":' not in blob


def test_live_executed_passthrough():
    """base 가 live 실행됨(lift found) → live_run_status = base status · blocked_no_live_opt_in 아님."""
    base = _base(targeted_live_query_executed=True,
                 live_recall_lift_status="live_no_recall_lift",
                 comparison_pair_count=100, max_live_recall_probe_score=0.1765,
                 blocked_reason="")
    out = run_provider_breadth_named_seed_ko_path(base_result=base, live_query=True)
    assert out["live_query_executed"] is True
    assert out["live_run_status"] == "live_no_recall_lift"
    assert LIVE_BLOCKED_NO_OPT_IN not in out["block_reasons"]
    assert out["comparison_pair_count"] == 100
    assert out["max_live_recall_probe_score"] == 0.1765


def test_real_base_integration_live_off():
    """실 discrete base(live_query=False·network 0) 통합 — gold 0·gap 노출·frontier 스키마 통과."""
    out = run_provider_breadth_named_seed_ko_path(live_query=False)
    assert out["operation_name"] == "provider_breadth_named_seed_ko_path"
    assert out["live_query_executed"] is False
    assert out["production_gold_count"] == 0
    assert out["current_r1_gap"] >= 0
    assert out["provider_breadth_inventory_ready"] is True
    InternalOpsProviderBreadthFrontier(**out["internal_ops_provider_breadth_frontier"])
