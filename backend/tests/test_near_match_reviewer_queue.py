"""ADR#59 — near-match reviewer/gold queue 테스트(§9 시나리오 1-33 + 안전계약).

near positive(paraphrase) + hard negative 를 기존 labeling packet/gold/agreement 머신으로 보내는 운영 큐의
계약을 잠근다: predicted_status 숨김·merge 0·LLM 0·source role guard·labeler view bias 0·gold_ready 정직·
acquisition linkage·embedding/LLM No-Go.
"""
from __future__ import annotations

from backend.app.services.identity_human_labeling import (
    PACKET_ALLOWED_KEYS,
    ReviewerLabel,
)
from backend.app.tools.near_match_reviewer_queue import (
    EMBEDDING_LLM_ADJUDICATOR_INTERFACE,
    augment_agent_schema_with_reviewer_queue,
    build_gold_seed_report,
    build_near_match_reviewer_queue,
    build_reviewer_queue_acquisition_linkage,
    build_synthetic_hard_negative_candidates,
    resolve_queue_gold,
)
from backend.app.tools.source_overlap_discovery import (
    _rec,
    build_agent_orchestration_schema,
    build_captured_overlap_fixture,
    discover_overlap,
)


def _disc_captured() -> dict:
    return discover_overlap(build_captured_overlap_fixture())


def _queue(**kw) -> dict:
    return build_near_match_reviewer_queue(_disc_captured(), **kw)


def _rlabel(pair_id: str, reviewer_id: str, label: str, *, rnd: int = 1) -> ReviewerLabel:
    """테스트용 human reviewer label(실 reviewer 아님 — gold 경로 입증용·production gold 아님)."""
    return ReviewerLabel(
        pair_id=pair_id, reviewer_id=reviewer_id, review_round=rnd, label=label,
        label_confidence="high", reviewed_at="2026-06-23T00:00:00Z", language="en",
        source_type_left="article", source_type_right="article",
        title_left="t left", title_right="t right",
        observed_at_left="2026-06-22", observed_at_right="2026-06-22")


# ── near-match queue (1-10) ──────────────────────────────────────────────────────
def test_1_near_match_pair_becomes_reviewer_candidate():
    q = _queue()
    assert q["near_positive_count"] == 5            # captured fixture paraphrase 5 → reviewer 후보.
    assert q["packet_items"]                        # packet 생성됨.


def test_2_fingerprint_pair_separately_classified_not_in_queue():
    """fingerprint 정확일치(deterministic 검출)는 reviewer queue 와 분리 — near(adjudicator-zone)만 큐로."""
    disc = _disc_captured()
    q = build_near_match_reviewer_queue(disc)
    rep = build_gold_seed_report(disc, q)
    assert rep["fingerprint_overlap_count"] == 1    # 별도 카운트(deterministic).
    assert rep["near_match_count"] == 5             # 큐는 near 만(fingerprint pair 미포함).
    # wire verbatim pair(fingerprint)는 큐 pair_id 에 없음.
    assert q["near_positive_count"] == disc["adjudicator_zone_pairs"]


def test_3_hard_negative_generated():
    q = _queue(include_synthetic_hard_negatives=True)
    assert q["hard_negative_synthetic_count"] == 3
    buckets = {r["sampling_bucket"] for r in q["packet_rows"]}
    assert "hard_negative" in buckets


def test_4_5_6_non_publishable_community_market_catalog_rejected():
    """community/market/catalog anchor 는 큐에서 거부(source role guard·both_pub 필터)."""
    day = "2026-06-22"
    title_a = "Major port strike halts container shipping operations nationwide"
    title_b = "Major port strike halts container shipping operations today"
    for bad_type in ("community_signal", "structured_signal", "catalog_metadata"):
        recs = [
            _rec(record_type=bad_type, source_id="x", canonical_url="https://x.test/1",
                 title_or_label=title_a, published_at_or_observed_at=day),
            _rec(record_type="article_candidate", source_id="y", canonical_url="https://y.test/2",
                 title_or_label=title_b, published_at_or_observed_at=day),
        ]
        q = build_near_match_reviewer_queue(discover_overlap(recs))
        assert q["near_positive_count"] == 0        # 비-publishable anchor → 큐 진입 0.
        assert q["hard_negative_discovery_count"] == 0


def test_7_predicted_status_hidden():
    q = _queue(include_synthetic_hard_negatives=True)
    for r in q["packet_rows"]:
        assert "predicted_status" not in r and "score" not in r and "label" not in r
    for v in q["labeler_view"]:
        assert "predicted_status" not in v and "sampling_bucket" not in v


def test_8_9_10_no_merge_no_iu_no_llm():
    q = _queue(include_synthetic_hard_negatives=True)
    assert q["no_merge_without_gold"] is True
    assert q["no_merge_without_gate"] is True
    assert q["no_public_intelligence_unit"] is True
    assert q["llm_invoked"] is False
    assert EMBEDDING_LLM_ADJUDICATOR_INTERFACE["status"].startswith("No-Go")


# ── reviewer packet (11-18) ──────────────────────────────────────────────────────
def test_11_reviewer_packet_exportable():
    rep = build_gold_seed_report(_disc_captured(), _queue())
    assert rep["reviewer_packet_exportable"] is True


def test_12_labeler_facing_view_hides_prediction_and_bucket():
    q = _queue(include_synthetic_hard_negatives=True)
    for v in q["labeler_view"]:
        for forbidden in ("sampling_bucket", "predicted_status", "score", "label", "risk_tags"):
            assert forbidden not in v               # bias 차단(model 판정·stratum 미노출).
        assert "title_left" in v and "instructions" in v


def test_13_14_queue_size_and_bucket_distribution_reported():
    disc = _disc_captured()
    q = build_near_match_reviewer_queue(disc, include_synthetic_hard_negatives=True)
    rep = build_gold_seed_report(disc, q)
    assert rep["queue_size"] == 8                   # near 5 + synthetic hard 3.
    assert rep["bucket_distribution"].get("paraphrase") == 10   # 5 pair × 2 reviewer.
    assert rep["bucket_distribution"].get("hard_negative") == 6  # 3 pair × 2 reviewer.


def test_15_risk_tags_preserved_in_packet():
    q = _queue()
    near_rows = [r for r in q["packet_rows"] if r["sampling_bucket"] == "paraphrase"]
    assert near_rows
    for r in near_rows:
        assert "near_match_below_fingerprint" in r["risk_tags"]
        assert "paraphrase" in r["risk_tags"]


def test_16_uncertainty_preserved():
    disc = _disc_captured()
    rep = build_gold_seed_report(disc, build_near_match_reviewer_queue(disc))
    assert rep["uncertainty"]["measured_jaccard_count"] >= 1     # near 후보 측정 jaccard 보존.
    assert rep["uncertainty"]["max_title_token_jaccard"] is not None


def test_17_hard_negative_count_reported():
    disc = _disc_captured()
    q = build_near_match_reviewer_queue(disc, include_synthetic_hard_negatives=True)
    rep = build_gold_seed_report(disc, q)
    assert rep["hard_negative_count"] == 3
    assert rep["hard_negative_synthetic_count"] == 3
    assert rep["hard_negative_discovery_count"] == 0


def test_18_raw_body_not_included():
    q = _queue(include_synthetic_hard_negatives=True)
    rep = build_gold_seed_report(_disc_captured(), q)
    assert rep["raw_body_included"] is False
    for r in q["packet_rows"]:
        assert set(r) <= PACKET_ALLOWED_KEYS        # allowlist — body/content/author/raw 키 부재.
        for forbidden in ("body", "content", "raw_payload", "text", "author", "email"):
            assert forbidden not in r


# ── gold seed / agreement (19-23) ────────────────────────────────────────────────
def test_19_gold_ready_false_unless_labels():
    rep = build_gold_seed_report(_disc_captured(), _queue())
    assert rep["gold_ready"] is False               # 실 reviewer label 0 → gold_ready False(정직).
    assert rep["gold_pair_count"] == 0
    # 빈 label 입력 → resolve 도 gold 0.
    assert resolve_queue_gold([])["gold_ready"] is False


def test_20_reviewer_agreement_path():
    """2명 합의(same_event) → agreement_rate 1.0·gold 승격(reviewer agreement 경로 입증)."""
    labels = [_rlabel("nm:0-1", "rev_a", "same_event"), _rlabel("nm:0-1", "rev_b", "same_event")]
    res = resolve_queue_gold(labels)
    assert res["reviewer_agreement"]["agreement_rate"] == 1.0
    assert res["gold_count"] == 1
    assert res["gold_ready"] is True
    assert res["merge_allowed"] is False            # gold 여도 병합 0(불변).


def test_21_22_conflict_routes_to_adjudication_queue():
    """2명 상충(same vs different)·adjudication 없음 → gold 0·conflict adjudication queue 로."""
    labels = [_rlabel("nm:0-1", "rev_a", "same_event"), _rlabel("nm:0-1", "rev_b", "different_event")]
    res = resolve_queue_gold(labels)
    assert res["gold_count"] == 0
    assert res["gold_ready"] is False
    assert res["conflict_count"] == 1               # human-only adjudication queue 로.
    q = res["conflict_adjudication_queue"][0]
    assert q["pair_id"] == "nm:0-1"


def test_22b_human_adjudication_resolves_conflict_to_gold():
    """상충 + human adjudication(adjudicator_kind=human) → gold 승격(LLM-as-judge 금지)."""
    labels = [_rlabel("nm:0-1", "rev_a", "same_event"), _rlabel("nm:0-1", "rev_b", "different_event")]
    adj = {"nm:0-1": {"label": "same_event", "adjudicator_kind": "human", "adjudicated_by": "lead_x"}}
    res = resolve_queue_gold(labels, adjudications=adj)
    assert res["gold_count"] == 1
    assert res["gold_ready"] is True


def test_23_single_reviewer_insufficient_no_gold():
    res = resolve_queue_gold([_rlabel("nm:0-1", "rev_a", "same_event")])
    assert res["gold_count"] == 0                   # 단일 reviewer → insufficient(gold 아님).
    assert res["gold_ready"] is False


# ── false positive guard (24-28) ─────────────────────────────────────────────────
def test_24_date_window_required():
    """다른 날 publishable pair 는 high overlap 이어도 near 후보 아님(date-window 강제)."""
    title = "Major port strike halts container shipping operations nationwide"
    recs = [
        _rec(source_id="a", canonical_url="https://a.test/1", title_or_label=title,
             published_at_or_observed_at="2026-06-22"),
        _rec(source_id="b", canonical_url="https://b.test/2", title_or_label=title,
             published_at_or_observed_at="2026-06-25"),
    ]
    q = build_near_match_reviewer_queue(discover_overlap(recs))
    assert q["near_positive_count"] == 0


def test_25_source_role_compatibility_required():
    q = _queue(include_synthetic_hard_negatives=True)
    for r in q["packet_rows"]:
        assert r["source_type_left"] in ("article", "official")
        assert r["source_type_right"] in ("article", "official")


def test_26_title_overlap_threshold_enforced():
    """floor 미만 overlap publishable pair → near/hard 둘 다 후보 0(잡음 차단)."""
    recs = [
        _rec(source_id="a", canonical_url="https://a.test/1",
             title_or_label="Major port strike halts container shipping nationwide",
             published_at_or_observed_at="2026-06-22"),
        _rec(source_id="b", canonical_url="https://b.test/2",
             title_or_label="Sunny weather forecast brings clear skies weekend",
             published_at_or_observed_at="2026-06-22"),
    ]
    q = build_near_match_reviewer_queue(discover_overlap(recs))
    assert q["near_positive_count"] == 0 and q["hard_negative_discovery_count"] == 0


def test_27_canonical_domain_clue_preserved():
    q = _queue()
    for v in q["labeler_view"]:
        assert "canonical_url_left" in v and "canonical_url_right" in v


def test_28_hard_negative_sampling_works():
    syn = build_synthetic_hard_negative_candidates()
    assert len(syn) == 3
    for c in syn:
        assert c["risk_tags"] == ["hard_negative"]
        assert c["source_type_left"] == "article" and c["source_type_right"] == "article"
        assert "predicted_status" not in c          # 음성도 predicted 미포함.


# ── source acquisition linkage (29-33) ───────────────────────────────────────────
def test_29_30_31_acquisition_values_computed():
    disc = _disc_captured()
    q = build_near_match_reviewer_queue(disc)
    link = build_reviewer_queue_acquisition_linkage(disc, q)
    pairs = link["source_pair_acquisition"]
    assert pairs
    # near positive 있는 pair 는 yield/reviewer/gold value high.
    near_pairs = [p for p in pairs if p["near_match_yield_potential"] == "high"]
    assert near_pairs
    for p in near_pairs:
        assert p["reviewer_value"] == "high"
        assert p["gold_value"] == "high"
        assert p["paraphrase_risk"] == "high"
    # 모든 항목이 필수 acquisition field 보유.
    for p in pairs:
        for f in ("near_match_yield_potential", "reviewer_value", "gold_value",
                  "hard_negative_value", "source_pair_priority"):
            assert f in p


def test_32_next_fetch_plan_includes_pairs_and_topic_windows():
    disc = _disc_captured()
    link = build_reviewer_queue_acquisition_linkage(disc, build_near_match_reviewer_queue(disc))
    assert isinstance(link["next_fetch_plan"], str) and link["next_fetch_plan"]
    assert "topics" in link["topic_window_priority"]
    assert link["no_merge_without_gate"] is True


def test_33_agent_schema_includes_no_merge_without_gate():
    disc = _disc_captured()
    q = build_near_match_reviewer_queue(disc)
    rep = build_gold_seed_report(disc, q)
    link = build_reviewer_queue_acquisition_linkage(disc, q)
    schema = augment_agent_schema_with_reviewer_queue(
        build_agent_orchestration_schema(disc), q, rep, link)
    assert schema["no_merge_without_gate"] is True
    assert schema["llm_invoked"] is False
    assert schema["embedding_llm_adjudicator"]["status"].startswith("No-Go")
    assert schema["near_match_queue_priority"] == "high"
    assert schema["reviewer_packet_priority"] == "high"
    # base schema field 보존(보강이 덮어쓰지 않음).
    assert schema["no_public_intelligence_unit"] is True


# ── 안전계약 회귀(packet validate fail-loud·empty queue 안전) ─────────────────────
def test_empty_queue_is_safe():
    """near/hard 후보 0 → packet 빈 리스트·report exportable False(crash 0)."""
    recs = [_rec(source_id="a", canonical_url="https://a.test/1", title_or_label="solo headline only",
                 published_at_or_observed_at="2026-06-22")]
    disc = discover_overlap(recs)
    q = build_near_match_reviewer_queue(disc)
    rep = build_gold_seed_report(disc, q)
    assert q["packet_items"] == []
    assert rep["reviewer_packet_exportable"] is False
    assert rep["gold_ready"] is False


def test_packet_validation_runs_on_build():
    """build_near_match_reviewer_queue 는 validate_labeling_packet 를 통과한 packet 만 반환(verdict 누출 시 raise)."""
    q = _queue(include_synthetic_hard_negatives=True)
    # validate 가 build 내부에서 이미 실행됨 — 통과했으므로 packet_rows 존재.
    assert q["packet_rows"]
    for r in q["packet_rows"]:
        assert r["assignment_status"] == "assigned"


def test_dataset_source_provenance_sealed_against_summarize():
    """adversarial LOW-1 봉인: synthetic 후보가 summarize_packet_sampling 에서 live 로 오집계되지 않음(dataset_source 명시)."""
    from backend.app.services.identity_human_labeling import (
        SOURCE_LIVE,
        SOURCE_SYNTHETIC,
        summarize_packet_sampling,
    )
    disc = _disc_captured()    # real_fetch=False → captured fixture 후보는 synthetic_fixture.
    q = build_near_match_reviewer_queue(disc, include_synthetic_hard_negatives=True)
    for w in q["worksheet_rows"]:
        assert w["dataset_source"] in (SOURCE_LIVE, SOURCE_SYNTHETIC)
    summ = summarize_packet_sampling(q["worksheet_rows"])
    assert summ["live_vs_synthetic"][SOURCE_SYNTHETIC] == 8   # captured near 5 + synthetic hard 3.
    assert summ["live_vs_synthetic"][SOURCE_LIVE] == 0        # synthetic 이 live 표본 부풀리지 않음.


def test_dataset_source_live_when_real_fetch():
    """real_fetch=True discovery → 후보 dataset_source=live_derived(captured fixture 와 정직 구분)."""
    from backend.app.services.identity_human_labeling import SOURCE_LIVE
    from backend.app.tools.source_overlap_discovery import discover_overlap
    disc = discover_overlap(build_captured_overlap_fixture(), real_fetch=True)
    q = build_near_match_reviewer_queue(disc)
    assert q["worksheet_rows"]
    assert all(w["dataset_source"] == SOURCE_LIVE for w in q["worksheet_rows"])
