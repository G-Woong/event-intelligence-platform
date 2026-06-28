"""ADR#79 — r1_discrete_event_acquisition 테스트(discrete seed 검증·recall probe 통합·merge 분리·(i)/(ii) 보존·안전).

§12 시나리오: discrete-event acquisition(8–15)·near-match root-cause(16–20)·recall probe(21–27)·no merge/LLM/DB(57–62).
"""
from __future__ import annotations

import json

from backend.app.tools import r1_discrete_event_acquisition as dea

REQUIRED_OUTPUT_FIELDS = [
    "operation_name", "actual_input_rechecked", "actual_contact_evidence_found",
    "actual_returned_labels_found", "actual_input_status", "discrete_event_seed_selected",
    "discrete_event_seed_source", "discrete_event_time_window", "targeted_live_query_approved",
    "targeted_live_query_executed", "live_call_count", "providers_used", "live_candidate_count",
    "comparison_pair_count", "max_title_jaccard", "max_recall_probe_score", "near_match_gap_status",
    "root_cause_hypotheses", "root_cause_confidence", "deterministic_recall_probe_ready",
    "recall_probe_applies_to_reviewer_routing_only", "recall_probe_applies_to_merge",
    "normalization_features_tested", "production_candidate_status", "production_candidate_batch_ready",
    "production_batch_id", "production_frozen_pair_count", "candidate_provenance", "blocked_reason",
    "provider_breadth_plan_ready", "korean_source_path_ready", "acquisition_frontier_status_persisted",
    "acquisition_frontier_ui_ready", "llm_rag_kg_contract_guard_ready", "production_gold_count",
    "current_r1_gap", "r2_r7_no_go", "public_truth_exposed", "same_event_truth_exposed", "score_exposed",
    "rationale_exposed", "predicted_status_exposed", "raw_pii_exposed", "raw_source_body_exposed",
    "no_public_intelligence_unit", "merge_allowed", "db_write", "llm_invoked", "embedding_invoked",
    "actual_sending_performed", "block_reasons", "next_actions",
]


def _run(**kw):
    return dea.run_discrete_event_acquisition_and_recall_probe(**kw)


# ── §5 discrete-event seed 검증(8–11) ─────────────────────────────────────────────────────────────────────
def test_discrete_event_seed_accepted():
    v = dea.validate_discrete_event_seed(
        {"seed_id": "fomc", "topic": "Federal Reserve FOMC rate decision", "time_window": "1d"})
    assert v["valid"] is True
    assert v["discrete_event_shape"] is True
    assert v["reject_reasons"] == []


def test_broad_umbrella_seed_rejected():
    v = dea.validate_discrete_event_seed({"seed_id": "fed", "topic": "Federal Reserve", "time_window": "1d"})
    assert v["valid"] is False
    assert "broad_umbrella_topic" in v["reject_reasons"]


def test_broad_war_topic_rejected():
    v = dea.validate_discrete_event_seed({"seed_id": "uk", "topic": "Ukraine war", "time_window": "1d"})
    assert v["valid"] is False
    assert "broad_umbrella_topic" in v["reject_reasons"]


def test_entity_only_without_event_phrase_rejected():
    v = dea.validate_discrete_event_seed({"seed_id": "sc", "topic": "Supreme Court", "time_window": "1d"})
    assert v["valid"] is False
    assert "no_discrete_event_phrase" in v["reject_reasons"]


def test_one_day_window_supported():
    v = dea.validate_discrete_event_seed(
        {"seed_id": "ec", "topic": "European Central Bank rate decision", "time_window": "1d"})
    assert v["valid"] is True


def test_broad_window_rejected_as_not_discrete():
    v = dea.validate_discrete_event_seed(
        {"seed_id": "sc", "topic": "Supreme Court major ruling", "time_window": "7d"})
    assert v["valid"] is False
    assert "time_window_not_discrete" in v["reject_reasons"]


def test_community_market_catalog_topic_rejected():
    for topic in ("reddit stock discussion", "ticker price chart", "product listing page"):
        v = dea.validate_discrete_event_seed({"seed_id": "x", "topic": topic, "time_window": "1d"})
        assert v["valid"] is False
        assert "community_market_catalog_only_topic" in v["reject_reasons"]


def test_single_generic_word_rejected():
    v = dea.validate_discrete_event_seed({"seed_id": "x", "topic": "climate", "time_window": "1d"})
    assert v["valid"] is False
    assert "topic_not_event_specific" in v["reject_reasons"]


def test_default_seeds_all_valid_discrete_shape():
    for s in dea.DISCRETE_EVENT_SEEDS:
        v = dea.validate_discrete_event_seed(s)
        assert v["valid"] is True
        assert v["seed_source"] == "code_proposed_shape"     # 특정 사건 날조 0(정직 표기).


# ── §4 output 계약(12–15) ─────────────────────────────────────────────────────────────────────────────────
def test_output_has_all_required_fields():
    out = _run()
    for f in REQUIRED_OUTPUT_FIELDS:
        assert f in out, f"missing required field: {f}"
    assert out["operation_name"] == "r1_discrete_event_acquisition_and_recall_probe"


def test_live_not_executed_without_opt_in():
    out = _run(live_query=False)
    assert out["targeted_live_query_approved"] is False
    assert out["targeted_live_query_executed"] is False
    assert out["live_call_count"] == 0
    assert out["comparison_pair_count"] == 0


def test_selected_discrete_seed_passthrough():
    out = _run()
    assert out["discrete_event_seed_selected"] == "fomc_decision"
    assert out["discrete_event_seed_source"] == "code_proposed_shape"
    assert out["discrete_event_time_window"] == "1d"


def test_no_raw_source_body():
    out = _run()
    assert out["raw_source_body_exposed"] is False


# ── near-match root-cause 보존(16–20) ─────────────────────────────────────────────────────────────────────
def test_root_cause_not_overclaimed():
    out = _run()
    assert out["same_event_truth_asserted"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["root_cause_confidence"] != "high"          # 단정 금지(indeterminate/n/a/low).


def test_root_cause_hypotheses_is_list():
    out = _run()
    assert isinstance(out["root_cause_hypotheses"], list)


def test_recall_probe_refinement_defers_live_verdict():
    # ADR#80: dry 모드(live off)는 3분류상 live_blocked_by_rate_or_opt_in(opt-in off=실행 블록). synthetic lever 는 보존.
    out = _run()
    ref = out["recall_probe_root_cause_refinement"]
    assert ref["recall_probe_lever_demonstrated"] is True   # synthetic 에서 lever 작동 증명.
    assert ref["live_recall_probe_applied"] is False        # live 미실행 → live pair 미적용.
    assert ref["live_frontier_verdict"] == "live_blocked_by_rate_or_opt_in"
    assert ref["same_event_truth_asserted"] is False        # 실 frontier 단정 0.


# ── recall probe 통합(21–27) ──────────────────────────────────────────────────────────────────────────────
def test_normalization_features_tested_present():
    out = _run()
    assert out["normalization_features_tested"]
    assert "organization_phrase_alias" in out["normalization_features_tested"]
    assert "acronym_alias" in out["normalization_features_tested"]


def test_recall_probe_lifts_known_paraphrases():
    out = _run()
    s = out["recall_probe_summary"]
    assert s["pairs_newly_routed_by_probe"] >= 2            # below-floor 같은-사건 lift 측정.
    assert s["pairs_newly_routed_sharing_entity"] >= 2
    assert out["max_recall_probe_score"] > 0.0


def test_recall_probe_does_not_set_merge_allowed():
    out = _run()
    assert out["recall_probe_applies_to_merge"] is False
    assert out["recall_probe_applies_to_reviewer_routing_only"] is True
    assert out["merge_allowed"] is False
    assert out["recall_probe_summary"]["merge_allowed"] is False


def test_recall_probe_score_not_reviewer_facing():
    out = _run()
    s = out["recall_probe_summary"]
    assert s["score_exposed_to_reviewer"] is False
    assert s["score_exposed_to_public"] is False
    assert out["score_exposed"] is False


def test_synthetic_production_separation_preserved():
    out = _run()
    assert out["candidate_provenance"] == "none"           # live-derived 후보 0 → 둔갑 0.
    assert out["production_frozen_pair_count"] == 0
    assert out["production_candidate_batch_ready"] is False


# ── no merge / no LLM / no DB / no sending(57–62) ─────────────────────────────────────────────────────────
def test_all_runtime_gates_off():
    out = _run()
    assert out["merge_allowed"] is False
    assert out["llm_invoked"] is False
    assert out["embedding_invoked"] is False
    assert out["db_write"] is False
    assert out["actual_sending_performed"] is False
    assert out["no_public_intelligence_unit"] is True
    assert out["public_truth_exposed"] is False


def test_r1_gold_and_gap_passthrough():
    out = _run()
    assert out["production_gold_count"] == 0
    assert out["current_r1_gap"] == 200
    assert out["r2_r7_no_go"] is True


def test_contract_guard_ready_runtime_unbuilt():
    out = _run()
    assert out["llm_rag_kg_contract_guard_ready"] is True
    assert out["product_bridge_runtime_built"] is False     # 계약만·runtime 0.


def test_provider_and_korean_plans_ready():
    out = _run()
    assert out["provider_breadth_plan_ready"] is True
    assert out["korean_source_path_ready"] is True
    ko = out["korean_source_strategy"]
    assert ko["ko_floor_current_gold"] == 0
    assert ko["ko_floor_gap_visible"] is True


# ── frontier sanitized(no same_event truth/score/PII) + 안전 가드 ─────────────────────────────────────────
def test_frontier_sanitized_flags():
    out = _run()
    fr = out["internal_ops_discrete_acquisition_frontier"]
    assert fr["recall_probe_applies_to_merge"] is False
    assert fr["r2_r7_no_go"] is True
    flags = fr["flags"]
    assert all(flags[k] for k in ("no_public_truth", "no_same_event_truth", "no_score",
                                  "no_rationale", "no_predicted_status", "no_raw_body", "no_secret"))


def test_actual_input_recheck_no_fabrication():
    out = _run()
    assert out["actual_input_status"] == "no_actual_input"
    assert out["actual_returned_labels_found"] is False
    assert "external_reviewer_input_required" in out["block_reasons"]


def test_determinism():
    assert _run() == _run()


def test_no_valid_seed_blocks():
    # 전부 broad → no_valid_discrete_event_seed.
    out = _run(seeds=[{"seed_id": "b1", "topic": "Federal Reserve", "time_window": "1d"},
                      {"seed_id": "b2", "topic": "stock market", "time_window": "7d"}])
    assert out["discrete_event_seed_selected"] is None
    assert "no_valid_discrete_event_seed" in out["block_reasons"]


# ── ADR#80: live recall probe applied to ACTUAL cross-source pairs (3-bucket·merge 0·gold 0) ─────────────
DAY = "2026-06-22"


def _g_payload(items, day=DAY):
    return json.dumps({"response": {"status": "ok", "total": len(items), "results": [
        {"webTitle": t, "webUrl": u, "webPublicationDate": day + "T08:00:00Z"} for t, u in items]}})


def _n_payload(items, day=DAY):
    return json.dumps({"status": "OK", "response": {"docs": [
        {"headline": {"main": t}, "web_url": u, "pub_date": day + "T09:00:00Z"} for t, u in items]}})


def _probe(_v):
    return {"var_name": _v, "credential_present": True, "env_file_present": True, "declared_in_example": True}


def _ready():
    return {"credential_status": {"guardian": True, "nyt": True}}


def _gate(**_kw):
    return {
        "actual_input_status": "no_actual_input", "external_input_required": True,
        "actual_contact_evidence_found": False, "actual_returned_labels_found": False,
        "returned_label_count": 0, "production_gold_count": 0, "synthetic_gold_count": 0,
        "calibration_ready": False, "merge_gate_ready": False,
        "input_directory": "outputs/reviewer_batch/intake",
        "score_exposed": False, "rationale_exposed": False, "predicted_status_exposed": False,
        "raw_pii_exposed": False, "no_public_intelligence_unit": True, "merge_allowed": False,
        "db_write": False, "llm_invoked": False, "embedding_invoked": False,
        "next_actions": [], "block_reasons": [],
    }


def _synth(**_kw):
    return {"batch_frozen": True, "pilot_batch_is_production_candidate": False,
            "batch_id": "synthetic_pilot", "frozen_pair_count": 4}


def _tf_lift(seed_id, provider):
    """below-floor same-event paraphrase(fed≡federal reserve) → probe 가 routing 으로 lift."""
    if provider == "guardian":
        return lambda _u: _g_payload([("Fed raises rates again", "https://g/fed")])
    return lambda _u: _n_payload([("Federal Reserve lifts interest rates", "https://nyt/fed")])


def _tf_no_lift(seed_id, provider):
    """cross pair·entity 공유하나 정규화 후도 routing floor 미달 → no_lift(different-events/normalization 한계)."""
    if provider == "guardian":
        return lambda _u: _g_payload([("Federal Reserve holds interest rates steady amid inflation", "https://g/a")])
    return lambda _u: _n_payload([("Fed keeps rates unchanged as policymakers weigh economy", "https://nyt/a")])


def _tf_zero_overlap(seed_id, provider):
    """양 provider 가 records 반환(live 실행)하나 다른 날짜 → cross-source same-date 비교쌍 0(overlap 부재)."""
    if provider == "guardian":
        return lambda _u: _g_payload([("Federal Reserve rate decision announced", "https://g/a")], day="2026-06-22")
    return lambda _u: _n_payload([("Supreme Court issues major ruling", "https://nyt/a")], day="2026-06-10")


def _run_live(tf, *, live_query=True):
    return dea.run_discrete_event_acquisition_and_recall_probe(
        live_query=live_query, seeds=[dea.DISCRETE_EVENT_SEEDS[0]],
        transport_factory=tf, env_probe_fn=_probe, readiness_fn=_ready, gate_fn=_gate, synthetic_batch_fn=_synth)


def test_live_recall_lift_found_on_actual_pair():
    """ADR#80: 실 cross-source below-floor pair 를 probe 가 lift → live_recall_lift_found(reviewer-routing 후보)."""
    out = _run_live(_tf_lift)
    assert out["targeted_live_query_executed"] is True
    assert out["live_recall_probe_applied"] is True
    assert out["live_recall_lift_status"] == "live_recall_lift_found"
    assert out["live_pairs_newly_routed_by_probe"] >= 1
    assert out["live_pairs_sharing_entity_after_probe"] >= 1
    assert out["max_live_recall_probe_score"] >= 0.2
    assert out["recall_probe_root_cause_refinement"]["live_frontier_verdict"] == "live_recall_lift_found"


def test_live_recall_lift_found_never_merge_or_gold():
    """ADR#80 불변: live lift 가 나와도 merge 0·same_event 0·gold 0(reviewer-routing 후보일 뿐)."""
    out = _run_live(_tf_lift)
    assert out["merge_allowed"] is False
    assert out["recall_probe_applies_to_merge"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["production_gold_count"] == 0
    assert out["current_r1_gap"] == 200


def test_live_no_recall_lift_when_below_floor():
    """ADR#80: cross pair 존재·probe 가 정규화는 했으나 routing floor 미달 → live_no_recall_lift(same-event 단정 아님)."""
    out = _run_live(_tf_no_lift)
    assert out["targeted_live_query_executed"] is True
    assert out["live_recall_probe_applied"] is True              # cross pair 존재→probe 적용됨.
    assert out["live_recall_lift_status"] == "live_no_recall_lift"
    assert out["live_pairs_newly_routed_by_probe"] == 0
    # probe 가 정규화로 score 를 만들었으나(>0·entity federalreserve 공유) routing floor(0.2) 미달 → 미lift.
    assert 0.0 < out["max_live_recall_probe_score"] < 0.2


def test_live_no_recall_lift_when_zero_comparison_pairs():
    """ADR#80: live 실행됐으나 cross-source 비교쌍 0(overlap 부재·breadth lever) → live_no_recall_lift(blocked 아님)."""
    out = _run_live(_tf_zero_overlap)
    assert out["targeted_live_query_executed"] is True           # 양 provider records→실행됨(blocked 아님).
    assert out["comparison_pair_count"] == 0                     # 다른 날짜→same-date cross pair 0.
    assert out["live_recall_probe_applied"] is False             # live pair 부재→probe 미적용(None).
    assert out["live_recall_lift_status"] == "live_no_recall_lift"
    assert out["live_pairs_newly_routed_by_probe"] == 0


def test_live_blocked_when_not_opted_in():
    """ADR#80: live 미실행 → live_blocked_by_rate_or_opt_in(코드 실패 아닌 실행 블록·data 판정 아님)."""
    out = _run_live(_tf_lift, live_query=False)
    assert out["targeted_live_query_executed"] is False
    assert out["live_recall_probe_applied"] is False
    assert out["live_recall_lift_status"] == "live_blocked_by_rate_or_opt_in"
    assert out["live_recall_lift_blocked_reason"]              # 실행 블록 사유 명시.


def test_live_recall_frontier_aggregate_only_no_per_pair_score():
    """ADR#80 §8: internal ops frontier 는 max aggregate + newly-routed count 만(per-pair score 미노출)."""
    out = _run_live(_tf_lift)
    fr = out["internal_ops_discrete_acquisition_frontier"]
    assert "max_live_recall_probe_score" in fr
    assert "live_pairs_newly_routed_by_probe" in fr
    assert "live_recall_lift_status" in fr
    assert "top_lift_samples" not in fr and "recall_probe_score" not in fr   # per-pair 미노출(aggregate only).
    assert "Newly routed does not mean same event" in fr["required_copy"]
    assert "Recall probe is reviewer-routing only, not merge" in fr["required_copy"]


def test_live_recall_output_pii_safe():
    """ADR#80: live 적용 출력에 exact score/rationale/predicted_status 키 0(재귀 가드 통과)."""
    out = _run_live(_tf_lift)
    blob = json.dumps(out, ensure_ascii=False)
    assert '"score":' not in blob
    assert '"rationale":' not in blob
    assert '"predicted_status":' not in blob
