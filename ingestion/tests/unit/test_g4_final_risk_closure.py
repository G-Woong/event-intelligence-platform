"""G-4: end-to-end final risk closure — risk verdict + source-specific proof + gdelt escalation(net-0)."""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.dcinside_strategy import DCInsideDetailAudit, DCInsideStrategyResult
from ingestion.orchestration.final_source_closure import (
    EXTERNAL_RATE_LIMITED_PENDING_RESUME,
    PRODUCTION_READY,
    PRODUCTION_READY_COMMUNITY_PREVIEW,
)
from ingestion.orchestration.gdelt_strategy import GdeltStrategyResult
from ingestion.orchestration.vendor_api_routes import VendorRouteResult
from ingestion.tools.run_final_source_closure import run_final_source_closure

_NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=timezone.utc)
_ROBOTS = "User-agent: *\nAllow: /\n"


def _eq(rt, sid, url, t, sig, conf):
    return {"record_type": rt, "source_id": sid, "title_or_label": "T", "source_url_or_evidence": url,
            "canonical_url": url, "published_at_or_observed_at": t, "body_state_or_signal": sig,
            "confirmation_policy": conf, "quality_pre_gate_decision": "pass"}


def _dc_list():
    recs = tuple(_eq("community_signal", "dcinside",
                     f"https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={n}",
                     "2026-06-16T10:00:00+09:00", "community_signal", "unconfirmed_until_corroborated")
                 for n in (1, 2, 3))
    return DCInsideStrategyResult("dcinside", "stockus", "u", True, 200, None, recs, 3, "COMMUNITY_SIGNAL_ALIVE")


def _dc_audit(urls):
    return DCInsideDetailAudit("dcinside", tuple(urls), len(urls), (200,) * len(urls), None,
                               ".write_div", 0, False, "DETAIL_BODY_EMPTY_STATIC")


def _ph():
    return VendorRouteResult("product_hunt", "ph_graphql_posts", True, 200, "community_signal",
                             (_eq("community_signal", "product_hunt", "https://www.producthunt.com/products/novu",
                                  "2026-06-15T07:01:00Z", "community_signal", "unconfirmed_until_corroborated"),),
                             None, 1)


def _culture():
    return VendorRouteResult("culture_info", "culture_period2_detail2", True, 200, "official_record",
                             (_eq("official_record", "culture_info", "https://sma.sbculture.or.kr/x#seq=315929",
                                  "2025-02-26", "official_record", "source_confirmed"),), None, 1)


def _gdelt_ok(gov):
    return GdeltStrategyResult("gdelt", True, 200,
                               (_eq("official_record", "gdelt", "https://x.test/a", "20260616T100000Z",
                                    "official_record", "evidence_required"),), 1, ("broad",),
                               "OFFICIAL_RECORD_ALIVE", None, None, None)


def _gdelt_429(gov):
    return GdeltStrategyResult("gdelt", False, 429, (), 0, ("broad", "single_keyword", "narrow"),
                               EXTERNAL_RATE_LIMITED_PENDING_RESUME,
                               "2026-06-16T12:31:00Z", "2026-06-16T12:31:00Z", "provider_rate_limited")


def _run(**over):
    kw = dict(robots_get=lambda u: _ROBOTS, dcinside_list_collect=_dc_list, dcinside_detail_audit=_dc_audit,
              ph_fetch=_ph, culture_fetch=_culture, gdelt_collect=_gdelt_ok,
              apply_config=False, write_outputs=False, now=_NOW)
    kw.update(over)
    return run_final_source_closure(**kw)


def test_all_risks_closed_when_gdelt_fresh():
    r = _run()
    by = {c.source_id: c for c in r["results"]}
    assert by["dcinside"].final_status == PRODUCTION_READY_COMMUNITY_PREVIEW
    assert by["gdelt"].final_status == PRODUCTION_READY
    assert r["risk_verdict"]["verdict"] == "ALL_REMAINING_NON_EXCLUDED_SOURCE_RISKS_CLOSED"
    assert r["risk_verdict"]["open_risks"] == []
    # source-specific proof: 4 target 모두 eq/raw contract 통과
    for s in ("dcinside", "culture_info", "product_hunt", "gdelt"):
        assert r["proof_pass"][s] is True
        assert r["proof_by_source"][s]["eventqueue_proof"] >= 1
        assert r["proof_by_source"][s]["raw_events_proof"] >= 1
    assert r["critical_alerts"] == 0


def test_gdelt_429_yields_provider_constrained_partial():
    r = _run(gdelt_collect=_gdelt_429)
    by = {c.source_id: c for c in r["results"]}
    assert by["gdelt"].final_status == EXTERNAL_RATE_LIMITED_PENDING_RESUME
    # 나머지 3개는 닫혔고 gdelt만 scheduled → provider-constrained PARTIAL
    assert r["risk_verdict"]["verdict"] == "PARTIAL_ONLY_IF_LEGAL_OR_PROVIDER_HARD_BLOCKER_WITH_FULL_EVIDENCE"
    assert r["risk_verdict"]["open_risks"] == ["gdelt"]
    assert r["risk_verdict"]["gdelt_scheduled"] is True
    # culture/ph는 여전히 proof 통과
    assert r["proof_pass"]["culture_info"] is True and r["proof_pass"]["product_hunt"] is True
