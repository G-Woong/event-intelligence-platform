"""G-4: GDELT host-level rate-limit profile — lock/persist/cooldown/ladder(우회 없음, net-0 주입)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ingestion.orchestration.gdelt_strategy import collect_gdelt
from ingestion.orchestration.rate_limit_governor import RateLimitGovernor
from ingestion.orchestration.vendor_api_routes import VendorRouteResult

_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)


def _vr(*, success, status, records=(), error=None):
    return VendorRouteResult("gdelt", "gdelt_doc_artlist", success, status,
                             "official_record", tuple(records), error, len(records))


def _ok_rec():
    return {"record_type": "official_record", "source_id": "gdelt", "title_or_label": "T",
            "source_url_or_evidence": "https://x.test/a", "canonical_url": "https://x.test/a",
            "published_at_or_observed_at": "20260616T100000Z", "body_state_or_signal": "official_record",
            "confirmation_policy": "evidence_required", "quality_pre_gate_decision": "pass"}


def test_persisted_last_call_blocks_within_min_interval(tmp_path):
    p = tmp_path / "gdelt_rl.json"
    gov = RateLimitGovernor(state_path=p)
    gov.record_call("gdelt", now=_NOW)
    gov.save()
    # 재로드(프로세스 재시작 모사) → min_interval 미경과면 차단
    gov2 = RateLimitGovernor(state_path=p)
    d = gov2.decide("gdelt", min_interval_seconds=10, now=_NOW + timedelta(seconds=5))
    assert d.allowed is False and "min_interval" in d.reason


def test_cooldown_active_skips_network_call():
    gov = RateLimitGovernor()
    gov.record_rate_limited("gdelt", reason="gdelt_provider_429", now=_NOW)
    called = {"n": 0}
    def _fetch(**kw):
        called["n"] += 1
        return _vr(success=True, status=200, records=[_ok_rec()])
    res = collect_gdelt(governor=gov, vendor_fetch=_fetch, now=_NOW)
    assert res.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert called["n"] == 0          # 쿨다운 중 → 네트워크 호출 0(무한 retry 금지)


def test_single_429_is_pending_not_disabled():
    gov = RateLimitGovernor()
    res = collect_gdelt(governor=gov, vendor_fetch=lambda **kw: _vr(success=False, status=429,
                                                                    error="provider_rate_limited"),
                        now=_NOW)
    # 단발 429는 pending_resume(자동 재개) — disabled/terminal 아님
    assert res.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"
    assert res.cooldown_until is not None and res.next_resume_at is not None


def test_query_ladder_order_when_empty():
    seen = []
    def _fetch(*, query, limit, timespan):
        seen.append(query)
        return _vr(success=True, status=200, records=[])   # 200 OK but no articles → 다음 query
    res = collect_gdelt(governor=RateLimitGovernor(), vendor_fetch=_fetch, now=_NOW,
                        sleep=lambda s: None)
    # 기본 ladder를 순서대로 소진(broad→single_keyword→narrow)
    assert res.attempts == ("broad", "single_keyword", "narrow")
    assert res.final_status == "EXTERNAL_RATE_LIMITED_PENDING_RESUME"


def test_success_payload_alive():
    res = collect_gdelt(governor=RateLimitGovernor(),
                        vendor_fetch=lambda **kw: _vr(success=True, status=200, records=[_ok_rec()]),
                        now=_NOW)
    assert res.final_status == "OFFICIAL_RECORD_ALIVE"
    assert res.item_count == 1
