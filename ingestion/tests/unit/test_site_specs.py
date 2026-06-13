from __future__ import annotations

import pytest

from ingestion.probes.site_specs import SiteSpec, load_site_specs


def test_load_site_specs_returns_dict():
    specs = load_site_specs()
    assert isinstance(specs, dict)


def test_seven_sites_present():
    specs = load_site_specs()
    expected = {
        "signal_bz",
        "google_trending_now",
        "google_trends_explore",
        "dcinside",
        "fmkorea",
        "krx_kind",
        "eu_press_corner",
    }
    assert expected <= set(specs.keys()), f"Missing sites: {expected - set(specs.keys())}"


def test_signal_bz_official_is_false():
    specs = load_site_specs()
    assert specs["signal_bz"].official is False


def test_google_trending_now_official_is_true():
    specs = load_site_specs()
    assert specs["google_trending_now"].official is True


def test_signal_bz_evidence_level_low():
    specs = load_site_specs()
    assert specs["signal_bz"].evidence_level == "low"


def test_google_trending_now_evidence_level():
    specs = load_site_specs()
    assert specs["google_trending_now"].evidence_level == "low_to_medium"


def test_krx_kind_is_deferred():
    specs = load_site_specs()
    assert specs["krx_kind"].deferred is True


def test_eu_press_corner_is_live():
    """eu_press_corner was validated LIVE_SUCCESS on 2026-06-03; deferred=False."""
    specs = load_site_specs()
    assert specs["eu_press_corner"].deferred is False


def test_non_deferred_sites_have_selectors():
    specs = load_site_specs()
    live_sites = [s for s in specs.values() if not s.deferred]
    for spec in live_sites:
        assert spec.selectors, f"{spec.site_id} has no selectors"


def test_site_spec_fields():
    specs = load_site_specs()
    spec = specs["signal_bz"]
    assert isinstance(spec, SiteSpec)
    assert spec.site_id == "signal_bz"
    assert spec.layer == "fast_signal"
    assert spec.collection_method == "playwright"
    assert spec.start_url.startswith("https://")
    assert spec.max_items_default > 0
    assert spec.min_interval_minutes > 0


def test_signal_bz_start_url():
    specs = load_site_specs()
    assert "signal.bz" in specs["signal_bz"].start_url


def test_google_trending_now_url_has_region_template():
    specs = load_site_specs()
    assert "{region}" in specs["google_trending_now"].start_url
