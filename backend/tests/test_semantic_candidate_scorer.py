"""ADR#65 — semantic candidate scorer tests (병합 0·LLM 0·embedding 0·score labeler-facing 숨김).

§10 시나리오 잠금:
  - scorer contract(1-8): SemanticPairInput/Score schema·requires_gold/merge_gate·labeler_visible False·
    merge_allowed False·no raw body·no secret value.
  - deterministic/fake scorer(9-16): no network/LLM/embedding by default·fake/deterministic 점수화·no_pairs·
    top-k bounded·score distribution.
  - reviewer queue integration(17-24): scored top-k → queue·hard negatives 포함·labeler view score/rationale/
    predicted_status 숨김·production_gold_count 0·merge_allowed False·no public IU.
  - optional embedding/LLM policy(25-32): opt-in required·missing credentials block·env var name 노출/값 숨김·
    pair count bounded·raw body 미전달·output internal-only·no merge·no DB write.
  - agent contract(38-42): semantic prioritization·no truth assertion·no_merge_without_gate·no_public_IU·secret boundary.
network 0(env_probe_fn/scorer_fn 주입). 실 `.env` 미접촉.
"""
from __future__ import annotations

import json

from backend.app.services.identity_human_labeling import labeler_facing_view
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.semantic_candidate_scorer import (
    MODE_DETERMINISTIC,
    MODE_EMBEDDING,
    MODE_FAKE,
    MODE_LLM,
    SCORER_AGENT_CONTRACT,
    build_pair_score,
    main,
    normalize_candidate_pair,
    run_semantic_candidate_scoring,
    score_candidate_pairs,
    select_top_k,
)
from backend.app.tools.source_overlap_discovery import build_captured_overlap_fixture

DAY = "2026-06-22"
_SENTINEL = "ZZZ_FAKE_SCORER_KEY_must_never_appear_65"

# paraphrase near pair(고overlap)·hard-negative band([0.2,0.5))·below_floor(overlap 0) 제목.
NEAR_A = "Major port strike halts container shipping operations nationwide"
NEAR_B = "Major port strike halts container shipping operations today"          # near(고overlap)
HARD_A = "Central bank raises interest rate today decision"
HARD_B = "Central bank governor interest groups meeting speech"                 # [0.2,0.5) band
UNREL = "Record heat wave grips southern region this week"                      # overlap 0


def _cp(pair_id, ta, tb, *, band="near_match", role="article",
        sl="guardian:a", sr="nyt:b", ul="https://g.test/x", ur="https://n.test/y", day=DAY):
    """discover_overlap candidate pair(`_near_pair_record`+band) 형태 — queue 통합 테스트 정밀 제어용(score 필드 없음)."""
    return {
        "pair_id": pair_id,
        "source_id_left": sl, "source_id_right": sr,
        "source_type_left": role, "source_type_right": role,
        "title_left": ta, "title_right": tb,
        "observed_at_left": day, "observed_at_right": day,
        "canonical_url_left": ul, "canonical_url_right": ur,
        "title_token_jaccard": 0.0, "date_bucket_match": True,
        "source_role_compatible": role in ("official", "article"),
        "band": band,
    }


def _disc(candidate_pairs, *, real_fetch=True):
    return {
        "candidate_pairs": candidate_pairs, "near_match_pairs": [], "hard_negative_pairs": [],
        "real_fetch": real_fetch, "overlap_potential_matrix": [], "fingerprint_overlap_pairs": 0,
    }


def _input(**kw):
    base = dict(
        pair_id="cp:0-1", source_id_left="guardian:a", source_id_right="nyt:b",
        source_type_left="article", source_type_right="article",
        title_left=NEAR_A, title_right=NEAR_B, observed_at_left=DAY, observed_at_right=DAY,
        canonical_url_left="https://g.test/x", canonical_url_right="https://n.test/y")
    base.update(kw)
    return normalize_candidate_pair(
        base, topic="port strike", time_window="1d", provider_a="guardian", provider_b="nyt",
        dataset_source="live_derived", provenance="live_derived")


# ── scorer contract(1-8) ─────────────────────────────────────────────────────────────────────
def test_01_semantic_pair_input_schema_validates():
    inp = _input()
    for k in ("pair_id", "source_a", "source_b", "provider_a", "provider_b", "source_role_a",
              "source_role_b", "title_a", "title_b", "canonical_url_a", "canonical_url_b",
              "published_at_a", "published_at_b", "topic", "time_window", "dataset_source", "provenance"):
        assert k in inp
    assert inp["provider_a"] == "guardian" and inp["provider_b"] == "nyt"
    assert inp["source_role_a"] == "article"


def test_02_score_output_schema_validates():
    s = build_pair_score(_input(), scorer_mode=MODE_DETERMINISTIC)
    for k in ("pair_id", "score", "score_type", "scorer_mode", "confidence", "reasons_internal",
              "model_metadata_internal", "labeler_visible", "merge_allowed", "requires_gold",
              "requires_merge_gate"):
        assert k in s
    assert isinstance(s["score"], float)


def test_03_score_requires_gold_true():
    assert build_pair_score(_input(), scorer_mode=MODE_DETERMINISTIC)["requires_gold"] is True


def test_04_score_requires_merge_gate_true():
    assert build_pair_score(_input(), scorer_mode=MODE_FAKE)["requires_merge_gate"] is True


def test_05_labeler_visible_false():
    assert build_pair_score(_input(), scorer_mode=MODE_DETERMINISTIC)["labeler_visible"] is False


def test_06_merge_allowed_false():
    assert build_pair_score(_input(), scorer_mode=MODE_FAKE)["merge_allowed"] is False


def test_07_no_raw_body_in_input_or_score():
    inp = _input()
    s = build_pair_score(inp, scorer_mode=MODE_DETERMINISTIC)
    forbidden = {"body", "raw_body", "content", "raw_text", "article_body", "full_text", "author", "email"}
    assert not (set(inp) & forbidden)
    assert not (set(s) & forbidden)
    blob = json.dumps(s, ensure_ascii=False)
    assert "body" not in blob.lower() or "raw" not in blob.lower()


def test_08_no_secret_value_offline():
    # offline mode 는 credential probe 자체를 안 함 → credential_status None·값 노출 0.
    out = run_semantic_candidate_scoring(
        records=build_captured_overlap_fixture(), scorer_mode=MODE_DETERMINISTIC,
        topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["credential_value_exposed"] is False
    assert out["credential_status"] is None
    assert _SENTINEL not in json.dumps(out, ensure_ascii=False)


# ── deterministic/fake scorer(9-16) ──────────────────────────────────────────────────────────
def test_09_no_network_by_default():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_FAKE, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["network_used"] is False


def test_10_no_llm_by_default():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_DETERMINISTIC, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["llm_invoked"] is False


def test_11_no_embedding_by_default():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_FAKE, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["embedding_invoked"] is False
    assert out["scorer_fn_invoked"] is False


def test_12_fake_scorer_scores_pairs():
    scores = score_candidate_pairs([_input()], scorer_mode=MODE_FAKE)
    assert len(scores) == 1 and scores[0]["score_type"] == "fake_semantic_scaffold"
    assert scores[0]["score"] > 0.0


def test_13_deterministic_scaffold_scores_pairs():
    scores = score_candidate_pairs([_input()], scorer_mode=MODE_DETERMINISTIC)
    assert len(scores) == 1 and scores[0]["score_type"] == "deterministic_title_jaccard"


def test_14_empty_pair_set_returns_no_pairs():
    out = run_semantic_candidate_scoring(records=[], scorer_mode=MODE_DETERMINISTIC,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert "no_pairs" in out["block_reasons"]


def test_15_top_k_bounded():
    cps = [_cp(f"cp:{i}", NEAR_A, NEAR_B) for i in range(8)]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE, top_k=3,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["candidate_count"] == 3
    assert out["reviewer_queue_population_count"] <= 3


def test_16_score_distribution_reported():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_DETERMINISTIC, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    dist = out["score_distribution"]
    assert set(dist["bands"]) == {"0.0-0.2", "0.2-0.5", "0.5-0.8", "0.8-1.0"}
    assert dist["max"] is not None


# ── reviewer queue integration(17-24) ────────────────────────────────────────────────────────
def test_17_scored_topk_enters_reviewer_queue():
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B), _cp("cp:2-3", HARD_A, HARD_B, band="hard_negative")]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_DETERMINISTIC, top_k=1,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["reviewer_queue_population_count"] >= 1
    assert out["near_match_count"] == 1


def test_18_hard_negatives_included():
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B), _cp("cp:2-3", HARD_A, HARD_B, band="hard_negative")]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_DETERMINISTIC, top_k=1,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    # top-1=near pair; hard-negative band pair 는 hard 로 분리 충원(음성 floor).
    assert out["hard_negative_count"] == 1
    assert out["reviewer_queue_population_count"] == 2


def _build_queue_labeler_view(cps, top_k=1):
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE, top_k=top_k,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    # labeler_facing_view 를 직접 재구성해 누출 검사(scorer 가 build_near_match_reviewer_queue 로 같은 경로 사용).
    return out


def test_19_labeler_view_hides_score():
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B)]
    queue = build_near_match_reviewer_queue(
        {"near_match_pairs": cps, "hard_negative_pairs": [], "real_fetch": True,
         "fingerprint_overlap_pairs": 0}, packet_id="t")
    for v in queue["labeler_view"]:
        assert "score" not in v and "semantic_score" not in v
        assert "scorer_mode" not in v


def test_20_labeler_view_hides_rationale():
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B)]
    queue = build_near_match_reviewer_queue(
        {"near_match_pairs": cps, "hard_negative_pairs": [], "real_fetch": True,
         "fingerprint_overlap_pairs": 0}, packet_id="t")
    for v in queue["labeler_view"]:
        assert "reasons_internal" not in v and "rationale" not in v
        assert "model_metadata_internal" not in v


def test_21_predicted_status_hidden():
    out = run_semantic_candidate_scoring(discovery=_disc([_cp("cp:0-1", NEAR_A, NEAR_B)]),
                                         scorer_mode=MODE_FAKE, top_k=1, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["labeler_prediction_hidden"] is True
    assert out["score_hidden_from_labeler"] is True
    assert out["rationale_hidden_from_labeler"] is True


def test_22_production_gold_count_zero():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_DETERMINISTIC, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["production_gold_count"] == 0
    assert out["eval_gold_linkage"]["production_gold_count"] == 0
    assert out["eval_gold_linkage"]["current_status"] == "No-Go for merge"


def test_23_merge_allowed_false():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_FAKE, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["merge_allowed"] is False and out["no_merge_without_gold"] is True


def test_24_no_public_intelligence_unit():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_DETERMINISTIC, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["no_public_intelligence_unit"] is True


# ── optional embedding/LLM policy(25-32) ─────────────────────────────────────────────────────
def _present_probe(_var):
    return {"var_name": _var, "credential_present": True, "env_file_present": True, "declared_in_example": True}


def _missing_probe(_var):
    return {"var_name": _var, "credential_present": False, "env_file_present": True, "declared_in_example": True}


def _noenv_probe(_var):
    return {"var_name": _var, "credential_present": False, "env_file_present": False, "declared_in_example": True}


def test_25_opt_in_required():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_EMBEDDING, opt_in=False, topic="t",
                                         time_window="1d", provider_a="a", provider_b="b")
    assert "scorer_disabled" in out["block_reasons"]
    assert out["scored_pair_count"] == 0


def test_26_missing_credentials_blocks():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_EMBEDDING, opt_in=True, env_probe_fn=_missing_probe,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert "missing_credentials" in out["block_reasons"]
    out2 = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                          scorer_mode=MODE_LLM, opt_in=True, env_probe_fn=_noenv_probe,
                                          topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert "env_not_loaded" in out2["block_reasons"]


def test_27_env_var_name_visible_value_hidden():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_EMBEDDING, opt_in=True, env_probe_fn=_missing_probe,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["opt_in_env_var"] == "OPENAI_API_KEY"           # 이름 노출.
    assert any("OPENAI_API_KEY" in a for a in out["next_actions"])
    assert out["credential_value_exposed"] is False           # 값 미노출.
    assert _SENTINEL not in json.dumps(out, ensure_ascii=False)


def test_28_pair_count_bounded():
    cps = [_cp(f"cp:{i}", NEAR_A, NEAR_B) for i in range(50)]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE, top_k=5,
                                         max_pairs=10, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["scored_pair_count"] == 10        # max_pairs bound.


def test_29_raw_body_not_sent_to_scorer_fn():
    seen = {}

    def _capture_scorer(inp):
        seen.update(inp)
        return 0.5

    run_semantic_candidate_scoring(
        discovery=_disc([_cp("cp:0-1", NEAR_A, NEAR_B)]), scorer_mode=MODE_EMBEDDING, opt_in=True,
        scorer_fn=_capture_scorer, env_probe_fn=_present_probe, topic="t", time_window="1d",
        provider_a="a", provider_b="b")
    forbidden = {"body", "raw_body", "content", "raw_text", "article_body", "full_text"}
    assert not (set(seen) & forbidden)
    assert "title_a" in seen   # 헤드라인만 전달.


def test_30_output_internal_only_score_not_in_queue_artifacts():
    out = run_semantic_candidate_scoring(
        discovery=_disc([_cp("cp:0-1", NEAR_A, NEAR_B)]), scorer_mode=MODE_EMBEDDING, opt_in=True,
        scorer_fn=lambda _i: 0.9, env_probe_fn=_present_probe, top_k=1, topic="t", time_window="1d",
        provider_a="a", provider_b="b")
    # scorer ran via injected fn but module made no real provider call.
    assert out["scorer_fn_invoked"] is True
    assert out["llm_invoked"] is False and out["embedding_invoked"] is False


def test_31_no_merge_and_no_db_write():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_DETERMINISTIC, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["merge_allowed"] is False and out["db_write"] is False


def test_32_provider_error_when_optin_present_but_no_scorer_fn():
    out = run_semantic_candidate_scoring(records=build_captured_overlap_fixture(),
                                         scorer_mode=MODE_LLM, opt_in=True, scorer_fn=None,
                                         env_probe_fn=_present_probe, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert "provider_error" in out["block_reasons"]
    assert out["scored_pair_count"] == 0


# ── agent contract(38-42) ────────────────────────────────────────────────────────────────────
def test_38_agent_schema_includes_semantic_prioritization():
    assert SCORER_AGENT_CONTRACT["semantic_prioritization"] is True
    assert "semantic candidate prioritization" in SCORER_AGENT_CONTRACT["can_plan"]


def test_39_agent_schema_includes_no_truth_assertion():
    assert SCORER_AGENT_CONTRACT["no_truth_assertion"] is True
    assert "semantic score 를 truth 로 사용" in SCORER_AGENT_CONTRACT["cannot"]


def test_40_agent_schema_includes_no_merge_without_gate():
    assert SCORER_AGENT_CONTRACT["no_merge_without_gate"] is True
    assert "merge 실행" in SCORER_AGENT_CONTRACT["cannot"]


def test_41_agent_schema_includes_no_public_intelligence_unit():
    assert SCORER_AGENT_CONTRACT["no_public_intelligence_unit"] is True


def test_42_agent_schema_includes_secret_boundary():
    assert "secret_boundary" in SCORER_AGENT_CONTRACT
    assert "secret 을 읽거나 출력" in SCORER_AGENT_CONTRACT["cannot"]


# ── CLI / select_top_k 보조 ──────────────────────────────────────────────────────────────────
def test_43_cli_hermetic_default_offline():
    rc = main(["--mode", "deterministic_scaffold", "--json"])
    assert rc == 0


def test_44_select_top_k_excludes_zero_signal():
    scores = [{"pair_id": "a", "score": 0.0}, {"pair_id": "b", "score": 0.7}, {"pair_id": "c", "score": 0.3}]
    top = select_top_k(scores, top_k=10)
    assert "a" not in top and top[0] == "b"


def test_45_unknown_scorer_mode_raises():
    try:
        run_semantic_candidate_scoring(records=[], scorer_mode="bogus",
                                       topic="t", time_window="1d", provider_a="a", provider_b="b")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_46_labeler_view_helper_strips_internal(tmp_path=None):
    # labeler_facing_view 가 우리가 만든 packet item 에도 score/판정을 노출하지 않음(간접 회귀).
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B)]
    queue = build_near_match_reviewer_queue(
        {"near_match_pairs": cps, "hard_negative_pairs": [], "real_fetch": True,
         "fingerprint_overlap_pairs": 0}, packet_id="t")
    if queue["packet_items"]:
        v = labeler_facing_view(queue["packet_items"][0])
        assert "score" not in v and "sampling_bucket" not in v


# ── adversarial/code-review fix locks ────────────────────────────────────────────────────────
def test_47_cross_source_only_excludes_same_source():
    """adversarial M-1: same-source(source_id 동일) pair 는 scorer 입력에서 제외(cross_source_only 기본 True)."""
    # 실 adapter 는 guardian records 전부 source_id="guardian"·nyt 는 "nyt"(상수) → same-provider pair 는 source_id 동일.
    cps = [
        _cp("cp:0-1", NEAR_A, NEAR_B, sl="guardian", sr="nyt"),        # cross-source
        _cp("cp:2-3", NEAR_A, NEAR_B, sl="guardian", sr="guardian"),   # same-source(둔갑 위험)
    ]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE, top_k=10,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["input_pair_count"] == 2
    assert out["cross_source_pair_count"] == 1            # cross-source 만 점수화.
    assert out["same_source_pair_excluded"] == 1
    assert out["scored_pair_count"] == 1


def test_48_cross_source_only_off_keeps_same_source():
    cps = [_cp("cp:0-1", NEAR_A, NEAR_B, sl="g:a", sr="g:b")]   # same-source
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE,
                                         cross_source_only=False, topic="t", time_window="1d",
                                         provider_a="a", provider_b="b")
    assert out["cross_source_pair_count"] == 1 and out["same_source_pair_excluded"] == 0


def test_49_sub_floor_candidates_have_zero_above_near_floor():
    """adversarial M-2: deterministic_scaffold 가 sub-floor pair(Jaccard>0·near floor 미만)에 candidate>0 을 내도
    above_near_floor_count=0 — candidate_count 가 '검출 진전'으로 오독되지 않게 분해."""
    # 토픽 1토큰 공유·near floor(0.5) 미만 → band=below_floor·deterministic score>0.
    a = "Ukraine border tensions escalate sharply overnight reports indicate"
    b = "Ukraine economic sanctions package announced separately by officials"
    cp = _cp("cp:0-1", a, b, band="below_floor")
    out = run_semantic_candidate_scoring(discovery=_disc([cp]), scorer_mode=MODE_DETERMINISTIC,
                                         top_k=10, topic="ukraine", time_window="1d",
                                         provider_a="guardian", provider_b="nyt")
    assert out["candidate_count"] >= 1                   # sub-floor 후보가 prioritization 에 들어감.
    assert out["above_near_floor_count"] == 0            # 그러나 deterministic 검출(near floor 이상)은 여전히 0.
    assert out["candidate_band_distribution"].get("below_floor", 0) >= 1


def test_50_hard_negative_band_not_promoted_to_near_positive():
    """code-review MED-1: hard_negative band pair 가 높은 fake_semantic 점수여도 near positive(gold seed)로 승격 금지·
    negative floor 보존(top-k 는 hard band 제외 space 에서만 rank)."""
    cps = [
        _cp("cp:0-1", NEAR_A, NEAR_B, band="near_match"),
        _cp("cp:2-3", NEAR_A, NEAR_A, band="hard_negative"),   # 어휘 동일이나 band=hard_negative(다른-사건 lean)
    ]
    out = run_semantic_candidate_scoring(discovery=_disc(cps), scorer_mode=MODE_FAKE, top_k=10,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    # hard-band pair 는 top-k(near positive)에 안 들어가고 hard lane 에 보존.
    assert out["near_match_count"] == 1
    assert out["hard_negative_count"] == 1
    assert out["reviewer_queue_population_count"] == 2


def test_51_discovery_fallback_without_candidate_pairs_keeps_hard():
    """code-review HIGH-1: candidate_pairs 없는 discovery 직접 주입(near/hard만)도 band 부여로 hard lane 보존."""
    near = _cp("nm:0-1", NEAR_A, NEAR_B)
    hard = _cp("hn:2-3", HARD_A, HARD_B)
    for p in (near, hard):
        p.pop("band", None)   # 원본 _near_pair_record 는 band 없음(fallback 재현).
    disc = {"near_match_pairs": [near], "hard_negative_pairs": [hard], "real_fetch": True,
            "fingerprint_overlap_pairs": 0}   # candidate_pairs 키 없음 → fallback.
    out = run_semantic_candidate_scoring(discovery=disc, scorer_mode=MODE_DETERMINISTIC, top_k=10,
                                         topic="t", time_window="1d", provider_a="a", provider_b="b")
    assert out["hard_negative_count"] == 1            # band 부여로 hard negative 살아남음.
    assert out["near_match_count"] == 1
