"""ADR#60 — targeted same-event acquisition → reviewer/gold operating readiness 테스트(시나리오 1-49 +
실 fetch provenance + adversarial 음성 가드 M1/M2).

targeted acquisition(source-pair·topic·time-window) → near-match reviewer/gold queue 운영 경로의 계약을 잠근다:
정직한 no_candidate/block_reason·predicted_status 숨김·merge 0·LLM 0·gold path 검증(production gold 0)·hard
negative 균형·dataset_source 봉인·acquisition linkage·Agent No-Go. 실 near-match 후보는 여전히 0(fixture=경로 입증).
음성 가드(M1/M2): synthetic↔live 봉인을 코드로 강제·GDELT blocked block_reason·gold_ready False·verify 계산값 입증.
"""
from __future__ import annotations

from backend.app.services.identity_human_labeling import SOURCE_LIVE, SOURCE_SYNTHETIC
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)
from backend.app.tools.targeted_same_event_acquisition import (
    build_provider_capability_matrix,
    build_reviewer_operating_checklist,
    build_targeted_acquisition_plan,
    build_targeted_same_event_fixture,
    run_targeted_acquisition,
    run_targeted_same_event_operating_readiness,
    simulate_gold_calibration,
)


def _run(**kw) -> dict:
    """기본 fixture(synthetic·network 0) 운영 readiness."""
    return run_targeted_same_event_operating_readiness(**kw)


def _rss_xml(title: str, link: str, pub: str = "Mon, 22 Jun 2026 10:00:00 GMT") -> str:
    return (f'<rss><channel><item><title>{title}</title><link>{link}</link>'
            f'<pubDate>{pub}</pubDate></item></channel></rss>')


# ── acquisition-linked queue (1-10) ───────────────────────────────────────────────
def test_1_plan_produces_candidate_inputs():
    plan = build_targeted_acquisition_plan(provider="fixture")
    assert plan["source_pair_plan"]                 # 같은 보도권 다출처 조합.
    assert plan["topic"] and plan["time_window"]
    assert plan["no_merge_without_gate"] is True


def test_2_candidate_inputs_become_reviewer_queue():
    out = _run()
    assert out["report"]["candidate_count"] > 0
    assert out["queue"]["packet_items"]             # discover → queue 배선.


def test_3_near_positive_count_reported():
    assert _run()["report"]["near_positive_count"] == 2   # 검증된 band(paraphrase 0.545).


def test_4_hard_negative_count_reported():
    assert _run()["report"]["hard_negative_count"] == 3   # 같은 주제·다른 사건 0.31~0.33.


def test_5_fingerprint_overlap_count_reported():
    assert _run()["report"]["fingerprint_overlap_count"] == 1   # wire verbatim(deterministic 검출).


def test_6_empty_acquisition_honest_no_candidate():
    """후보 0 → 정직한 block_reason(no_candidate 을 모델 실패로 뭉뚱그리지 않음)."""
    out = _run(records=[])
    assert out["report"]["candidate_count"] == 0
    assert out["report"]["block_reason"] == "insufficient_records"
    assert out["report"]["reviewer_packet_exportable"] is False


def test_7_provider_blocked_honest_block_reason():
    """실 RSS fetch 가 0건 → block_reason 정직 노출·real_fetch True(fixture 위장 0)."""
    out = _run(provider="rss", rss_transport=lambda sid, ep: None)
    assert out["report"]["real_fetch"] is True
    assert out["report"]["block_reason"] == "rss_no_records"
    assert out["report"]["candidate_count"] == 0
    assert out["report"]["dataset_source"] == SOURCE_LIVE   # 실 시도 — synthetic 위장 금지.


def test_8_no_raw_body_stored():
    from backend.app.services.identity_human_labeling import PACKET_ALLOWED_KEYS
    q = _run(include_synthetic_hard_negatives=True)["queue"]
    for r in q["packet_rows"]:
        assert set(r) <= PACKET_ALLOWED_KEYS
        for forbidden in ("body", "content", "raw_payload", "text", "author", "email"):
            assert forbidden not in r


def test_9_no_merge():
    rep = _run()["report"]
    assert rep["merge_allowed"] is False
    assert rep["no_merge_without_gold"] is True


def test_10_no_llm():
    out = _run()
    assert out["report"]["llm_invoked"] is False
    assert out["agent_schema"]["embedding_llm_adjudicator"]["status"].startswith("No-Go")


def test_real_fetch_live_derived_from_rss_transport():
    """실 RSS fetch(transport 주입) 가 paraphrase 후보 생성 → dataset_source=live_derived(fixture 와 정직 구분)."""
    wire = "Federal Reserve raises benchmark interest rate by quarter point"
    para = "Federal Reserve raises benchmark interest rate by 25 basis points"
    xml = {
        "bbc": _rss_xml(wire, "https://bbc.test/1"),
        "aljazeera": _rss_xml(para, "https://aljazeera.test/2"),
        "the_verge": None, "techcrunch": None,
    }
    out = _run(provider="rss", rss_transport=lambda sid, ep: xml.get(sid))
    rep = out["report"]
    assert rep["real_fetch"] is True
    assert rep["dataset_source"] == SOURCE_LIVE
    assert rep["near_positive_count"] >= 1          # 실 fetch paraphrase → near 후보.
    assert all(w["dataset_source"] == SOURCE_LIVE for w in out["queue"]["worksheet_rows"])


# ── reviewer operating packet (11-20) ─────────────────────────────────────────────
def test_11_packet_exportable():
    assert _run()["reviewer_operating_checklist"]["assignment_count"] > 0
    assert _run()["report"]["reviewer_packet_exportable"] is True


def test_12_packet_id_present():
    assert _run()["reviewer_operating_checklist"]["packet_id"] == "targeted_near_match_pkt"


def test_13_dataset_source_present():
    chk = _run()["reviewer_operating_checklist"]
    assert chk["dataset_source"] in (SOURCE_LIVE, SOURCE_SYNTHETIC)


def test_14_hidden_prediction_verified():
    assert _run(include_synthetic_hard_negatives=True)[
        "reviewer_operating_checklist"]["hidden_prediction_verified"] is True


def test_15_raw_body_absent_verified():
    assert _run(include_synthetic_hard_negatives=True)[
        "reviewer_operating_checklist"]["raw_body_absent_verified"] is True


def test_16_reviewer_instructions_present():
    chk = _run()["reviewer_operating_checklist"]
    assert "모델 예측은 보이지 않는다" in chk["reviewer_instruction"]
    assert "anchor" in chk["reviewer_instruction"]


def test_17_allowed_labels_present():
    assert _run()["reviewer_operating_checklist"]["allowed_labels"] == [
        "ambiguous", "different_event", "insufficient", "same_event"]


def test_18_conflict_policy_present():
    assert "conflict" in _run()["reviewer_operating_checklist"]["conflict_policy"]


def test_19_agreement_policy_present():
    assert "agreed" in _run()["reviewer_operating_checklist"]["agreement_policy"]


def test_20_merge_policy_prohibited_until_gate():
    assert _run()["reviewer_operating_checklist"]["merge_policy"].startswith("prohibited until MERGE_GATE")


# ── gold calibration simulation (21-27) ───────────────────────────────────────────
def test_21_unanimous_same_becomes_gold():
    sim = simulate_gold_calibration()
    assert "unanimous_same" in sim["scenarios"]
    assert sim["simulated_gold_count"] >= 1


def test_22_unanimous_different_becomes_gold():
    sim = simulate_gold_calibration()
    assert "unanimous_different" in sim["scenarios"]
    assert sim["simulated_gold_count"] == 3         # same + different + adjudicated.


def test_23_single_reviewer_insufficient():
    assert simulate_gold_calibration()["insufficient_count"] == 1


def test_24_conflict_creates_adjudication_queue():
    assert simulate_gold_calibration()["conflict_count"] == 1


def test_25_human_adjudication_resolves():
    sim = simulate_gold_calibration()
    assert "human_adjudicated" in sim["scenarios"]
    assert sim["path_verified"] is True             # adjudicated → gold 경로 포함.


def test_26_production_gold_count_zero():
    sim = simulate_gold_calibration()
    assert sim["production_gold_count"] == 0         # 전부 synthetic_fixture(실 gold 0).
    assert sim["dataset_source"] == SOURCE_SYNTHETIC


def test_27_merge_allowed_false_in_sim():
    assert simulate_gold_calibration()["merge_allowed"] is False


# ── false positive / hard negative (28-32) ────────────────────────────────────────
def test_28_hard_negative_included():
    out = _run()
    assert out["queue"]["hard_negative_discovery_count"] == 3   # discovery-derived(measured band).


def test_29_hard_negative_dataset_source_explicit():
    out = _run()
    hard_rows = [w for w in out["queue"]["worksheet_rows"] if "hard_negative" in w["risk_tags"]]
    assert hard_rows
    for w in hard_rows:
        assert w["dataset_source"] in (SOURCE_LIVE, SOURCE_SYNTHETIC)


def test_30_synthetic_hard_negative_not_live():
    """fixture(real_fetch=False) + synthetic hard negative → live 표본 0(synthetic 이 live 부풀리기 0)."""
    from backend.app.services.identity_human_labeling import summarize_packet_sampling
    out = _run(include_synthetic_hard_negatives=True)
    summ = summarize_packet_sampling(out["queue"]["worksheet_rows"])
    assert summ["live_vs_synthetic"][SOURCE_LIVE] == 0
    assert summ["live_vs_synthetic"][SOURCE_SYNTHETIC] == 8   # near 2 + hard_disc 3 + hard_syn 3.


def test_31_near_positive_not_auto_labeled():
    out = _run()
    near_rows = [w for w in out["queue"]["worksheet_rows"] if "paraphrase" in w["risk_tags"]]
    assert near_rows
    for w in near_rows:
        assert w["label"] == "unlabeled"            # reviewer 가 채움(자동 라벨 0).
    for r in out["queue"]["packet_rows"]:
        assert "label" not in r and "predicted_status" not in r


def test_32_hard_negative_not_auto_labeled():
    out = _run()
    hard_rows = [w for w in out["queue"]["worksheet_rows"] if "hard_negative" in w["risk_tags"]]
    assert hard_rows
    for w in hard_rows:
        assert w["label"] == "unlabeled"            # 음성도 reviewer 가 확인(다른 사건 단정 0).


# ── source acquisition linkage (33-38) ────────────────────────────────────────────
def test_33_expected_near_match_yield():
    assert _run()["acquisition_linkage"]["expected_near_match_yield"] == 2


def test_34_expected_gold_value():
    assert _run()["acquisition_linkage"]["expected_gold_value"] == "high"   # near>0 → gold seed.


def test_35_expected_reviewer_load():
    assert _run()["acquisition_linkage"]["expected_reviewer_load"] == 10    # (near 2+hard 3)×2 reviewer.


def test_36_source_pair_priority():
    link = _run()["acquisition_linkage"]
    assert link["source_pair_acquisition"]
    for p in link["source_pair_acquisition"]:
        assert "source_pair_priority" in p


def test_37_next_fetch_plan_present():
    assert isinstance(_run()["report"]["next_fetch_plan"], str) and _run()["report"]["next_fetch_plan"]


def test_38_fallback_plan_present():
    assert _run()["acquisition_linkage"]["fallback_plan"]


# ── Agent contract (39-43) ────────────────────────────────────────────────────────
def test_39_agent_schema_reviewer_packet_priority():
    assert _run()["agent_schema"]["reviewer_packet_priority"] == "high"


def test_40_agent_schema_no_merge_without_gate():
    assert _run()["agent_schema"]["no_merge_without_gate"] is True


def test_41_agent_schema_no_public_iu():
    assert _run()["agent_schema"]["no_public_intelligence_unit"] is True


def test_42_llm_not_invoked():
    assert _run()["agent_schema"]["llm_invoked"] is False


def test_43_embedding_no_go_maintained():
    schema = _run()["agent_schema"]
    assert schema["embedding_llm_adjudicator"]["status"].startswith("No-Go")
    assert "같은 사건 확정" in schema["agent_cannot"]
    assert "merge 실행" in schema["agent_cannot"]


# ── regression (44-49) ────────────────────────────────────────────────────────────
def test_44_adr59_queue_behavior_preserved():
    """captured fixture(ADR#59) 재사용 시 near_positive_count==5 불변(orchestrator 가 ADR#59 동작 안 깸)."""
    out = _run(records=build_captured_overlap_fixture())
    assert out["report"]["near_positive_count"] == 5
    assert out["report"]["fingerprint_overlap_count"] == 1


def test_45_adr58_acquisition_capability_preserved():
    """provider capability matrix 가 ADR#58 현실 반영: GDELT topic query 가능하나 high risk·RSS topic 불가."""
    m = build_provider_capability_matrix()["providers"]
    assert m["gdelt"]["topic_query"] is True and m["gdelt"]["rate_limit_risk"] == "high"
    assert m["rss"]["topic_query"] is False and m["rss"]["auth"] == "none"


def test_46_adr57_overlap_decomposition_preserved():
    """discover_overlap 가 fixture 를 fingerprint/near/hard 로 분해(ADR#57 입도 불변)."""
    disc = discover_overlap(build_targeted_same_event_fixture())
    assert disc["fingerprint_overlap_pairs"] == 1
    assert disc["near_match_below_fingerprint_pairs"] == 2
    assert disc["hard_negative_band_pairs"] == 3
    assert disc["no_auto_merge"] is True


def test_47_order_invariance():
    """record 순서를 바꿔도 overlap 분해 동일(order-invariant·결정론)."""
    recs = build_targeted_same_event_fixture()
    a = run_targeted_acquisition(build_targeted_acquisition_plan(), records=recs)["discovery"]
    b = run_targeted_acquisition(
        build_targeted_acquisition_plan(), records=list(reversed(recs)))["discovery"]
    for k in ("fingerprint_overlap_pairs", "near_match_below_fingerprint_pairs",
              "hard_negative_band_pairs"):
        assert a[k] == b[k]


def test_48_community_anchor_rejected():
    """community 반응 record 는 anchor 금지(source role guard) — near/hard 후보로 진입 0."""
    out = _run()
    for w in out["queue"]["worksheet_rows"]:
        assert w["source_type_left"] in ("article", "official")
        assert w["source_type_right"] in ("article", "official")


def test_49_acquisition_run_id_deterministic():
    """같은 입력 → 같은 run_id(timestamp 아님·재현 가능)."""
    a = _run()["report"]["acquisition_run_id"]
    b = _run()["report"]["acquisition_run_id"]
    assert a == b and a.startswith("tsea:")


# ── adversarial 음성 가드(MEDIUM-1/2 — honesty 불변을 코드로 잠금) ─────────────────────────────────────
def test_m1_synthetic_fixture_cannot_be_stamped_live():
    """MEDIUM-1: synthetic fixture record 는 real_fetch=True 여도 live_derived 도장 불가(코드 강제·call discipline 아님)."""
    recs = build_targeted_same_event_fixture()
    out = run_targeted_same_event_operating_readiness(records=recs, real_fetch=True)
    assert out["report"]["real_fetch"] is False                 # 강제 다운그레이드.
    assert out["report"]["dataset_source"] == SOURCE_SYNTHETIC
    for w in out["queue"]["worksheet_rows"]:
        assert w["dataset_source"] == SOURCE_SYNTHETIC           # synthetic 이 live 표본 부풀리기 0.


def test_m1b_non_fixture_records_honor_real_fetch_flag():
    """대조: marker 없는 record 는 real_fetch 플래그를 그대로 따른다(가드가 fixture 만 표적)."""
    recs = build_captured_overlap_fixture()                     # ADR#57 fixture — marker 없음.
    out = run_targeted_same_event_operating_readiness(records=recs, real_fetch=True)
    assert out["report"]["real_fetch"] is True
    assert out["report"]["dataset_source"] == SOURCE_LIVE


def test_m2b_gdelt_blocked_block_reason_honest():
    """MEDIUM-2: 실 GDELT fetch 가 막히면(429/cooldown/host) block_reason 정직·real_fetch True·후보 0(silent success 0)."""
    out = run_targeted_same_event_operating_readiness(
        provider="gdelt", gdelt_transport=lambda url: "You have exceeded your limit requests")
    rep = out["report"]
    assert rep["real_fetch"] is True
    assert rep["block_reason"] is not None
    assert rep["candidate_count"] == 0
    assert rep["dataset_source"] == SOURCE_LIVE                  # 실 시도 — synthetic 위장 금지.


def test_m2c_gold_ready_false_without_real_gold():
    """MEDIUM-2: 실 gold 0 이면 gold_ready False(packet 있어도·synthetic hard negative 있어도)."""
    assert _run()["report"]["gold_ready"] is False
    assert _run(include_synthetic_hard_negatives=True)["report"]["gold_ready"] is False


def test_m2d_checklist_verify_is_computed_not_hardcoded():
    """MEDIUM-2: hidden_prediction/raw_body_absent verify 가 위반 입력에서 False(하드코딩 True 아님)."""
    poisoned = {
        "queue_pair_ids": ["x"],
        "labeler_view": [{"pair_id": "x", "predicted_status": "likely_same_event"}],   # verdict 누출.
        "packet_rows": [{"pair_id": "x", "body": "raw text leak"}],                     # raw body 누출.
    }
    chk = build_reviewer_operating_checklist(poisoned, dataset_source=SOURCE_SYNTHETIC)
    assert chk["hidden_prediction_verified"] is False
    assert chk["raw_body_absent_verified"] is False


def test_m2e_real_provider_without_fetch_substitutes_fixture_honestly():
    """code-review: rss/gdelt 요청이나 transport/live_network 없음 → fixture 대체를 block_reason 으로 정직 노출(masking 0)."""
    out = run_targeted_same_event_operating_readiness(provider="rss")   # transport·live_network 없음.
    rep = out["report"]
    assert rep["real_fetch"] is False
    assert rep["dataset_source"] == SOURCE_SYNTHETIC
    assert rep["block_reason"] == "real_fetch_not_attempted_fixture_substituted"


def test_m3_fixture_topic_label_consistent_with_fixture():
    """code-review: fixture provider 는 report.topic 이 실 fixture 내용과 일치(임의 --topic 라벨 오표기 차단)."""
    out = run_targeted_same_event_operating_readiness(provider="fixture", topic="some unrelated topic")
    assert out["report"]["topic_window"] == "central bank rate decision"
