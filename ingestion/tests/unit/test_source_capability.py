"""G-3: SourceCapability 선언 — 4개 target 능력 + 접근자."""
from __future__ import annotations

from ingestion.orchestration.source_capability import (
    POLICY_HIGH,
    POLICY_LOW,
    all_capabilities,
    capability_for,
)


def test_four_targets_present():
    ids = {c.source_id for c in all_capabilities()}
    assert {"dcinside", "culture_info", "product_hunt", "gdelt"}.issubset(ids)


def test_dcinside_high_sensitivity_static_detail():
    cap = capability_for("dcinside")
    assert cap.policy_sensitivity == POLICY_HIGH      # robots/ToS/PII 민감
    assert cap.supports_static_html and cap.supports_detail
    assert cap.requires_key is False


def test_culture_info_official_api_requires_key():
    cap = capability_for("culture_info")
    assert cap.supports_api and cap.requires_key
    assert cap.expected_record_type == "official_record"
    assert cap.policy_sensitivity == POLICY_LOW


def test_product_hunt_api_community():
    cap = capability_for("product_hunt")
    assert cap.supports_api and cap.requires_key
    assert cap.expected_record_type == "community_signal"


def test_gdelt_no_key_has_rate_limit_policy():
    cap = capability_for("gdelt")
    assert cap.requires_key is False
    assert cap.rate_limit_policy_id == "gdelt_host"


def test_unknown_source_returns_none():
    assert capability_for("does_not_exist") is None
