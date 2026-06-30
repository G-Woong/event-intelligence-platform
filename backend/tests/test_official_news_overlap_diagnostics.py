"""ADR#91 §11 — official_news_overlap_diagnostics 테스트(entity/action/date/canonical/published/role/window 차원 분해).

차원 테스트는 entity/action 토큰을 직접 주입해 tokenizer 의존성을 제거(결정론). seed→token 도출 경로는 별도 1개로 검증.
모든 진단은 score 0·truth 0·reviewer/public 비노출."""
from __future__ import annotations

from backend.app.tools.live_no_yield_taxonomy import (
    TX_DATE_PROXIMITY_FAILED,
    TX_NO_ACTION_OVERLAP,
    TX_NO_ENTITY_OVERLAP,
)
from backend.app.tools.official_news_overlap_diagnostics import (
    DIM_ACTION,
    DIM_CANONICAL,
    DIM_DATE_PROXIMITY,
    DIM_ENTITY,
    DIM_FREEZE_ARTIFACT,
    DIM_IN_WINDOW,
    DIM_PUBLISHED_AT,
    DIM_SOURCE_ROLE,
    OVERLAP_CANONICAL_MISSING,
    OVERLAP_DATE_PROXIMITY_FAILED,
    OVERLAP_FREEZE_ARTIFACT_UNSAFE,
    OVERLAP_NO_ACTION_OVERLAP,
    OVERLAP_NO_ENTITY_OVERLAP,
    OVERLAP_NOT_RUN,
    OVERLAP_OUT_OF_WINDOW,
    OVERLAP_PUBLISHED_AT_MISSING,
    OVERLAP_SATISFIED,
    OVERLAP_SOURCE_ROLE_INVALID,
    build_official_news_overlap_diagnostics,
    diagnose_official_news_overlap,
    sanitized_overlap_diagnostics,
)

_ENTITY = frozenset({"securities", "commission"})
_ACTION = frozenset({"enforcement", "penalty"})


def _good_candidate(**over) -> dict:
    """모든 차원을 통과하는 bridge candidate(테스트가 한 차원만 깬다)."""
    c = {
        "shared_tokens": ["securities", "commission", "enforcement", "penalty"],
        "date_proximity_days": 0,
        "both_canonical_present": True,
        "both_published_present": True,
        "source_role_official": "official",
        "source_role_news": "news",
        "official_in_window": True,
        "news_in_window": True,
        "same_event_asserted": False,
        "merge_allowed": False,
    }
    c.update(over)
    return c


def _diag(candidate: dict) -> dict:
    return diagnose_official_news_overlap(candidate=candidate, entity_tokens=_ENTITY, action_tokens=_ACTION)


# ── 모든 차원 통과 → satisfied ──────────────────────────────────────────────────────────────────────────────
def test_all_dimensions_satisfied():
    d = _diag(_good_candidate())
    assert d["overlap_diagnostic_status"] == OVERLAP_SATISFIED
    assert d["blocked_dimension"] == ""
    assert d["overlap_dimensions_satisfied"] is True


# ── §19-28: entity overlap missing classified ───────────────────────────────────────────────────────────────
def test_28_entity_overlap_missing():
    d = _diag(_good_candidate(shared_tokens=["enforcement", "penalty"]))  # entity 토큰 없음.
    assert d["overlap_diagnostic_status"] == OVERLAP_NO_ENTITY_OVERLAP
    assert d["blocked_dimension"] == DIM_ENTITY
    assert d["entity_overlap"] is False
    assert d["missing_entity_tokens"] == ["commission", "securities"]
    assert d["overlap_failure_taxonomy_key"] == TX_NO_ENTITY_OVERLAP


# ── §19-29: action overlap missing classified ───────────────────────────────────────────────────────────────
def test_29_action_overlap_missing():
    d = _diag(_good_candidate(shared_tokens=["securities", "commission"]))  # action 토큰 없음.
    assert d["overlap_diagnostic_status"] == OVERLAP_NO_ACTION_OVERLAP
    assert d["blocked_dimension"] == DIM_ACTION
    assert d["action_overlap"] is False
    assert d["overlap_failure_taxonomy_key"] == TX_NO_ACTION_OVERLAP


# ── §19-30: date proximity failed classified ────────────────────────────────────────────────────────────────
def test_30_date_proximity_failed():
    d = _diag(_good_candidate(date_proximity_days=5))  # tolerance(1) 초과.
    assert d["overlap_diagnostic_status"] == OVERLAP_DATE_PROXIMITY_FAILED
    assert d["blocked_dimension"] == DIM_DATE_PROXIMITY
    assert d["date_close"] is False
    assert d["overlap_failure_taxonomy_key"] == TX_DATE_PROXIMITY_FAILED


# ── §19-31: canonical missing classified ────────────────────────────────────────────────────────────────────
def test_31_canonical_missing():
    d = _diag(_good_candidate(both_canonical_present=False))
    assert d["overlap_diagnostic_status"] == OVERLAP_CANONICAL_MISSING
    assert d["blocked_dimension"] == DIM_CANONICAL


# ── §19-32: published_at missing classified ─────────────────────────────────────────────────────────────────
def test_32_published_at_missing():
    d = _diag(_good_candidate(both_published_present=False))
    assert d["overlap_diagnostic_status"] == OVERLAP_PUBLISHED_AT_MISSING
    assert d["blocked_dimension"] == DIM_PUBLISHED_AT


# ── §19-33: source role invalid classified ──────────────────────────────────────────────────────────────────
def test_33_source_role_invalid():
    d = _diag(_good_candidate(source_role_news="community"))  # news 역할 아님.
    assert d["overlap_diagnostic_status"] == OVERLAP_SOURCE_ROLE_INVALID
    assert d["blocked_dimension"] == DIM_SOURCE_ROLE
    assert d["source_role_valid"] is False


# ── §19-34: freeze artifact unsafe classified ───────────────────────────────────────────────────────────────
def test_34_freeze_artifact_unsafe():
    d = _diag(_good_candidate(same_event_asserted=True))  # truth 주장 → unsafe.
    assert d["overlap_diagnostic_status"] == OVERLAP_FREEZE_ARTIFACT_UNSAFE
    assert d["blocked_dimension"] == DIM_FREEZE_ARTIFACT
    assert d["freeze_artifact_safe"] is False


# ── out-of-window 차원 ──────────────────────────────────────────────────────────────────────────────────────
def test_out_of_window_classified():
    d = _diag(_good_candidate(news_in_window=False))
    assert d["overlap_diagnostic_status"] == OVERLAP_OUT_OF_WINDOW
    assert d["blocked_dimension"] == DIM_IN_WINDOW


# ── §19-35: diagnostic not exposed to reviewer/public ───────────────────────────────────────────────────────
def test_35_not_exposed_to_reviewer_or_public():
    d = _diag(_good_candidate())
    assert d["reviewer_facing"] is False
    assert d["public_exposed"] is False
    assert d["is_truth"] is False
    assert d["composite_score_exposed"] is False
    assert d["same_event_asserted"] is False
    assert d["merge_allowed"] is False
    for forbidden in ("score", "rationale", "predicted_status"):
        assert forbidden not in d


# ── seed → token 도출 경로(bridge tokenizer 재사용) ───────────────────────────────────────────────────────────
def test_seed_token_derivation():
    seed = {"agency_or_entity": "securities commission", "action_phrase": "enforcement penalty"}
    d = diagnose_official_news_overlap(candidate=_good_candidate(), seed=seed)
    assert d["overlap_diagnostic_status"] == OVERLAP_SATISFIED
    assert d["entity_overlap"] is True
    assert d["action_overlap"] is True


# ── aggregate: no candidates → not_run(frontier 안전) ─────────────────────────────────────────────────────────
def test_aggregate_no_candidates_not_run():
    out = build_official_news_overlap_diagnostics()
    assert out["overlap_diagnostic_status"] == OVERLAP_NOT_RUN
    assert out["blocked_dimension"] == ""
    assert out["diagnosed_pair_count"] == 0


# ── aggregate: satisfied 후보 존재 → satisfied ────────────────────────────────────────────────────────────────
def test_aggregate_satisfied():
    out = build_official_news_overlap_diagnostics(
        candidates=[_good_candidate()],
        seed={"agency_or_entity": "securities commission", "action_phrase": "enforcement penalty"})
    assert out["overlap_diagnostic_status"] == OVERLAP_SATISFIED
    assert out["overlap_satisfied_count"] == 1


# ── aggregate: 전부 entity 결손 → 대표 blocked=entity ─────────────────────────────────────────────────────────
def test_aggregate_dominant_blocked_dimension():
    cands = [_good_candidate(shared_tokens=["enforcement", "penalty"]) for _ in range(3)]
    out = build_official_news_overlap_diagnostics(
        candidates=cands, seed={"agency_or_entity": "securities commission", "action_phrase": "enforcement penalty"})
    assert out["overlap_diagnostic_status"] == OVERLAP_NO_ENTITY_OVERLAP
    assert out["blocked_dimension"] == DIM_ENTITY
    assert out["overlap_satisfied_count"] == 0


# ── sanitized 투영(token 목록 제외) ──────────────────────────────────────────────────────────────────────────
def test_sanitized_projection():
    out = build_official_news_overlap_diagnostics()
    s = sanitized_overlap_diagnostics(out)
    assert set(s) == {"overlap_diagnostic_status", "overlap_blocked_dimension", "diagnosed_pair_count",
                      "overlap_satisfied_count", "next_action"}
    assert "missing_entity_tokens" not in s
