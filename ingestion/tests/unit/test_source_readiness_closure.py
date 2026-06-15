"""G-1/G-7: readiness gap matrix — 비-ready non-excluded source 진단(네트워크 0)."""
from __future__ import annotations

from ingestion.orchestration.production_state import ProductionSourceState
from ingestion.orchestration.source_profile import SourceProfile
from ingestion.orchestration.source_readiness_closure import (
    API_PARAMS,
    API_ROUTE,
    BODY_FETCH,
    EVIDENCE_ANCHOR,
    POLICY,
    SOURCE_VALUE,
    build_gap_matrix,
    build_readiness_gap,
    summarize_gaps,
)


def _state(sid, status, group, reason=None):
    return ProductionSourceState(
        source_id=sid, enabled=True, excluded=False, source_group=group,
        expected_alive_type="X", current_status=status, terminal_reason=reason)


def _profile(sid, group="official"):
    return SourceProfile(source_id=sid, enabled=True, source_group=group, purpose=group)


def test_vendor_contract_is_api_route():
    g = build_readiness_gap(_state("bok_ecos", "VENDOR_CONTRACT_REQUIRED", "official",
                                   "CATALOG_ENDPOINT_NOT_SERIES"), _profile("bok_ecos"))
    assert g.blocking_layer == API_ROUTE and g.rescue_possible


def test_kma_result_code_is_api_params():
    g = build_readiness_gap(_state("kma", "EXTERNAL_API_ERROR", "domain",
                                   "API_RESULT_CODE_10_RANGE"), _profile("kma", "domain"))
    assert g.blocking_layer == API_PARAMS


def test_nyt_403_is_api_route():
    g = build_readiness_gap(_state("nyt", "EXTERNAL_API_ERROR", "news",
                                   "HTTP_403_ANTI_BOT"), _profile("nyt", "news"))
    assert g.blocking_layer == API_ROUTE


def test_cnbc_excerpt_is_body_fetch():
    g = build_readiness_gap(_state("cnbc", "EXTERNAL_API_ERROR", "news",
                                   "EXCERPT_ONLY_NO_FULL_BODY"), _profile("cnbc", "news"))
    assert g.blocking_layer == BODY_FETCH


def test_degraded_is_evidence_anchor():
    g = build_readiness_gap(_state("culture_info", "PRODUCTION_READY_DEGRADED", "domain",
                                   "NO_STABLE_URL"), _profile("culture_info", "domain"))
    assert g.blocking_layer == EVIDENCE_ANCHOR


def test_not_service_useful_is_source_value():
    g = build_readiness_gap(_state("its", "NOT_SERVICE_USEFUL", "domain"), _profile("its", "domain"))
    assert g.blocking_layer == SOURCE_VALUE
    assert g.final_required_status == "DISABLED_NOT_SERVICE_USEFUL"


def test_gap_matrix_excludes_ready_and_excluded():
    states = [
        _state("bbc", "PRODUCTION_READY", "news"),
        ProductionSourceState(source_id="reddit", enabled=False, excluded=True,
                              source_group="community", expected_alive_type="X",
                              current_status="POLICY_EXCLUDED"),
        _state("kma", "EXTERNAL_API_ERROR", "domain", "API_RESULT_CODE_10_RANGE"),
    ]
    profiles = [_profile("bbc", "news"), _profile("reddit", "community"), _profile("kma", "domain")]
    gaps = build_gap_matrix(states, profiles)
    ids = {g.source_id for g in gaps}
    assert ids == {"kma"}  # ready/excluded 제외


def test_summarize_gaps_counts():
    states = [_state("kma", "EXTERNAL_API_ERROR", "domain", "API_RESULT_CODE_10_RANGE"),
              _state("its", "NOT_SERVICE_USEFUL", "domain")]
    profiles = [_profile("kma", "domain"), _profile("its", "domain")]
    s = summarize_gaps(build_gap_matrix(states, profiles))
    assert s["targets"] == 2 and s["rescuable"] == 2
