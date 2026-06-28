"""ADR#82 — bounded live breadth run + date-pin gate + production candidate freeze attempt 테스트.

검증: ① named seed date-pin 게이트(occurrence_date 없으면 not pinned·blocked) · ② bounded live pool = anchor_eligible
∩ adapter_wired ∩ credential(breadth 크기가 아님·key-free/credential 분리) · ③ live-derived pair 없으면 freeze 없음·
있으면 worklist passthrough(same_event 단정 0·gold 0) · ④ KO source lane(EN run 분리) · ⑤ frontier 30 필드 sanitized ·
⑥ merge/LLM/embedding/DB/전송 0 · ⑦ _assert_pii_safe 통과(score/rationale/predicted_status/raw PII/secret 0).
"""
from __future__ import annotations

from backend.app.schemas.internal_ops import InternalOpsBoundedLiveBreadthFrontier
from backend.app.tools.r1_bounded_live_breadth_run import (
    BLOCKED_MISSING_DATE_PIN,
    BLOCKED_QUERY_WIRING,
    LIVE_QUERY_TARGET_WIRED,
    build_bounded_live_provider_pool,
    run_bounded_live_breadth_run,
)


def _inv_rows() -> list[dict]:
    """provider breadth inventory rows(축약) — anchor-eligible guardian/nyt(wired,cred present)·gdelt(keyfree,미wired)·
    federal_register(keyfree,미wired)·community(anchor-eligible 아님)."""
    return [
        {"source_id": "guardian", "category": "query_capable_publishable", "anchor_eligible": True,
         "credential_required": True, "credential_presence_secret_safe": {"GUARDIAN_API_KEY": "present"},
         "query_capability": "topic+time_window"},
        {"source_id": "nyt", "category": "query_capable_publishable", "anchor_eligible": True,
         "credential_required": True, "credential_presence_secret_safe": {"NYT_API_KEY": "present"},
         "query_capability": "topic+time_window"},
        {"source_id": "gdelt", "category": "official_source", "anchor_eligible": True,
         "credential_required": False, "credential_presence_secret_safe": {},
         "query_capability": "topic+time_window"},
        {"source_id": "federal_register", "category": "official_source", "anchor_eligible": True,
         "credential_required": False, "credential_presence_secret_safe": {},
         "query_capability": "topic+time_window"},
        {"source_id": "yna", "category": "ko_official_news", "anchor_eligible": True,
         "credential_required": False, "credential_presence_secret_safe": {},
         "query_capability": "feed_only"},
        {"source_id": "reddit", "category": "community_reaction_only", "anchor_eligible": False,
         "credential_required": False, "credential_presence_secret_safe": {},
         "query_capability": "topic"},
    ]


def _synthetic_base(**overrides) -> dict:
    """orchestrator 단위 테스트용 합성 base(ADR#81 run_provider_breadth_named_seed_ko_path 출력 축약)."""
    base = {
        "actual_input_rechecked": True, "actual_contact_evidence_found": False,
        "actual_returned_labels_found": False, "actual_input_status": "external_input_required",
        "selected_seed_for_next_live_run": {"seed_id": "fomc_rate_decision"},
        "provider_breadth_inventory": _inv_rows(),
        "live_query_executed": False, "live_recall_lift_status": "live_blocked_by_rate_or_opt_in",
        "live_call_count": 0, "providers_used": ["guardian", "nyt"], "comparison_pair_count": 0,
        "max_live_recall_probe_score": 0.0, "live_pairs_newly_routed_by_probe": 0,
        "live_pairs_sharing_entity_after_probe": 0, "max_baseline_jaccard": 0.0,
        "production_candidate_status": "blocked_no_live_opt_in", "production_candidate_batch_ready": False,
        "production_batch_id": "reviewer_prod_cand_001", "production_frozen_pair_count": 0,
        "candidate_provenance": "none", "production_gold_count": 0, "current_r1_gap": 200,
        "source_role_guard_preserved": True,
        "score_exposed": False, "rationale_exposed": False, "predicted_status_exposed": False,
        "raw_pii_exposed": False, "merge_allowed": False, "db_write": False, "llm_invoked": False,
        "embedding_invoked": False, "block_reasons": ["not_opted_in"], "next_actions": ["x"],
    }
    base.update(overrides)
    return base


# ── ① date-pin 게이트 ──────────────────────────────────────────────────────────────────────────────────────
def test_default_no_date_pin_blocks_live_with_missing_date_pin_reason():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    assert out["named_seed_selected"] == "fomc_rate_decision"
    assert out["named_seed_date_pinned"] is False
    assert out["selected_seed_actual_occurrence"] is None
    assert out["blocked_reason"] == BLOCKED_MISSING_DATE_PIN
    assert out["live_query_executed"] is False
    assert "missing_occurrence_date" in out["named_seed_date_pin_status"]


def test_operator_pinned_event_records_occurrence_but_not_executed_without_opt_in():
    pinned = {"seed_id": "fomc_2026_06_17", "named_entity": "US Federal Reserve FOMC",
              "event_phrase": "FOMC federal funds rate decision announcement", "date_window": "1d",
              "provider_coverage_hypothesis": "guardian+nyt", "occurrence_date": "2026-06-17"}
    out = run_bounded_live_breadth_run(base_result=_synthetic_base(), pinned_event=pinned)
    assert out["named_seed_date_pinned"] is True
    assert out["selected_seed_actual_occurrence"] == "2026-06-17"
    # date-pin 충족이나 live 미실행 → blocked_reason 은 더 이상 missing_date_pin 아님(query-wiring blocker).
    assert out["live_query_executed"] is False
    assert out["blocked_reason"] != BLOCKED_MISSING_DATE_PIN


def test_date_pinned_plus_optin_still_blocked_query_wiring_not_implemented():
    """date-pin 충족 + live_query 승인이어도 pinned-event→실 쿼리 plumbing 미구현이라 fail-closed(정직·둔갑 금지)."""
    assert LIVE_QUERY_TARGET_WIRED is False   # 이 ADR 에서는 미배선이 진실.
    pinned = {"seed_id": "fomc_2026_06_17", "named_entity": "US Federal Reserve FOMC",
              "event_phrase": "FOMC federal funds rate decision announcement", "date_window": "1d",
              "provider_coverage_hypothesis": "guardian+nyt", "occurrence_date": "2026-06-17"}
    out = run_bounded_live_breadth_run(base_result=_synthetic_base(), pinned_event=pinned, live_query=True)
    assert out["named_seed_date_pinned"] is True
    assert out["live_query_target_wired"] is False
    assert out["live_query_executed"] is False
    assert out["blocked_reason"] == BLOCKED_QUERY_WIRING
    assert BLOCKED_QUERY_WIRING in out["block_reasons"]


# ── ② bounded live pool(adapter_wired ∩ credential·breadth 크기 아님) ─────────────────────────────────────────
def test_pool_is_adapter_wired_intersect_credential_not_breadth_size():
    pool = build_bounded_live_provider_pool(_inv_rows())
    # guardian/nyt 만 wired+credential → runnable. gdelt/federal_register 는 query-capable 이나 미wired.
    assert pool["providers_in_pool"] == ["guardian", "nyt"]
    assert pool["provider_breadth_used"] == 2
    assert pool["key_free_provider_count"] == 0
    assert pool["credential_required_provider_count"] == 2
    assert "gdelt" in pool["query_capable_not_yet_wired"]
    assert "federal_register" in pool["query_capable_not_yet_wired"]
    # community(anchor_eligible=False)는 pool 진입 자체 불가(source role guard).
    assert all(p["source_id"] != "reddit" for p in pool["bounded_live_provider_pool"])
    assert pool["source_role_guard_preserved"] is True


def test_pool_missing_credential_drops_from_runnable():
    rows = _inv_rows()
    rows[0]["credential_presence_secret_safe"] = {"GUARDIAN_API_KEY": "missing"}  # guardian cred 결여.
    pool = build_bounded_live_provider_pool(rows)
    assert pool["providers_in_pool"] == ["nyt"]
    assert pool["provider_breadth_used"] == 1


# ── ③ production candidate freeze(live-derived 없으면 없음·있으면 worklist passthrough) ───────────────────────
def test_no_live_derived_pair_means_no_freeze():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    assert out["production_candidate_batch_ready"] is False
    assert out["production_frozen_pair_count"] == 0
    assert out["production_gold_count"] == 0


def test_live_derived_freeze_passthrough_is_worklist_not_truth():
    base = _synthetic_base(
        live_query_executed=True, live_recall_lift_status="live_no_recall_lift",
        providers_used=["guardian", "nyt"], comparison_pair_count=40,
        production_candidate_status="frozen_live_derived", production_candidate_batch_ready=True,
        production_frozen_pair_count=3, candidate_provenance="live_derived")
    out = run_bounded_live_breadth_run(base_result=base)
    assert out["live_query_executed"] is True
    assert out["production_candidate_batch_ready"] is True
    assert out["production_frozen_pair_count"] == 3
    assert out["candidate_provenance"] == "live_derived"
    # freeze 여도 same_event 단정 0·gold 0(불변).
    assert out["same_event_truth_exposed"] is False
    assert out["production_gold_count"] == 0
    assert out["providers_used"] == ["guardian", "nyt"]


# ── ④ KO source lane(EN run 분리) ────────────────────────────────────────────────────────────────────────────
def test_ko_source_lane_present_and_floor_unsolved():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    assert out["ko_source_lane_status"].startswith("ready_") or out["ko_source_lane_status"].startswith("blocked_")
    assert out["ko_named_seed_needed"] is True
    assert out["ko_floor_current"] == 0
    assert out["ko_floor_required"] == 50


# ── ⑤ frontier 30 필드 sanitized + dict==pydantic ──────────────────────────────────────────────────────────
def test_frontier_matches_pydantic_schema_exactly():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    f = out["internal_ops_bounded_live_breadth_frontier"]
    model = InternalOpsBoundedLiveBreadthFrontier(**f)  # raises on missing/type mismatch.
    assert set(f.keys()) == set(InternalOpsBoundedLiveBreadthFrontier.model_fields.keys())
    assert len(f) == 30
    assert model.r2_r7_no_go is True
    assert len(f["flags"]) == 7


def test_frontier_has_no_forbidden_fields():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    f = out["internal_ops_bounded_live_breadth_frontier"]
    for forbidden in ("score", "rationale", "predicted_status", "same_event", "raw_body", "body",
                      "reviewer_email", "reviewer_name", "secret"):
        assert forbidden not in f


# ── ⑥/⑦ 안전 경계(merge/LLM/embedding/DB/전송 0 · 노출 0) ────────────────────────────────────────────────────
def test_no_merge_no_llm_no_embedding_no_db_no_sending():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    assert out["merge_allowed"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["db_write"] is False
    assert out["actual_sending_performed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["r2_r7_no_go"] is True


def test_no_truth_score_pii_secret_exposed():
    out = run_bounded_live_breadth_run(base_result=_synthetic_base())
    assert out["public_truth_exposed"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["score_exposed"] is False
    assert out["rationale_exposed"] is False
    assert out["predicted_status_exposed"] is False
    assert out["raw_pii_exposed"] is False
    assert out["raw_source_body_exposed"] is False
    assert out["host_gate_respected"] is True
    assert out["rate_limit_respected"] is True
    assert out["sanitized_live_snapshot_written"] is False


# ── 실 통합(합성 base 없이 — 실제 base + 실 registry) ────────────────────────────────────────────────────────
def test_real_integration_blocked_no_date_pin_pool_guardian_nyt():
    out = run_bounded_live_breadth_run()
    assert out["operation_name"] == "bounded_live_breadth_run_and_candidate_freeze_attempt"
    assert out["named_seed_date_pinned"] is False
    assert out["blocked_reason"] == BLOCKED_MISSING_DATE_PIN
    assert out["live_query_executed"] is False
    # 실 registry+실 adapter: guardian/nyt 만 wired. gdelt/federal_register 는 미wired.
    assert set(out["providers_in_pool"]).issubset({"guardian", "nyt"})
    assert "gdelt" in out["query_capable_not_yet_wired"]
    assert out["production_gold_count"] == 0
    assert out["current_r1_gap"] == 200
    assert out["source_role_guard_preserved"] is True
