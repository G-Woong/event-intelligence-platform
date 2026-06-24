from __future__ import annotations

"""Labeling packet generator / sampling report / reviewer assignment 단위 (ADR#46, R-GoldSamplingBias·R-ReviewerAgreement).

live-derived 워크시트 → bucket 샘플링 → reviewer ≥N 배정 → predicted_status/score/reason **차폐**(bias 0) → packet
JSONL + sampling deficit/표본 floor report 를 잠근다. 자동 병합 0·raw body/PII 차단·gold 0(라벨 전). 실 reviewer/
충원/대표성은 아직 0(부분진전).
"""

import json
from pathlib import Path

import pytest

from backend.app.services.identity_human_labeling import (
    ASSIGN_ASSIGNED,
    CANDIDATE_BUCKET_TARGETS,
    CANDIDATE_BUCKETS,
    DEFAULT_REVIEWERS_PER_PAIR,
    REVIEWER_HUMAN,
    SOURCE_LIVE,
    SOURCE_SYNTHETIC,
    AGREE_CONFLICT,
    LabelingPacketItem,
    ReviewerLabel,
    adjudication_queue_from_resolved,
    assign_candidate_bucket,
    assign_reviewer_packet,
    build_labeling_packet,
    estimate_sample_floor_for_fpr,
    estimate_sample_floor_for_precision,
    generate_labeling_protocol_report,
    generate_packet_ops_report,
    labeler_facing_view,
    load_reviewer_labels,
    packet_item_to_dict,
    resolve_gold_from_reviewers,
    resolved_to_gold_pairs,
    summarize_packet_sampling,
    validate_labeling_packet,
    write_labeling_packet_jsonl,
)

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identity_labeling_candidates.sample.jsonl"
_REVIEWERS = ["reviewer-a", "reviewer-b", "reviewer-c"]


def _candidates() -> list[dict]:
    rows: list[dict] = []
    for line in _FIXTURE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        rows.append(json.loads(line))
    return rows


def _ws(**kw) -> dict:
    base = {
        "pair_id": "p1", "language": "en", "source_type_left": "article", "source_type_right": "article",
        "title_left": "Federal Reserve raises benchmark interest rates today",
        "title_right": "Fed lifts benchmark rate in June meeting",
        "observed_at_left": "2026-06-24T09:00:00Z", "observed_at_right": "2026-06-24T10:00:00Z",
        "predicted_status": "likely_same_event", "score": 0.9, "reason": "high_sim_near_date_publishable",
        "risk_tags": [], "dataset_source": SOURCE_SYNTHETIC,
    }
    base.update(kw)
    return base


# ── 1. packet schema / build ─────────────────────────────────────────────────────────
def test_build_packet_pairs_times_reviewers():
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=2)
    # 16 후보 전부 target 미만 → 전부 선택. 16 pair × 2 reviewer = 32 item.
    assert len(items) == 32
    assert all(isinstance(i, LabelingPacketItem) for i in items)
    assert all(i.packet_id == "pkt-1" for i in items)
    assert all(i.assignment_status == ASSIGN_ASSIGNED for i in items)


def test_each_pair_gets_distinct_reviewers():
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=2)
    by_pair: dict[str, set[str]] = {}
    for it in items:
        by_pair.setdefault(it.pair_id, set()).add(it.reviewer_id)
    assert all(len(rs) == 2 for rs in by_pair.values())   # 동일 pair 2명(distinct)


def test_deterministic_packet_output():
    rows = _candidates()
    a = [packet_item_to_dict(i) for i in build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)]
    b = [packet_item_to_dict(i) for i in build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)]
    assert a == b


def test_single_reviewer_allowed_but_insufficient_downstream():
    # reviewers_per_pair=1 → 1명 배정(가능). resolve 단계에서 insufficient(gold 아님)는 별도 reviewer 테스트가 잠금.
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=1)
    by_pair: dict[str, set[str]] = {}
    for it in items:
        by_pair.setdefault(it.pair_id, set()).add(it.reviewer_id)
    assert all(len(rs) == 1 for rs in by_pair.values())


def test_assign_reviewer_packet_needs_enough_distinct_reviewers():
    rows = _candidates()
    sel = [("ambiguous_predicted", rows[2])]
    with pytest.raises(ValueError):
        assign_reviewer_packet(sel, packet_id="pkt-1", reviewers=["only-one"], reviewers_per_pair=2)
    # 중복 reviewer id 는 distinct dedup 후 부족으로 거부.
    with pytest.raises(ValueError):
        assign_reviewer_packet(sel, packet_id="pkt-1", reviewers=["a", "a"], reviewers_per_pair=2)


# ── 2. candidate bucket 배정 ─────────────────────────────────────────────────────────
def test_assign_candidate_bucket_predicted_and_guards():
    b = assign_candidate_bucket
    assert b(predicted_status="likely_same_event", reason="high_sim_near_date_publishable",
             language="en", source_type_left="article", source_type_right="article", risk_tags=()) \
        == "official_news_positive"
    assert b(predicted_status="ambiguous", reason="borderline", language="en",
             source_type_left="article", source_type_right="article", risk_tags=()) == "ambiguous_predicted"
    assert b(predicted_status="likely_same_event", reason="x", language="ko",
             source_type_left="official", source_type_right="official", risk_tags=()) == "ko_same_event_candidate"
    assert b(predicted_status="insufficient_features", reason="non_publishable_role", language="en",
             source_type_left="community", source_type_right="community", risk_tags=()) == "community_guard"
    assert b(predicted_status="insufficient_features", reason="non_publishable_role", language="en",
             source_type_left="market", source_type_right="market", risk_tags=()) == "market_guard"
    assert b(predicted_status="insufficient_features", reason="non_publishable_role", language="en",
             source_type_left="catalog", source_type_right="catalog", risk_tags=()) == "catalog_guard"
    assert b(predicted_status="insufficient_features", reason="unknown_source_type_fail_closed", language="en",
             source_type_left="unknown", source_type_right="article", risk_tags=()) == "unknown_guard"


def test_fixture_covers_all_buckets_no_unclassified():
    rows = _candidates()
    rep = summarize_packet_sampling(rows)
    assert rep["unclassified"] == 0
    for b in CANDIDATE_BUCKETS:
        assert rep["total_by_bucket"][b] >= 1, f"bucket {b} uncovered"


def test_live_signal_market_candidate_enters_packet(tmp_path):
    # ADR#46 adversarial HIGH 회귀: 라이브 evidence 는 market 을 'signal' 로 내보낸다. export 정규화
    # (_to_eval_source_type: signal→market)를 거친 뒤 market 후보가 market_guard 로 라우팅되고 build→write→
    # validate 를 통과하는지 — 즉 "라이브 market 후보가 packet 에 진입조차 못 한다"는 결함이 닫혔는지 잠근다.
    from backend.app.tools.export_identity_eval_pairs import _to_eval_source_type
    raw = _ws(pair_id="sig01", source_type_left="signal", source_type_right="signal",
              predicted_status="insufficient_features", reason="non_publishable_role",
              title_left="USD/KRW intraday move", title_right="USD/KRW intraday move")
    # export 경계 정규화 적용(라이브 collect_adjudication_eval_pairs 가 하는 변환).
    raw["source_type_left"] = _to_eval_source_type(raw["source_type_left"])
    raw["source_type_right"] = _to_eval_source_type(raw["source_type_right"])
    assert raw["source_type_left"] == "market"
    items = build_labeling_packet([raw], packet_id="pkt-sig", reviewers=_REVIEWERS, reviewers_per_pair=2)
    assert all(it.sampling_bucket == "market_guard" for it in items)
    p = tmp_path / "sig.jsonl"
    assert write_labeling_packet_jsonl(items, p) == 2     # market_guard packet 이 기록 가능(거부 0)


# ── 3. no-bias: model 판정 차폐 ──────────────────────────────────────────────────────
def test_packet_dict_has_no_model_verdict():
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)
    for it in items:
        d = packet_item_to_dict(it)
        for forbidden in ("predicted_status", "score", "reason", "label"):
            assert forbidden not in d


def test_labeler_view_strips_bucket_and_verdict():
    rows = _candidates()
    it = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)[0]
    lv = labeler_facing_view(it)
    for forbidden in ("sampling_bucket", "predicted_status", "score", "reason", "label", "assignment_status"):
        assert forbidden not in lv
    assert lv["title_left"] and lv["title_right"] and lv["reviewer_id"]


# ── 4. validation ────────────────────────────────────────────────────────────────────
def test_validate_rejects_model_verdict_key():
    rows = _candidates()
    d = packet_item_to_dict(build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)[0])
    for leak in ("predicted_status", "score", "reason", "label"):
        bad = dict(d)
        bad[leak] = "x"
        with pytest.raises(ValueError):
            validate_labeling_packet([bad])


def test_validate_rejects_raw_body_pii():
    rows = _candidates()
    d = packet_item_to_dict(build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)[0])
    for bad_key in ("body", "content", "author", "email"):
        bad = dict(d)
        bad[bad_key] = "leak"
        with pytest.raises(ValueError):
            validate_labeling_packet([bad])


def test_validate_required_and_enum():
    rows = _candidates()
    good = packet_item_to_dict(build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)[0])
    validate_labeling_packet([good])   # baseline ok
    for missing in ("packet_id", "reviewer_id", "pair_id", "sampling_bucket"):
        bad = dict(good)
        del bad[missing]
        with pytest.raises(ValueError):
            validate_labeling_packet([bad])
    with pytest.raises(ValueError):
        validate_labeling_packet([{**good, "assignment_status": "bogus"}])
    with pytest.raises(ValueError):
        validate_labeling_packet([{**good, "sampling_bucket": "nope"}])
    with pytest.raises(ValueError):
        validate_labeling_packet([{**good, "language": "fr"}])
    with pytest.raises(ValueError):
        validate_labeling_packet([{**good, "source_type_left": "blog"}])
    with pytest.raises(ValueError):
        validate_labeling_packet([{**good, "review_round": 0}])


def test_validate_duplicate_assignment_rejected():
    rows = _candidates()
    d = packet_item_to_dict(build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)[0])
    with pytest.raises(ValueError):
        validate_labeling_packet([d, dict(d)])


def test_write_packet_jsonl_roundtrip_deterministic(tmp_path):
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS)
    p = tmp_path / "packet.jsonl"
    n = write_labeling_packet_jsonl(items, p)
    assert n == len(items) and p.exists()
    t1 = p.read_text(encoding="utf-8")
    write_labeling_packet_jsonl(items, p)
    assert t1 == p.read_text(encoding="utf-8")
    # 기록된 행이 다시 validate 통과(verdict 부재 보존).
    loaded = [json.loads(x) for x in t1.splitlines() if x.strip()]
    validate_labeling_packet(loaded)
    assert all("predicted_status" not in r for r in loaded)


# ── 5. sampling report ───────────────────────────────────────────────────────────────
def test_sampling_selected_and_deficit():
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=2)
    rep = summarize_packet_sampling(rows, packet_items=items)
    assert rep["total_candidates"] == 16
    assert rep["selected_count"] == 16        # 전부 target 미만 → 전부 선택
    assert rep["reviewer_assignment_count"] == 32
    # 모든 bucket 이 draft target 미달(16 후보로는 floor 충당 불가) → deficit > 0·underfilled 전부.
    assert all(rep["deficit_by_bucket"][b] > 0 for b in CANDIDATE_BUCKETS)
    assert set(rep["underfilled_buckets"]) == set(CANDIDATE_BUCKETS)


def test_sampling_over_target_drops_excess():
    # 같은 bucket(official_news_positive)에 target 초과 후보 → cap 까지만 선택, 초과분 drop·oversampled 표면화.
    rows = [_ws(pair_id=f"p{i:02d}") for i in range(25)]   # 전부 official_news_positive
    target = {"official_news_positive": 5}
    rep = summarize_packet_sampling(rows, targets=target)
    assert rep["total_by_bucket"]["official_news_positive"] == 25
    assert rep["selected_by_bucket"]["official_news_positive"] == 5     # cap
    assert rep["selected_count"] == 5
    assert "official_news_positive" in rep["oversampled_buckets"]


def test_sampling_synthetic_does_not_inflate_live():
    rows = _candidates()   # 전부 synthetic_fixture
    rep = summarize_packet_sampling(rows)
    assert rep["live_vs_synthetic"][SOURCE_SYNTHETIC] == 16
    assert rep["live_vs_synthetic"][SOURCE_LIVE] == 0
    assert rep["floor_check"]["live_selected"] == 0     # synthetic 은 live floor 부풀리지 않음
    assert rep["floor_check"]["live_deficit"] == rep["floor_check"]["live_floor"]


def test_sampling_floor_check_uses_estimators():
    rows = _candidates()
    rep = summarize_packet_sampling(rows)
    fc = rep["floor_check"]
    assert fc["positive_floor"] == estimate_sample_floor_for_precision()   # 189
    assert fc["negative_floor"] == estimate_sample_floor_for_fpr()         # 381
    # selected positive/negative 가 floor 에 한참 못 미침 → deficit 정직 노출.
    assert fc["positive_deficit"] == fc["positive_floor"] - fc["positive_selected"]
    assert fc["negative_deficit"] == fc["negative_floor"] - fc["negative_selected"]
    assert fc["ko_deficit"] > 0


def test_sampling_ko_and_guard_buckets_counted():
    rows = _candidates()
    rep = summarize_packet_sampling(rows)
    assert rep["selected_by_bucket"]["ko_same_event_candidate"] == 1
    assert rep["selected_by_bucket"]["ko_different_event_candidate"] == 1
    for guard in ("community_guard", "market_guard", "catalog_guard", "unknown_guard"):
        assert rep["selected_by_bucket"][guard] == 1


# ── 6. ops report / no-auto-merge ────────────────────────────────────────────────────
def test_packet_ops_report_no_gold_no_merge():
    rows = _candidates()
    rep = generate_packet_ops_report(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=2)
    assert rep["candidates_in"] == 16
    assert rep["selected_pairs"] == 16
    assert rep["packet_items"] == 32
    assert rep["gold_resolved"] == 0        # packet 단계는 gold 0(라벨 전)
    assert rep["auto_merged"] == 0
    assert rep["distinct_reviewers"] == 3


def test_packet_report_deterministic():
    rows = _candidates()
    a = generate_packet_ops_report(rows, packet_id="pkt-1", reviewers=_REVIEWERS)
    b = generate_packet_ops_report(rows, packet_id="pkt-1", reviewers=_REVIEWERS)
    assert a == b


# ── 7. conflict → adjudication queue (자동 다수결 gold 금지) ──────────────────────────
def test_adjudication_queue_only_conflicts():
    # reviewer-a same / reviewer-b different → conflict. queue 에 표면화(자동 gold 아님).
    labels = [
        ReviewerLabel(pair_id="pX", reviewer_id="reviewer-a", review_round=1, label="same_event",
                      label_confidence="high", reviewed_at="2026-06-24T18:00:00Z", language="en",
                      source_type_left="article", source_type_right="article",
                      title_left="t", title_right="t",
                      observed_at_left="2026-06-24T09:00:00Z", observed_at_right="2026-06-24T10:00:00Z"),
        ReviewerLabel(pair_id="pX", reviewer_id="reviewer-b", review_round=1, label="different_event",
                      label_confidence="high", reviewed_at="2026-06-24T18:05:00Z", language="en",
                      source_type_left="article", source_type_right="article",
                      title_left="t", title_right="t",
                      observed_at_left="2026-06-24T09:00:00Z", observed_at_right="2026-06-24T10:00:00Z"),
    ]
    resolved = resolve_gold_from_reviewers(labels)
    assert resolved[0].agreement_status == AGREE_CONFLICT
    q = adjudication_queue_from_resolved(resolved)
    assert len(q) == 1
    assert q[0]["pair_id"] == "pX"
    assert q[0]["needs_human_adjudication"] is True
    assert q[0]["adjudicator_kind"] == REVIEWER_HUMAN
    # conflict 는 gold 0(자동 다수결 금지) — queue 가 자동 gold 를 만들지 않는다.
    assert resolved_to_gold_pairs(resolved) == []


def test_adjudication_queue_empty_when_agreed():
    labels = load_reviewer_labels(
        Path(__file__).resolve().parent / "fixtures" / "identity_reviewer_labels.sample.jsonl")
    resolved = resolve_gold_from_reviewers(labels, adjudications={
        "adjud_en": {"label": "different_event", "adjudicated_by": "reviewer-lead"}})
    q = adjudication_queue_from_resolved(resolved)
    # 샘플의 conflict_en 1건만 queue. agreed/adjudicated/single 은 제외.
    assert all(item["needs_human_adjudication"] for item in q)
    assert {i["pair_id"] for i in q} == {"conflict_en"}


# ── 8. end-to-end: packet → reviewer label → resolved gold ───────────────────────────
def test_packet_to_reviewer_roundtrip_no_auto_merge():
    rows = _candidates()
    items = build_labeling_packet(rows, packet_id="pkt-1", reviewers=_REVIEWERS, reviewers_per_pair=2)
    # 각 packet item(차폐된 view)에 reviewer 가 라벨을 단다(시뮬: 양쪽 same_event → agreed).
    labels = []
    for it in items:
        labels.append(ReviewerLabel(
            pair_id=it.pair_id, reviewer_id=it.reviewer_id, review_round=it.review_round,
            label="same_event", label_confidence="high", reviewed_at="2026-06-24T18:00:00Z",
            language=it.language, source_type_left=it.source_type_left, source_type_right=it.source_type_right,
            title_left=it.title_left, title_right=it.title_right,
            observed_at_left=it.observed_at_left, observed_at_right=it.observed_at_right,
            dataset_source=SOURCE_SYNTHETIC,
        ))
    report = generate_labeling_protocol_report(labels)
    assert report["auto_merged"] == 0
    # 16 pair 모두 2 reviewer 합의 → resolved gold 16. 자동 병합은 여전히 0.
    assert report["resolved_gold_count"] == 16
    assert report["conflict_count"] == 0
    if report["gold_metrics"] is not None:
        assert report["gold_metrics"]["merge_readiness"]["merge_ready"] is False
        assert report["gold_metrics"]["merge_readiness"]["auto_merge_enabled"] is False


def test_default_reviewers_per_pair_is_two():
    assert DEFAULT_REVIEWERS_PER_PAIR == 2
    # bucket target 은 hard_negative/ambiguous/KO 를 easy positive 보다 oversample.
    assert CANDIDATE_BUCKET_TARGETS["hard_negative"] > CANDIDATE_BUCKET_TARGETS["likely_same_predicted"]
    assert CANDIDATE_BUCKET_TARGETS["ambiguous_predicted"] > CANDIDATE_BUCKET_TARGETS["likely_same_predicted"]
