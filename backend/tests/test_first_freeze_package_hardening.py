"""ADR#92 §11 — first freeze package hardening tests.

검증: score/rationale/predicted_status/same_event/raw body/reviewer PII 가 섞인 artifact 는 unsafe·official/news role
설명 없으면 unsafe·canonical/published_at 없으면 unsafe·safe artifact 는 accept·production_gold_count 불변.
"""
from __future__ import annotations

from backend.app.tools.first_freeze_package_hardening import (
    FH_NO_ARTIFACT,
    FH_SAFE,
    FH_UNSAFE,
    build_first_freeze_package_hardening,
    sanitized_first_freeze_package_hardening,
)


def _safe_pair() -> dict:
    return {
        "pair_id": "oxn_0001",
        "official_record": {
            "record_type": "official_document",
            "source_id": "federal_register",
            "canonical_url": "https://www.federalregister.gov/documents/2026/06/25/epa-rule",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA final rule on greenhouse gas emissions standards",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "guardian",
            "canonical_url": "https://www.theguardian.com/environment/2026/jun/25/epa-emissions",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "EPA tightens vehicle emissions standards",
        },
        "shared_tokens": ["epa", "emissions"],
        "date_proximity_days": 0,
    }


# ── 38. safe artifact accepted ──
def test_safe_artifact_accepted():
    out = build_first_freeze_package_hardening(artifact=_safe_pair())
    assert out["freeze_package_hardening_status"] == FH_SAFE
    assert out["freeze_artifact_safe"] is True
    assert out["reviewer_instruction_ready"] is True
    assert out["official_news_role_explanation_present"] is True
    assert out["canonical_present"] is True
    assert out["published_at_present"] is True
    assert out["source_role_present"] is True
    assert out["record_schema_clean"] is True
    assert out["blocked_reason"] == ""


# ── 31. score in artifact rejected ──
def test_score_in_artifact_rejected():
    art = _safe_pair()
    art["official_record"]["score"] = 0.97
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_package_hardening_status"] == FH_UNSAFE
    assert out["score_hidden"] is False
    assert "score" in out["leaked_forbidden_keys"]


# ── 32. rationale in artifact rejected ──
def test_rationale_in_artifact_rejected():
    art = _safe_pair()
    art["news_record"]["rationale"] = "looks like the same event"
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["rationale_hidden"] is False


# ── 33. predicted_status in artifact rejected ──
def test_predicted_status_in_artifact_rejected():
    art = _safe_pair()
    art["predicted_status"] = "same_event"
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["predicted_status_hidden"] is False


# ── 34. same_event truth in artifact rejected ──
def test_same_event_truth_in_artifact_rejected():
    art = _safe_pair()
    art["same_event_asserted"] = True
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["artifact_asserts_same_event"] is True


# ── 35. raw body in artifact rejected ──
def test_raw_body_in_artifact_rejected():
    art = _safe_pair()
    art["official_record"]["body"] = "full official document text ..."
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["raw_body_hidden"] is False


# ── 36. reviewer PII rejected ──
def test_reviewer_pii_rejected():
    art = _safe_pair()
    art["news_record"]["email"] = "reviewer@example.com"
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["reviewer_pii_hidden"] is False


# ── 37. missing official/news role explanation rejected ──
def test_missing_role_explanation_rejected():
    art = _safe_pair()
    del art["news_record"]
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_package_hardening_status"] == FH_NO_ARTIFACT


def test_missing_source_role_indicator_rejected():
    art = _safe_pair()
    del art["official_record"]["record_type"]  # no role indicator
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["source_role_present"] is False


def test_missing_canonical_rejected():
    art = _safe_pair()
    art["news_record"]["canonical_url"] = ""
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["canonical_present"] is False


# ── 39. production_gold_count unchanged ──
def test_production_gold_count_unchanged_when_equal():
    out = build_first_freeze_package_hardening(
        artifact=_safe_pair(), production_gold_count_before=0, production_gold_count_after=0)
    assert out["production_gold_count_unchanged"] is True
    assert out["production_gold_count"] == 0
    assert out["freeze_artifact_safe"] is True


def test_production_gold_count_changed_rejected():
    out = build_first_freeze_package_hardening(
        artifact=_safe_pair(), production_gold_count_before=0, production_gold_count_after=5)
    assert out["production_gold_count_unchanged"] is False
    assert out["freeze_artifact_safe"] is False


# ── Finding A — non-allowlisted record field (value-level PII under arbitrary key) rejected ──
def test_non_allowlisted_record_field_rejected():
    art = _safe_pair()
    art["official_record"]["raw_text"] = "full official document body that should be stripped"
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["record_schema_clean"] is False
    assert "raw_text" in out["non_allowlisted_record_fields"]["official"]


def test_value_level_pii_under_arbitrary_key_rejected():
    # forbidden-key 가드(key명 전용)는 "note" 키를 못 잡지만 allowlist 가 잡는다(값-레벨 PII 차단).
    art = _safe_pair()
    art["news_record"]["note"] = "contact reviewer at reviewer@example.com"
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert "note" in out["non_allowlisted_record_fields"]["news"]


# ── Finding B — partial artifact with a leak surfaces the leak (still NO_ARTIFACT/unsafe) ──
def test_partial_artifact_with_leak_surfaces_leak():
    art = _safe_pair()
    del art["news_record"]
    art["official_record"]["score"] = 0.9
    out = build_first_freeze_package_hardening(artifact=art)
    assert out["freeze_artifact_safe"] is False
    assert out["freeze_package_hardening_status"] == FH_NO_ARTIFACT
    assert any("score" in b for b in out["all_blockers"])


# ── no artifact → FH_NO_ARTIFACT ──
def test_no_artifact():
    out = build_first_freeze_package_hardening(artifact=None)
    assert out["freeze_package_hardening_status"] == FH_NO_ARTIFACT
    assert out["freeze_artifact_safe"] is False


# ── invariants: module asserts no truth/merge/gold ──
def test_module_invariants():
    out = build_first_freeze_package_hardening(artifact=_safe_pair())
    assert out["same_event_asserted"] is False
    assert out["merge_allowed"] is False
    assert out["freeze_is_reviewer_worklist_only"] is True
    assert out["network_invoked"] is False


# ── sanitized projection (frontier 용) ──
def test_sanitized_projection_keys():
    out = build_first_freeze_package_hardening(artifact=_safe_pair())
    s = sanitized_first_freeze_package_hardening(out)
    assert set(s.keys()) == {
        "freeze_package_hardening_status", "freeze_artifact_safe", "blocked_reason",
        "production_gold_count_unchanged",
    }
