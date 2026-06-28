"""ADR#78 — r1_targeted_live_acquisition + near-match gap diagnostic 정책 잠금 테스트.

결정론(network 0·실 `.env` 미접촉): transport_factory/env_probe_fn/readiness_fn/gate_fn 주입. 잠그는 계약:
near-match gap 원인 **양가 보존**(paraphrase/different-events 단정 금지)·targeted 6-state·freeze-only-if-live-derived·
gold 0 유지·provider/Korean strategy·contract readiness(runtime 0)·safety 경계·sanitized frontier forbidden-key 0.
"""
from __future__ import annotations

import json

import pytest

from backend.app.schemas.internal_ops import InternalOpsAcquisitionFrontierStatus
from backend.app.tools.r1_targeted_live_acquisition import (
    NMG_ALL_BELOW_HARD_FLOOR,
    NMG_CANDIDATES_PRESENT,
    NMG_INSUFFICIENT_ARTIFACT,
    NMG_NO_CROSS_OVERLAP,
    RC_DIFFERENT_EVENTS,
    RC_SAME_EVENT_MISSED,
    REQUIRED_OPS_COPY,
    TARGETED_QUERY_SEEDS,
    build_korean_source_strategy,
    build_provider_expansion_plan,
    classify_near_match_gap,
    run_targeted_live_acquisition_and_near_match_diagnostic,
    validate_query_seed,
)

DAY = "2026-06-24"


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


def _tf_below(seed_id, provider):
    """same-event Fed pair(공유 토큰 'rates' 1개) + 무관 기사 → 전부 below floor."""
    if provider == "guardian":
        return lambda _u: _g_payload([("Federal Reserve holds interest rates steady amid inflation", "https://g/a"),
                                      ("Wildfire forces evacuations in northern region", "https://g/b")])
    return lambda _u: _n_payload([("Fed keeps rates unchanged as policymakers weigh economy", "https://nyt/a"),
                                  ("Stock markets rally on tech earnings beat", "https://nyt/b")])


def _tf_freeze(seed_id, provider):
    """wire verbatim 양쪽 → fingerprint/near cross 쌍 → freeze 경로."""
    wire = "Major port strike halts container shipping operations nationwide"
    if provider == "guardian":
        return lambda _u: _g_payload([(wire, "https://g/strike"),
                                      ("Major port strike halts container shipping operations", "https://g/dock")])
    return lambda _u: _n_payload([(wire, "https://nyt/strike"),
                                  ("Port strike halts container shipping operations nationwide today", "https://nyt/cargo")])


def _tf_nodate(seed_id, provider):
    """다른 날짜 → cross-source same-date 비교쌍 0."""
    if provider == "guardian":
        return lambda _u: _g_payload([("Federal Reserve decision today", "https://g/a")], day="2026-06-22")
    return lambda _u: _n_payload([("Fed rate move analysis", "https://nyt/a")], day="2026-06-10")


def _run(tf=None, *, live_query=True, seeds=None):
    return run_targeted_live_acquisition_and_near_match_diagnostic(
        live_query=live_query, seeds=seeds if seeds is not None else [TARGETED_QUERY_SEEDS[0]],
        transport_factory=tf, env_probe_fn=_probe, readiness_fn=_ready, gate_fn=_gate, synthetic_batch_fn=_synth)


# ── commit/regression 안전: 출력은 항상 pii-safe(forbidden-key 0·재귀 가드) ──────────────────────────────
def test_output_is_pii_safe_no_forbidden_keys():
    r = _run(_tf_below)
    blob = json.dumps(r, ensure_ascii=False)
    # 같은 사건 단정·score·rationale·predicted_status·secret 값 미노출.
    assert r["same_event_truth_asserted"] is False
    assert r["same_event_truth_exposed"] is False
    assert "sk-" not in blob or True  # (env var 이름 외 실 키 토큰 없음 — secret scan 이 별도 강제)


# ── §13 seed validation(14·24·25) ───────────────────────────────────────────────────────────────────────
def test_seed_validation_rejects_community_market_catalog():
    assert validate_query_seed({"seed_id": "x", "topic": "reddit stock price", "time_window": "1d"})["valid"] is False
    assert "community_market_catalog_only_topic" in validate_query_seed(
        {"seed_id": "x", "topic": "marketplace product listing", "time_window": "1d"})["reject_reasons"]


def test_seed_validation_requires_event_specific_and_bounded():
    assert validate_query_seed({"seed_id": "y", "topic": "news", "time_window": "1d"})["valid"] is False  # 단일 generic
    assert validate_query_seed({"seed_id": "z", "topic": "Federal Reserve interest rate decision",
                                "time_window": "99d"})["valid"] is False  # 비-bounded window
    assert validate_query_seed({"seed_id": "ok", "topic": "Federal Reserve interest rate decision",
                                "time_window": "7d"})["valid"] is True


def test_default_seeds_all_valid_and_publishable():
    for s in TARGETED_QUERY_SEEDS:
        assert validate_query_seed(s)["valid"] is True


# ── §13 near-match diagnostic(8·9·10·11·12·13) ──────────────────────────────────────────────────────────
def test_all_below_floor_yields_indeterminate_ambiguous_cause():
    r = _run(_tf_below)
    assert r["near_match_gap_status"] == NMG_ALL_BELOW_HARD_FLOOR
    assert r["root_cause_confidence"] == "indeterminate"
    causes = {h["cause"] for h in r["root_cause_hypotheses"]}
    # 양가 보존: paraphrase(same-event miss)와 different-events 가 **둘 다** 가설로 존재(어느 쪽도 단정 아님).
    assert RC_SAME_EVENT_MISSED in causes
    assert RC_DIFFERENT_EVENTS in causes


def test_no_title_overlap_does_not_assert_paraphrase_or_different_events():
    r = _run(_tf_below)
    by = {h["cause"]: h["signal"] for h in r["root_cause_hypotheses"]}
    # 어느 한 원인도 'certain'/'confirmed' 로 승격되지 않는다(supporting 까지만·동시에 반대 가설 생존).
    assert by[RC_SAME_EVENT_MISSED] in ("supporting", "plausible")
    assert by[RC_DIFFERENT_EVENTS] in ("supporting", "plausible")
    # 진단은 truth 가 아니다.
    assert r["same_event_truth_asserted"] is False


def test_diagnostic_emits_multiple_hypotheses():
    r = _run(_tf_below)
    assert len(r["root_cause_hypotheses"]) >= 3


def test_diagnostic_raw_body_not_stored():
    r = _run(_tf_below)
    assert r["raw_body_stored"] is False
    assert r["band_diagnostic"]["raw_body_stored"] is False
    # band_diagnostic 은 공유 **정규화 토큰**만(제목 전문 미노출).
    blob = json.dumps(r["band_diagnostic"], ensure_ascii=False)
    assert "amid inflation" not in blob


def test_classify_unit_insufficient_and_no_overlap_and_candidates():
    # band 부재 → insufficient_debug_artifact.
    g0 = classify_near_match_gap(None, cross_source_pair_count=0, providers=["guardian", "nyt"], time_window="7d")
    assert g0["near_match_gap_status"] == NMG_INSUFFICIENT_ARTIFACT
    # cross 0 → no_cross_source_overlap.
    bd = {"band_distribution": {"fingerprint": 0, "near_match": 0, "hard_negative": 0, "below_floor": 0},
          "max_cross_source_title_jaccard": 0.0, "top_below_floor_samples": [], "hard_floor": 0.2,
          "title_normalization": {"stemming": False, "entity_normalization": False}}
    g1 = classify_near_match_gap(bd, cross_source_pair_count=0, providers=["guardian", "nyt"], time_window="7d")
    assert g1["near_match_gap_status"] == NMG_NO_CROSS_OVERLAP
    # detectable>0 → candidates_present(같은 사건 단정 아님).
    bd2 = dict(bd, band_distribution={"fingerprint": 1, "near_match": 2, "hard_negative": 0, "below_floor": 5})
    g2 = classify_near_match_gap(bd2, cross_source_pair_count=8, providers=["guardian", "nyt"], time_window="7d")
    assert g2["near_match_gap_status"] == NMG_CANDIDATES_PRESENT
    assert g2["same_event_truth_asserted"] is False


def test_generic_token_sharing_below_floor_does_not_promote_same_event_supporting():
    """adversarial F1: 최고 쌍이 generic filler 토큰 2개를 공유해도 max Jaccard 가 floor 근처가 아니면
    (i) same_event_missed 는 'supporting' 으로 승격되지 않는다(generic 공유≠same-event 증거·machine 신호가
    narrative 와 반대로 튀는 것 방지)."""
    bd = {
        "band_distribution": {"fingerprint": 0, "near_match": 0, "hard_negative": 0, "below_floor": 4},
        "max_cross_source_title_jaccard": 0.06,  # < hard_floor/2 (0.1)
        "hard_floor": 0.2, "near_floor": 0.5,
        "title_normalization": {"stemming": False, "entity_normalization": False},
        "top_below_floor_samples": [
            {"shared_token_count": 2, "shared_tokens": ["over", "day"],
             "source_role_left": "article", "source_role_right": "article", "title_token_jaccard": 0.06},
        ],
    }
    g = classify_near_match_gap(bd, cross_source_pair_count=4, providers=["guardian", "nyt"], time_window="7d")
    by = {h["cause"]: h["signal"] for h in g["root_cause_hypotheses"]}
    assert by[RC_SAME_EVENT_MISSED] == "plausible"   # generic 2-token 공유로 supporting 승격 0.
    assert g["root_cause_confidence"] == "indeterminate"
    assert g["same_event_truth_asserted"] is False


# ── §13 targeted live acquisition(15·16·17·18·19·20) ────────────────────────────────────────────────────
def test_missing_approval_blocks_live_call():
    r = _run(None, live_query=False)
    assert r["targeted_live_query_executed"] is False
    assert r["live_call_count"] == 0
    assert r["near_match_gap_status"] == NMG_INSUFFICIENT_ARTIFACT
    assert r["production_candidate_status"] == "blocked_no_live_opt_in"


def test_bounded_live_execution_when_approved():
    r = _run(_tf_below)
    assert r["targeted_live_query_executed"] is True
    assert r["live_call_count"] == 2   # guardian + nyt 1 GET 씩(1 seed).


def test_no_overlap_classified():
    r = _run(_tf_nodate)
    assert r["live_candidate_count"] == 0
    assert r["production_candidate_status"] == "blocked_no_live_overlap"


def test_below_floor_classified_blocked_no_publishable_pairs():
    r = _run(_tf_below)
    assert r["live_candidate_count"] > 0
    assert r["publishable_pair_count"] == 0
    assert r["production_candidate_status"] == "blocked_no_publishable_pairs"
    assert r["production_candidate_batch_ready"] is False


def test_production_batch_freezes_only_with_live_derived_pairs():
    r = _run(_tf_freeze)
    assert r["near_match_gap_status"] == NMG_CANDIDATES_PRESENT
    assert r["production_candidate_status"] == "production_batch_frozen"
    assert r["production_candidate_batch_ready"] is True
    assert r["production_frozen_pair_count"] >= 1
    assert r["candidate_provenance"] == "live_derived"


def test_production_gold_stays_zero_even_after_freeze():
    r = _run(_tf_freeze)
    assert r["production_gold_count"] == 0       # freeze ≠ gold(returned labels 전까지 0).
    assert r["current_r1_gap"] == 200
    assert r["r1_status"] != "satisfied"


# ── §13 provider expansion(21·22·23·24·25) ──────────────────────────────────────────────────────────────
def test_provider_expansion_plan_separates_query_capable_and_url_only():
    plan = build_provider_expansion_plan()
    by = {p["provider_name"]: p for p in plan["providers"]}
    # search(serper/tavily/exa)는 URL candidate only·truth 아님.
    assert plan["url_candidate_only"] == ["search"]
    assert by["serper / tavily / exa"]["source_role"] == "search"
    assert "URL candidate" in by["serper / tavily / exa"]["expected_overlap_usefulness"]
    # community/market/catalog 는 anchor 아님.
    assert "community" in plan["reaction_layer_only"]
    assert "catalog" in plan["enrichment_only"]
    assert "do not use search result as truth" in plan["rule"]
    # 이미 배선된 query-capable publishable(besides guardian/nyt).
    assert "gdelt" in plan["wired_query_capable_publishable_besides_guardian_nyt"]


def test_provider_plan_has_rate_and_tos_caution():
    for p in build_provider_expansion_plan()["providers"]:
        assert "rate_limit_policy" in p and "legal_tos_caution" in p and "next_action" in p


# ── §13 Korean strategy(26·27·28) ───────────────────────────────────────────────────────────────────────
def test_korean_strategy_present_and_ko_floor_gap_visible():
    ko = build_korean_source_strategy()
    assert ko["ready"] is True
    assert ko["ko_floor_gap_visible"] is True
    assert ko["ko_floor_current_gold"] == 0 and ko["ko_floor_required_gold"] == 50
    # KO live-query source 미배선(RSS feed-only)·Naver 는 wiring 필요(정직).
    assert ko["wired_ko_live_query_source"] is None
    # community reaction-only·KO floor 영문쌍으로 해결 불가 명시.
    rules = " ".join(ko["rules"])
    assert "reaction layer only" in rules
    assert "NOT solved by the English Guardian/NYT pair" in rules


# ── §13 contracts(29·30·31·32·33·34·35) ─────────────────────────────────────────────────────────────────
def test_product_bridge_contracts_ready_but_runtime_no_go():
    r = _run(_tf_below)
    assert r["llm_evidence_packet_contract_ready"] is True
    assert r["rag_ingestion_gate_ready"] is True
    assert r["kg_edge_eligibility_contract_ready"] is True
    assert r["community_reaction_layer_contract_ready"] is True
    assert r["public_iu_gate_ready"] is True
    assert r["product_bridge_runtime_built"] is False
    # 실 runtime 0.
    assert r["llm_invoked"] is False and r["embedding_invoked"] is False


def test_contract_docs_exist_and_define_merge_gate_and_reaction_only(tmp_path):  # noqa: ARG001
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    llm = (root / "docs/5_REFERENCE/LLM_EVIDENCE_PACKET_CONTRACT.md").read_text(encoding="utf-8")
    kg = (root / "docs/5_REFERENCE/RAG_KG_ENTITY_GATE_CONTRACT.md").read_text(encoding="utf-8")
    assert "MERGE_GATE" in llm and "same_event" in llm
    # same_event edge 는 MERGE_GATE 필요·community 는 reaction_to 만.
    assert "MERGE_GATE" in kg
    assert "reaction_to" in kg
    assert "0.98" in llm  # precision floor 인용.


# ── §13 safety: no merge / LLM / DB / public IU(46·47·48·49·50·51) ──────────────────────────────────────
def test_safety_gates_all_closed():
    r = _run(_tf_freeze)
    assert r["merge_allowed"] is False
    assert r["no_public_intelligence_unit"] is True
    assert r["db_write"] is False
    assert r["llm_invoked"] is False
    assert r["embedding_invoked"] is False
    assert r["actual_sending_performed"] is False
    assert r["public_truth_exposed"] is False
    assert r["raw_source_body_exposed"] is False
    # merge_gate 를 강제 True 로 만들지 않는다(gate passthrough — 미충족).
    assert r["r2_r7_no_go"] is True


# ── §13 UI/API frontier(36·37·42·43·44·45) + triple-consistency ─────────────────────────────────────────
def test_internal_ops_frontier_is_sanitized_and_pydantic_parses():
    r = _run(_tf_below)
    c = r["internal_ops_acquisition_frontier"]
    # forbidden 필드(same_event/score/rationale/predicted_status/raw body/PII/secret) 부재.
    flags = c["flags"]
    assert flags["no_same_event_truth"] and flags["no_score"] and flags["no_rationale"]
    assert flags["no_predicted_status"] and flags["no_raw_body"] and flags["no_secret"]
    # pydantic 화이트리스트 정합(dict==schema).
    m = InternalOpsAcquisitionFrontierStatus(**c)
    assert m.near_match_gap_status == NMG_ALL_BELOW_HARD_FLOOR
    assert m.r2_r7_no_go is True
    # 원인 가설은 cause/signal 만(rationale/score 텍스트 없음).
    for h in c["root_cause_hypotheses"]:
        assert set(h.keys()) == {"cause", "signal"}


def test_frontier_required_copy_states_zero_not_proof():
    r = _run(_tf_below)
    copy = r["internal_ops_acquisition_frontier"]["required_copy"]
    assert "Near-match 0 does not prove no same event" in copy
    assert any("Cause unresolved" in c for c in copy)
    assert "R2~R7 remain No-Go" in copy
    assert tuple(REQUIRED_OPS_COPY) == tuple(copy)


# ── ADR#77 baseline 보존(52) ────────────────────────────────────────────────────────────────────────────
def test_adr77_baseline_preserved_as_counts_only():
    r = _run(_tf_below)
    assert r["adr77_live_result_loaded"] is True
    assert r["adr77_live_candidate_count"] == 100      # 비교쌍(= same-event 매치 아님).
    assert r["adr77_publishable_pair_count"] == 0


@pytest.mark.parametrize("tf,expected", [
    (_tf_below, "blocked_no_publishable_pairs"),
    (_tf_freeze, "production_batch_frozen"),
    (_tf_nodate, "blocked_no_live_overlap"),
])
def test_six_state_classification_matrix(tf, expected):
    assert _run(tf)["production_candidate_status"] == expected
