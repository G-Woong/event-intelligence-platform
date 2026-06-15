"""G2-10: gdelt 전략 — min_interval/cooldown 강제, 429 pending_resume, 성공 시 records.

네트워크 0: vendor_fetch/governor/now/sleep 주입형.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.vendor_api_routes import VendorRouteResult

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)


def _ok_record():
    return {"record_type": "official_record", "source_id": "gdelt", "title_or_label": "T",
            "source_url_or_evidence": "https://x.test/a", "canonical_url": "https://x.test/a",
            "published_at_or_observed_at": "20260615T100000Z", "body_state_or_signal": "official_record",
            "confirmation_policy": "evidence_required", "quality_pre_gate_decision": "pass"}


def _ok(**kw):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", True, 200, "official_record",
                             (_ok_record(),), None, 1)


def _rate_limited(**kw):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, 429, "official_record",
                             (), "provider_rate_limited", 0)


def test_success_first_probe_returns_records():
    gov = RateLimitGovernor()
    r = collect_gdelt(governor=gov, vendor_fetch=_ok, now=_NOW, sleep=lambda s: None)
    assert r.success and r.final_status == "OFFICIAL_RECORD_ALIVE"
    assert r.item_count == 1 and r.attempts == ("broad",)


def test_429_sets_cooldown_and_pending_resume():
    gov = RateLimitGovernor()
    r = collect_gdelt(governor=gov, vendor_fetch=_rate_limited, now=_NOW, sleep=lambda s: None)
    assert r.success is False and r.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert r.cooldown_until is not None and r.next_resume_at == r.cooldown_until
    # governor에 cooldown이 실제로 저장되어 다음 run에서 자동 skip/resume
    assert gov.cooldown_until("gdelt") == r.cooldown_until


def test_cooldown_active_skips_network_call():
    gov = RateLimitGovernor()
    gov.record_rate_limited("gdelt", reason="prev", now=_NOW)
    called = {"n": 0}
    def vf(**kw):
        called["n"] += 1
        return _ok()
    r = collect_gdelt(governor=gov, vendor_fetch=vf, now=_NOW, sleep=lambda s: None)
    assert called["n"] == 0                            # 호출 자체를 안 함(no-bypass)
    assert r.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"


def test_min_interval_blocks_back_to_back():
    gov = RateLimitGovernor()
    gov.record_call("gdelt", now=_NOW)
    r = collect_gdelt(governor=gov, vendor_fetch=_ok, min_interval_seconds=10, now=_NOW,
                      sleep=lambda s: None)
    assert r.success is False                           # min_interval 미경과 → 차단
    assert "min_interval" in (r.error or "")


def test_ladder_simplifies_on_empty_then_pending():
    gov = RateLimitGovernor()
    seq = {"n": 0}
    def vf(**kw):
        seq["n"] += 1
        # 항상 200 OK but no records → ladder 소진 후 pending_resume
        return VendorRouteResult("gdelt", "gdelt_doc_artlist", False, 200, "official_record",
                                 (), "http_200_no_articles", 0)
    r = collect_gdelt(governor=gov, vendor_fetch=vf, max_probes=3, now=_NOW, sleep=lambda s: None)
    assert seq["n"] == 3 and r.attempts == ("broad", "single_keyword", "narrow")
    assert r.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
