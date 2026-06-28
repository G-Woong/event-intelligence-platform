"""ADR#83 — date-pinned operator event → live query target wiring + isolated executor 테스트.

검증(§14): ① operator event 검증(missing/invalid/valid occurrence_date·broad·placeholder·same_event/occurrence
False) · ② query target wiring(query_text=named_entity+event_phrase·occurrence_date 절대 윈도우 [D,D+1]·curated
fallback 불가·LIVE_QUERY_TARGET_WIRED 게이트) · ③ executor(hard guard·operator query 로 smoke 호출·today 절대 윈도우가
provider URL 에 반영·freeze passthrough·raw body 0·secret 0). network 0(transport/smoke_fn/freeze_fn 주입).
"""
from __future__ import annotations

import json

from backend.app.tools.live_query_target import (
    BLOCK_BROAD_ENTITY,
    BLOCK_MISSING_OCCURRENCE_DATE,
    BLOCK_OCCURRENCE_NOT_ISO,
    BLOCK_PLACEHOLDER_ENTITY,
    BLOCK_TARGET_NOT_WIRED,
    LIVE_QUERY_TARGET_WIRED,
    build_live_query_target,
    execute_date_pinned_bounded_live_run,
)

# 결정적 fixture 제목(실 source 아님·body 0).
WIRE = "Federal Reserve raises benchmark interest rate by quarter point"
PARA = "Federal Reserve raises benchmark interest rate by 25 basis points"
DIFF = "Federal Reserve official comments on interest rate policy outlook"
_SENTINEL = "ZZZ_FAKE_LQT_KEY_must_never_appear_83"


def _valid_event(**over) -> dict:
    ev = {"named_entity": "US Federal Reserve", "event_phrase": "FOMC rate decision",
          "occurrence_date": "2026-06-17"}
    ev.update(over)
    return ev


def _g_payload(items, day="2026-06-17"):
    return json.dumps({"response": {"status": "ok", "results": [
        {"webTitle": t, "webUrl": u, "webPublicationDate": day + "T12:00:00Z"} for t, u in items]}})


def _n_payload(items, day="2026-06-17"):
    return json.dumps({"status": "OK", "response": {"docs": [
        {"headline": {"main": t}, "web_url": u, "pub_date": day + "T13:00:00+0000"} for t, u in items]}})


def _probe(present=True):
    return lambda v: {"var_name": v, "credential_present": present,
                      "env_file_present": True, "declared_in_example": True}


def _present_env(keys):
    return {k: "present" for k in keys}


# ── ① operator event 검증 ────────────────────────────────────────────────────────────────────────────────────
def test_no_operator_event_not_provided_not_wired():
    t = build_live_query_target(None)
    assert t["operator_event_provided"] is False
    assert t["wired"] is False
    assert t["date_pinned_named_event_valid"] is False
    assert "missing_occurrence_date" in t["block_reasons"]


def test_missing_occurrence_date_blocks():
    t = build_live_query_target(_valid_event(occurrence_date=""))
    assert BLOCK_MISSING_OCCURRENCE_DATE in t["block_reasons"]
    assert t["date_pinned_named_event_valid"] is False
    assert t["wired"] is False


def test_invalid_occurrence_date_blocks():
    t = build_live_query_target(_valid_event(occurrence_date="June 17 2026"))
    assert BLOCK_OCCURRENCE_NOT_ISO in t["block_reasons"]
    assert t["occurrence_date_valid_iso"] is False
    assert t["wired"] is False


def test_valid_iso_occurrence_passes_date_pin():
    t = build_live_query_target(_valid_event())
    assert t["date_pinned_named_event_valid"] is True
    assert t["occurrence_date_valid_iso"] is True
    assert t["occurrence_date"] == "2026-06-17"


def test_same_event_and_occurrence_remain_false_even_when_pinned():
    t = build_live_query_target(_valid_event())
    assert t["event_occurrence_verified"] is False
    assert t["same_event_asserted"] is False


def test_broad_entity_rejected():
    t = build_live_query_target(_valid_event(named_entity="Federal Reserve"))
    assert BLOCK_BROAD_ENTITY in t["block_reasons"]
    assert t["wired"] is False


def test_placeholder_entity_rejected():
    t = build_live_query_target(_valid_event(named_entity="<Acquirer> (operator fills)"))
    assert BLOCK_PLACEHOLDER_ENTITY in t["block_reasons"]
    assert t["wired"] is False


# ── ② query target wiring ────────────────────────────────────────────────────────────────────────────────────
def test_query_text_uses_named_entity_and_event_phrase():
    t = build_live_query_target(_valid_event())
    assert t["query_text"] == "US Federal Reserve FOMC rate decision"
    assert "US Federal Reserve" in t["query_text"]
    assert "FOMC rate decision" in t["query_text"]


def test_query_hint_recorded_but_not_in_executed_query():
    t = build_live_query_target(_valid_event(query_hint="fed hikes 25bps june"))
    assert t["operator_query_hint"] == "fed hikes 25bps june"
    # 실행 query 는 entity+phrase — hint 로 anchor 유실 방지(hint 는 기록만).
    assert t["query_text"] == "US Federal Reserve FOMC rate decision"


def test_occurrence_date_absolute_window_is_d_to_d_plus_1():
    t = build_live_query_target(_valid_event(occurrence_date="2026-06-17"))
    assert t["start_date"] == "2026-06-17"
    assert t["end_date"] == "2026-06-18"
    assert t["as_of_anchor"] == "2026-06-18"   # run_provider_query(today=) → window [D, D+1].
    assert t["time_window"] == "1d"


def test_providers_default_guardian_nyt_with_guardian_anchor():
    t = build_live_query_target(_valid_event())
    assert t["providers"] == ["guardian", "nyt"]
    assert t["provider_a"] == "guardian"
    assert t["second_provider"] == "nyt"
    assert t["source_role_required"] == "publishable"


def test_wired_flag_false_blocks_target():
    t = build_live_query_target(_valid_event(), wired_flag=False)
    assert t["live_query_target_wired"] is False
    assert BLOCK_TARGET_NOT_WIRED in t["block_reasons"]
    assert t["wired"] is False


def test_module_flag_is_true_after_test_lock():
    # ADR#83: plumbing test-locked → True. live 실행은 여전히 operator event + opt-in + pool 요구.
    assert LIVE_QUERY_TARGET_WIRED is True


# ── ③ executor: hard guard(curated fallback 불가) ──────────────────────────────────────────────────────────────
def test_executor_hard_guard_not_wired_does_not_execute():
    called = {"smoke": False}

    def boom_smoke(**_kw):
        called["smoke"] = True
        raise AssertionError("smoke must NOT be called when target not wired")

    t = build_live_query_target(_valid_event(), wired_flag=False)
    res = execute_date_pinned_bounded_live_run(t, smoke_fn=boom_smoke)
    assert res["executed"] is False
    assert res["smoke"] is None
    assert res["block_reason"] == BLOCK_TARGET_NOT_WIRED
    assert called["smoke"] is False


def test_executor_empty_query_text_does_not_execute():
    # date_pinned 이지만 query_text 빈값(이론상 — entity/phrase 없음)이면 fail-closed.
    t = build_live_query_target(None)
    res = execute_date_pinned_bounded_live_run(t, smoke_fn=lambda **k: {})
    assert res["executed"] is False
    assert res["block_reason"] == BLOCK_TARGET_NOT_WIRED


# ── ③ executor: operator query 로 smoke 호출(curated topic 아님) ───────────────────────────────────────────────
def test_executor_queries_operator_event_not_curated_seed():
    captured = {}

    def fake_smoke(**kw):
        captured.update(kw)
        return {"live_query_attempted": True, "provider_status_by_provider": {"guardian": "ok", "nyt": "ok"},
                "dataset_source": "live_derived", "cross_source_pair_count": 2,
                "recall_probe_diagnostic": {"max_recall_probe_score": 0.5, "pairs_newly_routed_by_probe": 1,
                                            "pairs_newly_routed_sharing_entity": 1},
                "band_diagnostic": {"max_cross_source_title_jaccard": 0.4}, "block_reasons": []}

    def fake_freeze(**kw):
        captured["acquire_result"] = kw["acquire_fn"](live_query=True)
        return {"production_candidate_status": "production_batch_frozen",
                "production_candidate_batch_ready": True, "production_frozen_pair_count": 1,
                "candidate_provenance": "live_derived", "production_gold_count": 0, "current_r1_gap": 200}

    t = build_live_query_target(_valid_event())
    res = execute_date_pinned_bounded_live_run(t, smoke_fn=fake_smoke, freeze_fn=fake_freeze)
    assert captured["topic"] == "US Federal Reserve FOMC rate decision"
    assert captured["today"] == "2026-06-18"            # occurrence_date+1 절대 anchor.
    assert captured["time_window"] == "1d"
    assert captured["provider_b"] == "nyt"
    assert "central bank" not in (captured["topic"] or "")   # curated default 아님.
    assert captured["emit_recall_probe"] is True
    assert res["executed"] is True
    # freeze 가 smoke 를 acquire_fn 으로 소비(targeted-layer 패턴).
    assert res["pcand"]["production_candidate_batch_ready"] is True
    assert res["pcand"]["candidate_provenance"] == "live_derived"


# ── ③ executor 통합: today 절대 윈도우가 provider URL 에 반영(date pin 이 실제 쿼리에 도달) ────────────────────
def test_today_anchor_and_query_reach_provider_url_real_smoke():
    cap: list[str] = []

    def gtr(url):
        cap.append(url)
        return _g_payload([(WIRE, "https://g.test/a"), (PARA, "https://g.test/b")])

    def ntr(url):
        cap.append(url)
        return _n_payload([(WIRE, "https://nyt.test/a"), (DIFF, "https://nyt.test/b")])

    t = build_live_query_target(_valid_event(occurrence_date="2026-06-17"))
    res = execute_date_pinned_bounded_live_run(
        t, transport_a=gtr, transport_b=ntr, env_status_fn=_present_env, env_probe_fn=_probe(True),
        freeze_fn=lambda **kw: {"production_candidate_status": "production_batch_frozen",
                                "production_candidate_batch_ready": True, "production_frozen_pair_count": 1,
                                "candidate_provenance": "live_derived", "production_gold_count": 0})
    # 절대 윈도우 [2026-06-17, 2026-06-18] 가 provider 쿼리 URL 에 반영(date pin 이 실제 쿼리에 도달).
    assert any("2026-06-17" in u and "2026-06-18" in u for u in cap), cap
    # query_text(entity+phrase) 가 URL 에 반영.
    assert any("Federal" in u for u in cap)
    assert res["executed"] is True
    assert res["smoke"]["dataset_source"] == "live_derived"
    # raw body 0·secret 0(sentinel 미노출).
    blob = json.dumps(res, default=str)
    assert _SENTINEL not in blob
    assert res["smoke"].get("credential_value_exposed") is False
    assert res["smoke"].get("env_file_read") is False


def test_executor_freeze_does_not_increase_gold():
    t = build_live_query_target(_valid_event())
    res = execute_date_pinned_bounded_live_run(
        t, smoke_fn=lambda **k: {"live_query_attempted": True,
                                 "provider_status_by_provider": {"guardian": "ok", "nyt": "ok"},
                                 "dataset_source": "live_derived", "cross_source_pair_count": 1,
                                 "recall_probe_diagnostic": {}, "band_diagnostic": {}, "block_reasons": []},
        freeze_fn=lambda **kw: {"production_candidate_status": "production_batch_frozen",
                                "production_candidate_batch_ready": True, "production_frozen_pair_count": 1,
                                "candidate_provenance": "live_derived", "production_gold_count": 0})
    assert res["pcand"]["production_gold_count"] == 0
