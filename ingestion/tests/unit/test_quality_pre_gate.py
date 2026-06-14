"""Phase E-0: 품질 사전 게이트 (pass/hold/reject) 검증."""
from __future__ import annotations

from ingestion.orchestration.article_candidate import ArticleCandidate
from ingestion.orchestration.quality_pre_gate import (
    compute_duplicate_key,
    evaluate_pre_gate,
    load_publication_policy,
    normalize_published_at,
    publication_policy_for,
)

_CLEAN_BODY = (
    "This is a synthetic news body written purely to exceed the two hundred character "
    "full body threshold so the body state classifier reports a present body. It avoids "
    "any boilerplate marker words and is not taken from any real article whatsoever here."
)


def _cand(**kw) -> ArticleCandidate:
    base = dict(
        source_id="bbc", title="Synthetic Title", source_url="https://news.test/a",
        canonical_url="https://news.test/a", raw_artifact_path="x/raw.json",
        body_text=_CLEAN_BODY, body_missing=False,
        collection_status="LIVE_SUCCESS", parser_name="rss",
    )
    base.update(kw)
    return ArticleCandidate(**base)


def test_evidence_present_passes():
    r = evaluate_pre_gate(_cand(), purpose="news", source_group="news")
    assert r.decision == "pass"
    assert r.evidence_ref == "x/raw.json"


def test_no_evidence_rejects():
    r = evaluate_pre_gate(
        _cand(raw_artifact_path=None, extracted_text_ref=None),
        purpose="news", source_group="news",
    )
    assert r.decision == "reject"
    assert "no_evidence_ref" in r.reasons


def test_no_title_but_structured_signal_passes():
    r = evaluate_pre_gate(
        _cand(title=None, body_text=None, body_missing=False,
              numeric_payload_exempt=True),
        purpose="numeric", source_group="market",
    )
    assert r.decision == "pass"


def test_no_title_no_structured_signal_rejects():
    r = evaluate_pre_gate(
        _cand(title=None, body_text=None, body_missing=True),
        purpose="news", source_group="news",
    )
    assert r.decision == "reject"
    assert "no_title_no_structured_signal" in r.reasons


def test_body_present_passes():
    r = evaluate_pre_gate(_cand(), purpose="news", source_group="news")
    assert r.decision == "pass"


def test_snippet_only_holds():
    r = evaluate_pre_gate(
        _cand(body_text=None, summary="short snippet", body_missing=True),
        purpose="news", source_group="news",
    )
    assert r.decision == "hold"
    assert "body_snippet_only" in r.reasons


def test_numeric_exempt_passes():
    r = evaluate_pre_gate(
        _cand(title=None, body_text=None, numeric_payload_exempt=True),
        purpose="numeric", source_group="market",
    )
    assert r.decision == "pass"


def test_parser_error_holds():
    r = evaluate_pre_gate(
        _cand(parse_error="boom", body_text=None), purpose="news", source_group="news",
    )
    assert r.decision == "hold"
    assert "parser_error" in r.reasons


def test_published_at_iso_normalization():
    iso, err = normalize_published_at("Wed, 13 Jun 2026 12:00:00 GMT")
    assert err is None
    assert iso.startswith("2026-06-13T12:00:00")
    iso2, err2 = normalize_published_at("20260613T120000Z")
    assert err2 is None
    assert iso2.startswith("2026-06-13T12:00:00")
    iso3, err3 = normalize_published_at("2026-06-15")
    assert err3 is None and iso3.startswith("2026-06-15")


def test_bad_published_at_holds_with_reason():
    r = evaluate_pre_gate(
        _cand(published_at="not-a-real-date"), purpose="news", source_group="news",
    )
    assert r.decision == "hold"
    assert any(x.startswith("published_at_unparseable") for x in r.reasons)
    assert r.normalized_published_at is None


def test_absent_published_at_is_note_not_hold():
    r = evaluate_pre_gate(_cand(published_at=None), purpose="news", source_group="news")
    assert r.decision == "pass"
    assert "published_at_absent" in r.reasons


def test_boilerplate_heuristic():
    boiler = (
        "Subscribe now. Sign up for our newsletter. This page uses cookies. "
        "All rights reserved."
    )
    r = evaluate_pre_gate(
        _cand(body_text=boiler), purpose="news", source_group="news",
    )
    assert r.boilerplate_risk == "high"
    assert r.decision == "hold"
    assert "boilerplate_suspected" in r.reasons
    # clean body는 low
    clean = evaluate_pre_gate(_cand(), purpose="news", source_group="news")
    assert clean.boilerplate_risk == "low"


def test_preview_only_publication_policy():
    policy = load_publication_policy()
    assert publication_policy_for("serper", policy) == "no_public_preview"
    assert publication_policy_for("bbc", policy) == "preview_only:200"
    assert publication_policy_for("federal_register", policy) == "preview_only:500"


def test_duplicate_key_from_canonical_url():
    k = compute_duplicate_key(_cand(canonical_url="https://news.test/a"))
    assert k is not None and k.startswith("url:")
    # 같은 canonical → 같은 키(dedup 안정성)
    k2 = compute_duplicate_key(_cand(canonical_url="https://news.test/a"))
    assert k == k2


def test_duplicate_key_fallback_from_title_source_time():
    k = compute_duplicate_key(
        _cand(canonical_url=None, title="T", published_at="2026-06-13T00:00:00Z")
    )
    assert k is not None and k.startswith("meta:")
    # 식별 근거가 전혀 없으면 키를 지어내지 않는다
    none_key = compute_duplicate_key(
        _cand(canonical_url=None, title=None, published_at=None)
    )
    assert none_key is None
