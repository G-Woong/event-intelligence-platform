"""G-3/G-9: RescueRouter — blocking_layer/vendor route → rescue strategy(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.rescue_router import (
    BODY_LADDER_FETCH,
    DISABLE_LOW_VALUE,
    POLICY_BLOCK_NO_BYPASS,
    SOURCE_ADAPTER_FIX,
    VENDOR_ROUTE_FIX,
    decide_rescue,
    route_all,
)
from ingestion.orchestration.source_readiness_closure import (
    BODY_FETCH,
    EVIDENCE_ANCHOR,
    POLICY,
    RATE_LIMIT,
    SOURCE_VALUE,
    SourceReadinessGap,
)


def _gap(sid, layer, final="PRODUCTION_READY"):
    return SourceReadinessGap(
        source_id=sid, previous_status="X", source_group="g", expected_record_type="r",
        root_cause=("x",), blocking_layer=layer, rescue_possible=True,
        rescue_plan=(), required_code_change=(), final_required_status=final)


def test_vendor_source_uses_vendor_route():
    d = decide_rescue(_gap("bok_ecos", "API_ROUTE"))
    assert d.rescue_strategy == VENDOR_ROUTE_FIX


def test_gdelt_ratelimit_uses_vendor_route():
    # gdelt는 RATE_LIMIT이지만 vendor route(GDELT DOC)가 있으므로 vendor_route_fix
    d = decide_rescue(_gap("gdelt", RATE_LIMIT))
    assert d.rescue_strategy == VENDOR_ROUTE_FIX


def test_body_fetch_source_uses_body_ladder():
    d = decide_rescue(_gap("cnbc", BODY_FETCH))
    assert d.rescue_strategy == BODY_LADDER_FETCH


def test_evidence_anchor_uses_adapter_fix():
    # vendorless EVIDENCE_ANCHOR source(tmdb)는 adapter anchor fix로 라우팅.
    # (culture_info는 Phase G-3에서 period2->detail2 vendor route를 갖게 되어 아래 별도 테스트로 이동.)
    d = decide_rescue(_gap("tmdb", EVIDENCE_ANCHOR))
    assert d.rescue_strategy == SOURCE_ADAPTER_FIX


def test_culture_info_evidence_anchor_now_uses_vendor_route():
    # Phase G-3: culture_info가 vendor route(period2->detail2 실 url)로 anchor를 해결 → vendor_route_fix.
    d = decide_rescue(_gap("culture_info", EVIDENCE_ANCHOR))
    assert d.rescue_strategy == VENDOR_ROUTE_FIX


def test_source_value_uses_disable_even_if_vendorless():
    d = decide_rescue(_gap("its", SOURCE_VALUE))
    assert d.rescue_strategy == DISABLE_LOW_VALUE


def test_policy_uses_no_bypass():
    d = decide_rescue(_gap("dcinside", POLICY))
    assert d.rescue_strategy == POLICY_BLOCK_NO_BYPASS
    assert d.reason == "policy_no_bypass_documented"


def test_source_value_not_overridden_by_vendor_route():
    # 만약 vendor route가 있어도 SOURCE_VALUE/POLICY는 disable/policy 우선(억지로 살리지 않음)
    d = decide_rescue(_gap("its", SOURCE_VALUE))
    assert d.rescue_strategy != VENDOR_ROUTE_FIX


def test_route_all_batch():
    gaps = [_gap("bok_ecos", "API_ROUTE"), _gap("cnbc", BODY_FETCH), _gap("its", SOURCE_VALUE)]
    decisions = {d.source_id: d for d in route_all(gaps)}
    assert decisions["bok_ecos"].rescue_strategy == VENDOR_ROUTE_FIX
    assert decisions["cnbc"].rescue_strategy == BODY_LADDER_FETCH
    assert decisions["its"].rescue_strategy == DISABLE_LOW_VALUE
