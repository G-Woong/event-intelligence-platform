"""G-3: EvidenceGate — synthetic/local evidence 거부, 실 증거만 ready 허용."""
from __future__ import annotations

from ingestion.orchestration.evidence_gate import evaluate_evidence, gate_records


def _rec(url, t="2026-06-15T07:01:00Z", sig="community_signal", canonical=None):
    return {"record_type": "community_signal", "source_id": "x",
            "source_url_or_evidence": url, "canonical_url": canonical or url,
            "published_at_or_observed_at": t, "body_state_or_signal": sig}


def test_real_external_url_ready():
    g = evaluate_evidence(source_id="product_hunt",
                          record=_rec("https://www.producthunt.com/products/novu"))
    assert g.ready_allowed and g.has_external_url and g.has_time_anchor


def test_synthetic_producthunt_slug_rejected():
    g = evaluate_evidence(source_id="product_hunt",
                          record=_rec("https://www.producthunt.com/posts/some-name", canonical=None))
    assert g.ready_allowed is False
    assert "SYNTHETIC_OR_LOCAL_EVIDENCE" in g.downgrade_reason


def test_dead_culture_detailview_rejected():
    g = evaluate_evidence(source_id="culture_info",
                          record=_rec("https://www.culture.go.kr/wantU/detailView.do?seq=315929"))
    assert g.ready_allowed is False


def test_local_path_rejected():
    for bad in ("file:///tmp/x.json", "C:\\Users\\x\\out.json", "/Users/me/outputs/a.json"):
        g = evaluate_evidence(source_id="x", record=_rec(bad))
        assert g.ready_allowed is False


def test_missing_time_anchor_not_ready():
    g = evaluate_evidence(source_id="x",
                          record=_rec("https://example.com/a", t=None))
    assert g.ready_allowed is False
    assert "NO_TIME_ANCHOR" in g.downgrade_reason


def test_gate_records_requires_at_least_one_ready():
    good = _rec("https://example.com/a")
    bad = _rec("https://www.producthunt.com/posts/synthetic")
    assert gate_records("x", [good, bad])["ready_allowed"] is True
    assert gate_records("x", [bad])["ready_allowed"] is False
    assert gate_records("x", [])["ready_allowed"] is False
