"""ADR#85 — provider date-window fidelity control experiment tests (offline·network 0·secret 0).

transport 주입으로 variant 별 provider 동작을 결정론적으로 시뮬레이션해 메커니즘 분류·result class·aggregate-only
경계를 잠근다. 절대 단정/overclaim 금지(confidence high 금지)·제목 전문/raw body/score 미노출을 테스트로 강제.
"""
from __future__ import annotations

import json

from backend.app.tools.provider_date_window_fidelity import (
    DEFAULT_VARIANTS,
    H_NEWEST,
    RC_GATED,
    RC_IN_WINDOW_RELATED,
    RC_NOT_RUN,
    RC_OUT_OF_WINDOW_ONLY,
    run_date_window_fidelity_probe,
)

# 손으로 만든 date-pinned target(build_live_query_target 검증과 분리 — probe 단위 테스트).
TARGET = {
    "query_text": "U.S. Supreme Court asylum metering ruling",
    "named_entity": "U.S. Supreme Court",
    "event_phrase": "asylum metering ruling",
    "start_date": "2026-06-25", "end_date": "2026-06-26",
    "as_of_anchor": "2026-06-26", "time_window": "1d",
    "providers": ["guardian", "nyt"], "wired": True,
}


def env_present(keys):
    return {k: "present" for k in keys}


def env_missing(keys):
    return {k: "missing" for k in keys}


def _g(results):
    return json.dumps({"response": {"status": "ok", "results": results}})


# out-of-window(2026-06-28)·주제 무관(ADR#84 핵심 증상 재현).
_OUT = [
    {"webTitle": "Austrian Grand Prix qualifying results", "webUrl": "https://g/o1",
     "webPublicationDate": "2026-06-28T09:00:00Z"},
    {"webTitle": "World Cup highlights and reaction", "webUrl": "https://g/o2",
     "webPublicationDate": "2026-06-28T10:00:00Z"},
]
# in-window(2026-06-25)·주제 관련(query 토큰과 높은 overlap).
_REL = [
    {"webTitle": "Supreme Court asylum metering ruling decision", "webUrl": "https://g/r1",
     "webPublicationDate": "2026-06-25T09:00:00Z"},
]


def _transport_newest_dominant(url):
    # relevance 정렬만 in-window related 를 끌어옴 → newest 지배 가설을 시뮬레이션.
    if "order-by=relevance" in url:
        return _g(_REL)
    return _g(_OUT)


def _transport_all_out(url):
    # 모든 variant 가 out-of-window → in-window coverage 0/메커니즘 미확정(정직·overclaim 0).
    return _g(_OUT)


def test_not_opted_in_runs_nothing():
    out = run_date_window_fidelity_probe(TARGET, provider="guardian", live_query=False)
    assert out["live_query_executed"] is False
    assert all(r["result_class"] == RC_NOT_RUN for r in out["variant_results"])
    assert len(out["variant_results"]) == len(DEFAULT_VARIANTS)
    assert out["mechanism_confidence"] != "high"


def test_newest_dominance_classified_medium_not_overclaimed():
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_present, live_query=True)
    assert out["live_query_executed"] is True
    # relevance 정렬이 in-window related 를 끌어옴 → newest 지배.
    rel = next(r for r in out["variant_results"] if r["variant"] == "relevance_order")
    assert rel["result_class"] == RC_IN_WINDOW_RELATED and rel["in_window_count"] == 1
    assert out["order_by_newest_effect"] == "strong"
    assert out["mechanism_primary_hypothesis"] == H_NEWEST
    assert out["mechanism_confidence"] == "medium"        # 단정 아님(절대 high 금지).
    assert out["mechanism_confidence"] != "high"


def test_enforce_window_variant_drops_out_of_window():
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_present, live_query=True)
    en = next(r for r in out["variant_results"] if r["variant"] == "enforce_window")
    # enforce 가 6/28 out-of-window 를 전부 drop → no_in_window_records → out_of_window_only.
    assert en["result_class"] == RC_OUT_OF_WINDOW_ONLY
    assert en["block_reason"] == "no_in_window_records"
    assert out["in_window_coverage_effect"] == "zero_in_returned"


def test_aggregates_in_out_window_counts():
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_present, live_query=True)
    # relevance 가 in-window 1 발견; original/no_date/exact 는 out 2.
    assert out["in_window_records_found"] == 1
    assert out["out_of_window_records_dropped"] == 2
    assert out["no_in_window_records"] is False   # relevance 가 in-window 를 찾음.


def test_all_out_classified_date_filter_ignored_medium_not_overclaimed():
    # original==no_date(둘 다 out-of-window·동일) → date param 이 응답을 제약 못 함을 직접 시사 → date_filter_ignored.
    # newest/relevance·exact_phrase 동일이라 order/loose-q 는 'weak'(제거). confidence medium(절대 high 금지).
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_all_out,
        env_status_fn=env_present, live_query=True)
    assert out["date_param_effect"] == "weak"
    assert out["order_by_newest_effect"] == "weak"
    assert out["query_relevance_effect"] == "weak"
    assert out["mechanism_primary_hypothesis"] == "date_filter_ignored"
    assert out["mechanism_confidence"] == "medium"
    assert out["mechanism_confidence"] != "high"    # 단일 bounded run 은 절대 high 금지.
    assert out["no_in_window_records"] is True       # 모든 variant 가 out-of-window.
    assert out["provider_date_window_status"] == "returns_out_of_window"
    # date_filter_ignored 가 medium 가설로 명시되되, zero_in_window_coverage 도 부차 가설로 남는다(미분리·정직).
    hyps = {h["hypothesis"]: h["confidence"] for h in out["date_filter_mechanism_hypotheses"]}
    assert hyps.get("date_filter_ignored") == "medium"


def test_missing_credentials_gates_and_stops():
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_missing, live_query=True)
    rows = out["variant_results"]
    # 첫 variant 가 missing_credentials 로 gated → 이후 variant 는 not_run(불필요 호출 0).
    assert rows[0]["result_class"] == RC_GATED
    assert rows[0]["block_reason"] == "missing_credentials"
    assert all(r["result_class"] == RC_NOT_RUN for r in rows[1:])
    assert out["gated_reason"] == "missing_credentials"
    assert out["provider_date_window_status"].startswith("gated:")


def test_pace_seconds_waits_between_variants_via_sleep_fn():
    # pace_seconds>0 → variant 호출 전 사전 대기(host min_spacing 정직 준수). sleep_fn 주입 → 실제 sleep 0.
    calls = []
    run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_present, live_query=True, pace_seconds=6.0,
        sleep_fn=lambda s: calls.append(s))
    assert calls == [6.0, 6.0, 6.0, 6.0]   # 5 variants → 4 inter-call 대기(첫 호출 전 대기 없음).


def test_aggregate_only_no_titles_or_scores_exposed():
    out = run_date_window_fidelity_probe(
        TARGET, provider="guardian", transport=_transport_newest_dominant,
        env_status_fn=env_present, live_query=True)
    forbidden = {"title", "title_or_label", "body", "raw_body", "score", "model_score",
                 "rationale", "predicted_status", "canonical_url"}
    for r in out["variant_results"]:
        assert not (set(r) & forbidden), f"variant row leaked a forbidden key: {set(r) & forbidden}"
    assert out["raw_source_body_exposed"] is False
    assert out["secret_value_exposed"] is False
    assert out["same_event_truth_exposed"] is False
    assert out["per_pair_score_exposed"] is False


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
