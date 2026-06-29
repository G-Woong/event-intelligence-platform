"""ADR#86 — Federal Register bounded live smoke tests (offline·transport 주입 결정론·network 0·secret 0).

§10 status 분류·date_filter live_verified/live_weak·key-free·raw body 0·snapshot aggregate-only 를 잠근다.
"""
from __future__ import annotations

import json

from backend.app.tools.federal_register_live_smoke import (
    DFC_DOCUMENTED_UNVERIFIED,
    DFC_LIVE_NO_RECORDS,
    DFC_LIVE_VERIFIED,
    DFC_LIVE_WEAK,
    FR_LIVE_NOT_RUN,
    FR_LIVE_OK_IN_WINDOW,
    FR_LIVE_OK_NO_RECORDS,
    FR_LIVE_OUT_OF_WINDOW,
    FR_LIVE_RATE_BLOCKED,
    run_federal_register_live_smoke,
    sanitized_fr_live,
)

_WINDOW = ("2026-06-25", "2026-06-26")


def _fr_payload(dates):
    return json.dumps({"count": len(dates), "results": [
        {"title": f"Rule {i} on asylum metering", "html_url": f"https://www.federalregister.gov/d/{i}",
         "publication_date": d, "document_number": f"2026-{i:05d}"}
        for i, d in enumerate(dates)]})


def env_missing(keys):
    return {k: "missing" for k in keys}


def test_01_not_opted_in_fr_live_not_run():
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, live_query=False)
    assert out["fr_live_status"] == FR_LIVE_NOT_RUN
    assert out["date_filter_capability"] == DFC_DOCUMENTED_UNVERIFIED
    assert out["live_query_executed"] is False and out["live_call_count"] == 0


def _tr(dates):
    """fake transport(def·E731 회피) — 주어진 publication_date 목록의 FR 응답을 반환."""
    def _t(_u):
        return _fr_payload(dates)
    return _t


def test_02_all_in_window_live_verified():
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-25", "2026-06-26"]),
                                          env_status_fn=env_missing)
    assert out["fr_live_status"] == FR_LIVE_OK_IN_WINDOW
    assert out["date_filter_capability"] == DFC_LIVE_VERIFIED   # FR 이 window 존중(in-window 전부).
    assert out["in_window_records"] == 2 and out["out_of_window_records"] == 0


def test_03_out_of_window_live_weak():
    # FR 이 명시 date 필터에도 window 밖(6/29) 문서를 반환 → live_weak(Guardian/NYT 와 같은 증상 class).
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-29", "2026-06-30"]),
                                          env_status_fn=env_missing)
    assert out["fr_live_status"] == FR_LIVE_OUT_OF_WINDOW
    assert out["date_filter_capability"] == DFC_LIVE_WEAK
    assert out["in_window_records"] == 0 and out["out_of_window_records"] == 2


def test_04_mixed_window_live_weak():
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-25", "2026-06-29"]),
                                          env_status_fn=env_missing)
    assert out["date_filter_capability"] == DFC_LIVE_WEAK   # 혼재도 live_weak(부분 제약·정직).
    assert out["in_window_records"] == 1 and out["out_of_window_records"] == 1


def test_05_no_records_live_no_records():
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr([]), env_status_fn=env_missing)
    assert out["fr_live_status"] == FR_LIVE_OK_NO_RECORDS
    assert out["date_filter_capability"] == DFC_LIVE_NO_RECORDS


def test_06_key_free_official_records_returned_for_bridge():
    # key-free(env_missing 이어도 fetch) + records 는 official_record(bridge 입력).
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-25"]),
                                          env_status_fn=env_missing)
    assert out["credential_required"] is False and out["secret_exposed"] is False
    assert len(out["official_records"]) == 1
    assert out["official_records"][0]["record_type"] == "official_record"


def test_07_sanitized_excludes_records_and_titles():
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-25", "2026-06-29"]),
                                          env_status_fn=env_missing)
    agg = sanitized_fr_live(out)
    assert "official_records" not in agg and "topic" not in agg
    blob = json.dumps(agg, ensure_ascii=False)
    assert "asylum metering" not in blob and "federalregister.gov/d" not in blob   # title/url 미노출.
    assert agg["records_returned"] == 2 and agg["in_window_records"] == 1


class _BlockGate:
    """host floor 미경과 gate 대역(allowed=False) — transport 전 차단(실 network 0)."""

    def decide(self, host, *, min_spacing_seconds):
        from types import SimpleNamespace
        return SimpleNamespace(allowed=False, reason=f"host_min_spacing_not_elapsed:1<{min_spacing_seconds}")

    def record_call(self, host):
        raise AssertionError("record_call must NOT run when the gate blocks")


def test_08_host_gate_blocked_is_not_no_records():
    # host gate 차단 = governance event(실 network 0) → fr_live_rate_blocked·live_call_count 0(no_records 둔갑 금지·NIT-1).
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, transport=_tr(["2026-06-25"]),
                                          env_status_fn=env_missing, host_gate=_BlockGate())
    assert out["fr_live_status"] == FR_LIVE_RATE_BLOCKED
    assert out["host_gate_blocked"] is True
    assert out["live_call_count"] == 0   # 실 network 미발생 → 호출 0(회계 정직).
    assert out["date_filter_capability"] == DFC_DOCUMENTED_UNVERIFIED


def test_09_max_records_forwarded_to_query():
    # max_records 가 run_provider_query 로 전달되어 parser cap 적용(NIT-2: dead param 아님).
    out = run_federal_register_live_smoke(topic="x", date_window=_WINDOW, today="2026-06-26",
                                          live_query=True, max_records=1,
                                          transport=_tr(["2026-06-25", "2026-06-26"]), env_status_fn=env_missing)
    assert out["records_returned"] == 1   # 2건 반환돼도 max_records=1 로 cap.
