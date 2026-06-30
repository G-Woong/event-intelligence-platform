"""ADR#91 §11 — official×news overlap diagnostics (no-yield 를 차원별로 분해·operator 가 payload/query 를 고칠 수 있게).

문제(ADR#90 Q7/Q8·R-LiveNoYieldTaxonomyBlindspot): bridge(`official_news_role_bridge`)는 entity/action 을 **결합 토큰
게이트**(`_title_tokens(official) ∩ _title_tokens(news) ≥ 2`)로 한 덩어리 판정하고, live engine 은 실패를 umbrella
`no_official_news_overlap` 하나로 접는다. operator 는 "후보 없음" 만 보고 *무엇을* (entity? action? date? canonical?
window?) 고쳐야 할지 알 수 없다.

이 모듈은 그 결합 게이트를 **차원별 진단**으로 분해한다(재구현 0·bridge feature 재사용):
  - bridge candidate dict 가 이미 주는 4차원(`date_proximity_days`·`both_canonical_present`·`both_published_present`·
    `source_role_*`)을 **그대로 재사용**하고,
  - 빠진 2차원(entity_overlap·action_overlap)만 **seed 토큰 ∩ bridge `shared_tokens`**(이미 official∩news 교집합)으로
    partition 하며,
  - 세 핵심 차원(entity/action/date)의 verdict 는 기존 taxonomy `classify_overlap_failure` 를 호출해 얻는다(매퍼 재사용).

절대 불변(§11): 진단 score 는 truth 가 아니다 · reviewer-facing/public artifact 에 score/rationale 노출 0 ·
`same_event_asserted=False` · `merge_allowed=False` · token 은 정규화 entity/action proxy(제목 전문/body 0·bridge
`shared_tokens` 와 동일 표면). 진단은 collection-stage operator 도구이지 reviewer worklist 가 아니다.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from typing import Optional

from backend.app.tools.live_no_yield_taxonomy import classify_overlap_failure
from backend.app.tools.official_news_role_bridge import (
    _DEFAULT_DATE_TOLERANCE_DAYS,
    _NEWS_ROLES,
    _OFFICIAL_ROLES,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe
from ingestion.orchestration.cross_source_dedup import _title_tokens

OPERATION_NAME = "official_news_overlap_diagnostics"

# overlap_diagnostic_status(차원 진단 결과·collection-stage·operator-facing).
OVERLAP_NOT_RUN = "not_run"
OVERLAP_SOURCE_ROLE_INVALID = "source_role_invalid"
OVERLAP_FREEZE_ARTIFACT_UNSAFE = "freeze_artifact_unsafe"
OVERLAP_CANONICAL_MISSING = "canonical_missing"
OVERLAP_PUBLISHED_AT_MISSING = "published_at_missing"
OVERLAP_OUT_OF_WINDOW = "out_of_window"
OVERLAP_DATE_PROXIMITY_FAILED = "date_proximity_failed"
OVERLAP_NO_ENTITY_OVERLAP = "no_entity_overlap"
OVERLAP_NO_ACTION_OVERLAP = "no_action_overlap"
OVERLAP_SATISFIED = "overlap_dimensions_satisfied"

# blocked_dimension 어휘(§11 차원 이름).
DIM_SOURCE_ROLE = "source_role_valid"
DIM_FREEZE_ARTIFACT = "freeze_artifact_safety"
DIM_CANONICAL = "canonical_present"
DIM_PUBLISHED_AT = "published_at_present"
DIM_IN_WINDOW = "in_window_status"
DIM_DATE_PROXIMITY = "date_proximity"
DIM_ENTITY = "entity_overlap"
DIM_ACTION = "action_overlap"

# 우선순위 ladder: 첫 실패 차원이 blocked_dimension(구조적 결손 → 토큰 overlap 순).
_LADDER: tuple[tuple[str, str], ...] = (
    (DIM_SOURCE_ROLE, OVERLAP_SOURCE_ROLE_INVALID),
    (DIM_FREEZE_ARTIFACT, OVERLAP_FREEZE_ARTIFACT_UNSAFE),
    (DIM_CANONICAL, OVERLAP_CANONICAL_MISSING),
    (DIM_PUBLISHED_AT, OVERLAP_PUBLISHED_AT_MISSING),
    (DIM_IN_WINDOW, OVERLAP_OUT_OF_WINDOW),
    (DIM_DATE_PROXIMITY, OVERLAP_DATE_PROXIMITY_FAILED),
    (DIM_ENTITY, OVERLAP_NO_ENTITY_OVERLAP),
    (DIM_ACTION, OVERLAP_NO_ACTION_OVERLAP),
)


def _tokens(text: object) -> frozenset[str]:
    """seed 필드 → 정규화 토큰(bridge 와 동일 tokenizer 재사용·None 안전)."""
    return _title_tokens(str(text or ""))


def _query_adjustment(blocked: str, missing_entity: list[str], missing_action: list[str]) -> str:
    """blocked_dimension → operator 가 payload/query 를 어떻게 고칠지 한 줄."""
    if blocked == DIM_SOURCE_ROLE:
        return "the pair is not official×news — ensure the official record is a regulatory source and the news a news/article source"
    if blocked == DIM_FREEZE_ARTIFACT:
        return "the candidate asserts truth (same_event/merge) — reject it; a bridge candidate is a reviewer worklist only"
    if blocked == DIM_CANONICAL:
        return "one side lacks a canonical URL — pick records that carry a canonical link"
    if blocked == DIM_PUBLISHED_AT:
        return "one side lacks a published date — pick records with a published_at date"
    if blocked == DIM_IN_WINDOW:
        return "a record is out of the date window — correct the occurrence window or use a window-honoring source"
    if blocked == DIM_DATE_PROXIMITY:
        return "the official and news dates are too far apart — verify the actual occurrence date"
    if blocked == DIM_ENTITY:
        return f"the named entity token(s) {missing_entity} are not shared by both records — refine agency_or_entity or news_query"
    if blocked == DIM_ACTION:
        return f"the action token(s) {missing_action} are not shared by both records — refine action_phrase or news_query"
    return "all overlap dimensions are satisfied — route to the reviewer worklist (not truth)"


def diagnose_official_news_overlap(
    *, candidate: dict, seed: Optional[dict] = None,
    entity_tokens: Optional[frozenset[str]] = None, action_tokens: Optional[frozenset[str]] = None,
    date_tolerance_days: int = _DEFAULT_DATE_TOLERANCE_DAYS,
) -> dict:
    """단일 bridge candidate × seed → 차원별 overlap 진단(PURE·score 0·truth 0).

    entity/action 토큰은 seed(agency_or_entity / action_phrase)에서 도출하거나 직접 주입한다. entity_overlap/action_overlap
    은 seed 토큰 ∩ candidate `shared_tokens`(official∩news 교집합)으로 partition 하고, date/canonical/published/role/window 는
    bridge feature 를 재사용한다. 세 핵심 차원 verdict 는 taxonomy `classify_overlap_failure` 로 얻는다(매퍼 재사용)."""
    if entity_tokens is None:
        entity_tokens = _tokens((seed or {}).get("agency_or_entity"))
    if action_tokens is None:
        action_tokens = _tokens((seed or {}).get("action_phrase"))
    shared = set(candidate.get("shared_tokens") or [])
    entity_hits = sorted(entity_tokens & shared)
    action_hits = sorted(action_tokens & shared)
    entity_overlap = bool(entity_hits)
    action_overlap = bool(action_hits)
    # agency_overlap: named entity 전체가 양측 공유(stricter)인가 — entity_overlap(any) 의 정밀 보강.
    agency_overlap = bool(entity_tokens) and entity_tokens <= shared

    date_proximity_days = candidate.get("date_proximity_days")
    date_close = date_proximity_days is not None and int(date_proximity_days) <= max(0, date_tolerance_days)
    source_role_valid = (candidate.get("source_role_official") in _OFFICIAL_ROLES
                         and candidate.get("source_role_news") in _NEWS_ROLES)
    canonical_present = bool(candidate.get("both_canonical_present"))
    published_at_present = bool(candidate.get("both_published_present"))
    in_window = (candidate.get("official_in_window") is True and candidate.get("news_in_window") is True)
    # freeze artifact 안전: candidate 가 truth(same_event/merge)를 주장하면 unsafe(routing 표식이어야 함).
    freeze_artifact_safe = (candidate.get("same_event_asserted") is not True
                            and candidate.get("merge_allowed") is not True)

    dim_pass = {
        DIM_SOURCE_ROLE: source_role_valid,
        DIM_FREEZE_ARTIFACT: freeze_artifact_safe,
        DIM_CANONICAL: canonical_present,
        DIM_PUBLISHED_AT: published_at_present,
        DIM_IN_WINDOW: in_window,
        DIM_DATE_PROXIMITY: date_close,
        DIM_ENTITY: entity_overlap,
        DIM_ACTION: action_overlap,
    }
    blocked_dimension, status = "", OVERLAP_SATISFIED
    for dim, st in _LADDER:
        if not dim_pass[dim]:
            blocked_dimension, status = dim, st
            break

    missing_entity = sorted(entity_tokens - shared)
    missing_action = sorted(action_tokens - shared)
    # 세 핵심 차원 verdict 는 taxonomy 매퍼 재사용(과대단정 0).
    overlap_failure = classify_overlap_failure(
        entity_overlap=entity_overlap, action_overlap=action_overlap, date_close=date_close)
    out = {
        "operation_name": OPERATION_NAME,
        "overlap_diagnostic_status": status,
        "blocked_dimension": blocked_dimension,
        "overlap_dimensions_satisfied": status == OVERLAP_SATISFIED,
        # 차원 boolean.
        "source_role_valid": source_role_valid,
        "freeze_artifact_safe": freeze_artifact_safe,
        "canonical_present": canonical_present,
        "published_at_present": published_at_present,
        "in_window_status": in_window,
        "date_close": date_close,
        "entity_overlap": entity_overlap,
        "action_overlap": action_overlap,
        "agency_overlap": agency_overlap,
        # 진단 수치(truth score 아님·token overlap count).
        "entity_overlap_count": len(entity_hits),
        "action_overlap_count": len(action_hits),
        "date_proximity_days": date_proximity_days,
        "missing_entity_tokens": missing_entity,
        "missing_action_tokens": missing_action,
        # taxonomy 매퍼 verdict(entity/action/date).
        "overlap_failure_taxonomy_key": overlap_failure["taxonomy_key"],
        # operator-facing 조정 제안.
        "operator_query_adjustment": _query_adjustment(blocked_dimension, missing_entity, missing_action),
        "official_query_adjustment": "adjust official_query (Federal Register) to match the agency/action wording",
        "news_query_adjustment": "adjust news_query to include the entity/action terms the official record uses",
        "source_adjustment": ("Guardian/NYT may not honor the date window (R-ProviderDateWindowFidelity) — "
                              "consider a window-honoring news source") if blocked_dimension in (DIM_IN_WINDOW,)
                             else "official=Federal Register (window-honoring); news=Guardian/NYT (enforce_window=True)",
        # ── 불변 경계(진단 ≠ truth·reviewer/public 비노출) ──
        "is_truth": False,
        "same_event_asserted": False,
        "merge_allowed": False,
        "reviewer_facing": False,
        "public_exposed": False,
        "composite_score_exposed": False,
    }
    _assert_pii_safe(out, _path="official_news_overlap_diagnostic_output")
    return out


def build_official_news_overlap_diagnostics(
    *, candidates: Optional[list[dict]] = None, seed: Optional[dict] = None,
    date_tolerance_days: int = _DEFAULT_DATE_TOLERANCE_DAYS,
) -> dict:
    """bridge candidate 목록 × seed → 집계 진단(no candidates → not_run·frontier 안전).

    후보가 없으면 not_run(현 live 미실행 상태). 후보가 있으면 차원별로 분해해, 하나라도 모든 차원 충족이면 satisfied,
    아니면 가장 흔한 blocked 차원을 대표로 보고한다(operator 가 무엇을 고칠지). 출력은 aggregate status/dimension/count 만."""
    cands = list(candidates or [])
    if not cands:
        out = {
            "operation_name": OPERATION_NAME,
            "overlap_diagnostic_status": OVERLAP_NOT_RUN,
            "blocked_dimension": "",
            "diagnosed_pair_count": 0,
            "overlap_satisfied_count": 0,
            "blocked_dimension_counts": {},
            "is_truth": False,
            "same_event_asserted": False,
            "merge_allowed": False,
            "reviewer_facing": False,
            "next_action": ("no official×news bridge candidates to diagnose — run a bounded live with a "
                            "confirmed operator payload to produce candidates"),
        }
        _assert_pii_safe(out, _path="official_news_overlap_diagnostics_not_run")
        return out

    diags = [diagnose_official_news_overlap(candidate=c, seed=seed, date_tolerance_days=date_tolerance_days)
             for c in cands]
    satisfied = [d for d in diags if d["overlap_diagnostic_status"] == OVERLAP_SATISFIED]
    blocked_counts = Counter(d["blocked_dimension"] for d in diags if d["blocked_dimension"])
    if satisfied:
        status, blocked_dimension = OVERLAP_SATISFIED, ""
        nxt = (f"{len(satisfied)}/{len(diags)} candidate(s) satisfy all overlap dimensions — route to the "
               f"reviewer worklist (bridge candidate is not same-event truth)")
    else:
        top_dim, _ = blocked_counts.most_common(1)[0]
        rep = next(d for d in diags if d["blocked_dimension"] == top_dim)
        status, blocked_dimension = rep["overlap_diagnostic_status"], top_dim
        nxt = rep["operator_query_adjustment"]
    out = {
        "operation_name": OPERATION_NAME,
        "overlap_diagnostic_status": status,
        "blocked_dimension": blocked_dimension,
        "diagnosed_pair_count": len(diags),
        "overlap_satisfied_count": len(satisfied),
        "blocked_dimension_counts": dict(blocked_counts),
        "is_truth": False,
        "same_event_asserted": False,
        "merge_allowed": False,
        "reviewer_facing": False,
        "next_action": nxt,
    }
    _assert_pii_safe(out, _path="official_news_overlap_diagnostics_output")
    return out


def sanitized_overlap_diagnostics(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(per-pair token 필드 제외).

    status/dimension/count + next_action 만. next_action 은 산문이며 정규화 entity/action token 을 *언급* 할 수 있으나
    (bridge `shared_tokens` 와 동일 표면·secret/PII 0), frontier 는 overlap next_action 을 소비하지 않는다(status +
    blocked_dimension 만 노출)."""
    return {
        "overlap_diagnostic_status": out["overlap_diagnostic_status"],
        "overlap_blocked_dimension": out.get("blocked_dimension", ""),
        "diagnosed_pair_count": int(out.get("diagnosed_pair_count") or 0),
        "overlap_satisfied_count": int(out.get("overlap_satisfied_count") or 0),
        "next_action": out.get("next_action", ""),
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#91 official×news overlap diagnostics (no-yield 를 entity/action/date/canonical/published/role/"
                     "window 차원으로 분해; score 0·truth 0·reviewer/public 비노출·bridge feature 재사용)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(현 live 미실행 → not_run).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_official_news_overlap_diagnostics()
    if ns.json:
        print(json.dumps(sanitized_overlap_diagnostics(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['overlap_diagnostic_status']} "
          f"blocked_dimension={out['blocked_dimension'] or '(none)'}")
    print(f"- diagnosed_pairs={out['diagnosed_pair_count']} satisfied={out['overlap_satisfied_count']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
