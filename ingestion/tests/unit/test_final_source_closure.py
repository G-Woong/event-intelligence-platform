"""G-3: final source closure — 흡수 파이프라인 통합(net-0 주입) + 결정/분류 로직."""
from __future__ import annotations

from datetime import datetime, timezone

from ingestion.orchestration.dcinside_strategy import DCInsideDetailAudit, DCInsideStrategyResult
from ingestion.orchestration.final_source_closure import (
    EXTERNAL_RATE_LIMITED_PENDING_RESUME,
    PRODUCTION_READY,
    PRODUCTION_READY_COMMUNITY_PREVIEW,
    PRODUCTION_READY_WITH_PUBLIC_PREVIEW_ONLY,
    VERIFIED_HARD_BLOCKER,
    FinalSourceClosure,
    classify_final_closure,
    decide_final_status,
)
from ingestion.orchestration.gdelt_strategy import GdeltStrategyResult
from ingestion.orchestration.source_capability import capability_for
from ingestion.orchestration.vendor_api_routes import VendorRouteResult
from ingestion.tools.run_final_source_closure import run_final_source_closure

_NOW = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
_ROBOTS = "User-agent: ClaudeBot\nDisallow: /\nUser-agent: *\nAllow: /\n"


def _eq(rt, sid, url, t, sig, conf):
    return {"record_type": rt, "source_id": sid, "title_or_label": "T", "source_url_or_evidence": url,
            "canonical_url": url, "published_at_or_observed_at": t, "body_state_or_signal": sig,
            "confirmation_policy": conf, "quality_pre_gate_decision": "pass"}


def _dc_list():
    recs = tuple(_eq("community_signal", "dcinside",
                     f"https://gall.dcinside.com/mgallery/board/view/?id=stockus&no={n}",
                     "2026-06-15T10:00:00+09:00", "community_signal", "unconfirmed_until_corroborated")
                 for n in (1, 2, 3))
    return DCInsideStrategyResult("dcinside", "stockus", "u", True, 200, None, recs, 3, "COMMUNITY_SIGNAL_ALIVE")


def _dc_cloudflare():
    return DCInsideStrategyResult("dcinside", "stockus", "u", False, 200, "cloudflare_challenge",
                                  (), 0, "CLOUDFLARE_BLOCKED_NO_BYPASS")


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
                               (_eq("official_record", "gdelt", "https://x.test/a", "20260615T100000Z",
                                    "official_record", "evidence_required"),), 1, ("broad",),
                               "OFFICIAL_RECORD_ALIVE", None, None, None)


def _gdelt_429(gov):
    return GdeltStrategyResult("gdelt", False, 429, (), 0, ("broad",),
                               "EXTERNAL_RATE_LIMITED_PENDING_RESUME",
                               "2026-06-15T12:31:00Z", "2026-06-15T12:31:00Z", "provider_rate_limited")


def _run(**over):
    kw = dict(robots_get=lambda u: _ROBOTS, dcinside_list_collect=_dc_list, dcinside_detail_audit=_dc_audit,
              ph_fetch=_ph, culture_fetch=_culture, gdelt_collect=_gdelt_ok,
              apply_config=False, write_outputs=False, now=_NOW)
    kw.update(over)
    return run_final_source_closure(**kw)


def test_three_ready_dcinside_community_preview_role():
    r = _run()
    by = {c.source_id: c for c in r["results"]}
    assert by["product_hunt"].final_status == PRODUCTION_READY and by["product_hunt"].is_production_ready()
    assert by["culture_info"].final_status == PRODUCTION_READY and by["culture_info"].is_production_ready()
    assert by["gdelt"].final_status == PRODUCTION_READY
    # G-4: dcinside는 애매한 DEGRADED가 아니라 community preview signal 역할로 명확히 닫힌다.
    assert by["dcinside"].final_status == PRODUCTION_READY_COMMUNITY_PREVIEW
    assert by["dcinside"].is_community_preview() is True
    assert by["dcinside"].is_production_ready() is False     # clean READY와는 구분
    assert by["dcinside"].is_degraded() is False             # DEGRADED로 세지 않음
    # degraded_remaining 0(더 이상 preview-only DEGRADED 없음), rate_limited 0
    assert r["verdict"]["degraded_remaining"] == 0
    assert r["verdict"]["external_rate_limited_remaining"] == 0
    # G-4 risk verdict: 4개 모두 닫힘(gdelt fresh) → ALL_CLOSED
    assert r["risk_verdict"]["verdict"] == "ALL_REMAINING_NON_EXCLUDED_SOURCE_RISKS_CLOSED"
    assert r["risk_verdict"]["open_risks"] == []
    assert r["eventqueue_written"] == 6 and r["raw_events_written"] == 6
    assert r["bridge_contract_pass"] is True and r["critical_alerts"] == 0
    # source-specific proof: 4 target 모두 contract 통과
    assert all(r["proof_pass"].get(s) for s in ("dcinside", "culture_info", "product_hunt", "gdelt"))


def test_gdelt_429_pending_resume_not_disguised():
    r = _run(gdelt_collect=_gdelt_429)
    g = {c.source_id: c for c in r["results"]}["gdelt"]
    assert g.final_status == EXTERNAL_RATE_LIMITED_PENDING_RESUME
    assert g.pending_resume_at == "2026-06-15T12:31:00Z"
    assert g.eventqueue_records == 0          # fresh record 0 → ready 둔갑 금지
    assert r["verdict"]["external_rate_limited_remaining"] == 1


def test_dcinside_cloudflare_is_hard_blocker_no_bypass():
    r = _run(dcinside_list_collect=_dc_cloudflare)
    dc = {c.source_id: c for c in r["results"]}["dcinside"]
    assert dc.final_status == VERIFIED_HARD_BLOCKER
    assert "CLOUDFLARE" in (dc.hard_blocker_evidence or "")
    assert dc.eventqueue_records == 0         # 우회 없이 0건


def test_decide_final_status_rate_limited_pending():
    cap = capability_for("gdelt")
    fs, reason, blk = decide_final_status(capability=cap, gate=None, record_count=0,
                                          rate_limited=True, pending_resume_at="2026-06-15T12:31:00Z")
    assert fs == EXTERNAL_RATE_LIMITED_PENDING_RESUME


def test_decide_final_status_gate_fail_needs_review():
    cap = capability_for("product_hunt")
    bad_gate = {"ready_allowed": False, "downgrade_reasons": ("SYNTHETIC_OR_LOCAL_EVIDENCE",)}
    fs, reason, blk = decide_final_status(capability=cap, gate=bad_gate, record_count=2)
    assert fs == "NEEDS_OPERATOR_REVIEW"      # 데이터 있어도 gate 실패면 둔갑 금지


def test_classify_all_ready():
    def mk(sid, fs, eq):
        return FinalSourceClosure(sid, "x", (), "s", (), eq, eq, eq, fs, None, None, None)
    allr = [mk(s, PRODUCTION_READY, 1) for s in ("a", "b", "c", "d")]
    assert classify_final_closure(allr)["verdict"] == "ALL_REMAINING_NON_EXCLUDED_SOURCES_READY"
    # records 0이면 ready로 안 침
    none = [mk(s, PRODUCTION_READY, 0) for s in ("a", "b")]
    assert classify_final_closure(none)["verdict"] == "BLOCKED"


def test_memory_update_emitted_for_promotions():
    r = _run(apply_config=False)
    # 승격 source는 memory 패치를 만든다(러너가 profile_patches로 노출).
    assert "product_hunt" in r["profile_patches"]
    assert "culture_info" in r["profile_patches"]
