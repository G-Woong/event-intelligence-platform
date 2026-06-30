"""ADR#91 §13 — Hot Post gate alignment (Hot Intelligence Post 의 public_readiness 를 R1/R2 + evidence gate 에 결속).

문제(ADR#90 Q13): `hot_intelligence_post_contract.evaluate_hot_post_readiness` 는 merge_gate/official_evidence/
human_label/uncertainty/anchor 만 검사했고, "production gold 가 있는가·news 교차가 있는가·public safety/moderation/
reply policy 가 준비됐는가" 같은 **상위 게이트 결속** 이 빠져 있었다. Hot Post 는 최종 제품 방향이지만 지금 runtime 은
No-Go 이며, public_readiness 는 R1(gold)·R2(MERGE_GATE)·evidence·source-role·community 경계를 *모두* 요구해야 한다.

이 모듈은 그 11개 게이트 요구를 한 곳에서 결속한다(재구현 0·COMPOSE):
  - 기존 `evaluate_hot_post_readiness` 를 호출해 5개(merge_gate/official_evidence/source_role/uncertainty/community-
    reaction-only)를 재사용하고,
  - 5개(verified_event_identity·production_gold_available·news_corroboration_present·public_safety_review·
    moderation_policy_ready·reply_policy_ready)를 **새로** 결속한다.

절대 불변(§13): hotness alone cannot publish · community buzz cannot publish · official record alone cannot publish ·
LLM headline cannot publish · public_readiness 는 evidence/gold/merge gate 를 모두 요구 · 모든 요구 충족이어도
`runtime_enabled=False`(public post runtime 은 후속 ADR 의 별도 auth/safety gate 후에만) · public_post_body_generated=
False · comment_reply_generation=False · 이 모듈은 게시하지 않는다(계약 검증만·`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.hot_intelligence_post_contract import (
    evaluate_hot_post_readiness,
    is_valid_anchor_role,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "hot_post_gate_alignment"

# §13 11개 게이트 요구(순서 고정·public_readiness = 전부 충족).
HOT_POST_GATE_REQUIREMENTS: tuple[str, ...] = (
    "verified_event_identity",
    "production_gold_available",
    "merge_gate_passed",
    "official_evidence_present",
    "news_corroboration_present",
    "source_role_guard_passed",
    "uncertainty_summary_present",
    "community_layer_reaction_to_only",
    "public_safety_review",
    "moderation_policy_ready",
    "reply_policy_ready",
)

# hot_post_gate_status 어휘.
GATE_REQUIREMENTS_UNMET = "blocked_requirements_unmet"
GATE_REQUIREMENTS_MET_RUNTIME_DISABLED = "requirements_met_runtime_disabled"

# evaluate_hot_post_readiness 의 anchor/role 위반(source_role_guard 실패 신호).
_ANCHOR_VIOLATIONS = frozenset({
    "community_reaction_used_as_anchor", "market_signal_used_as_anchor",
    "search_url_candidate_is_not_truth",
})


def _evaluate_requirements(draft: dict, readiness: dict) -> dict[str, bool]:
    """draft + 기존 readiness → 11개 요구 boolean(5개 readiness 재사용·5개 신규 결속)."""
    violations = set(readiness.get("violations") or [])
    anchor_role = str(draft.get("anchor_role") or "")
    source_role_guard_passed = (
        is_valid_anchor_role(anchor_role)
        and not any(v.startswith("non_anchor_role_used_as_anchor") for v in violations)
        and violations.isdisjoint(_ANCHOR_VIOLATIONS))
    return {
        # ── 신규 결속(5) ──
        "verified_event_identity": draft.get("verified_event_identity") is True,
        "production_gold_available": int(draft.get("production_gold_count") or 0) > 0,
        "news_corroboration_present": bool(draft.get("news_corroboration")),
        "public_safety_review": draft.get("public_safety_review") is True,
        "moderation_policy_ready": draft.get("moderation_policy_ready") is True,
        "reply_policy_ready": draft.get("reply_policy_ready") is True,
        # ── 기존 readiness 재사용(5) ──
        "merge_gate_passed": "no_public_post_before_merge_gate" not in violations,
        "official_evidence_present": "no_official_evidence_no_authoritative_claim" not in violations,
        "source_role_guard_passed": source_role_guard_passed,
        "uncertainty_summary_present": "uncertainty_must_be_visible" not in violations,
        "community_layer_reaction_to_only": "community_reaction_used_as_anchor" not in violations,
    }


def build_hot_post_gate_alignment(draft: Optional[dict] = None) -> dict:
    """Hot Post draft → 11개 게이트 결속 결과(public_readiness·missing_requirements·runtime No-Go).

    draft 미제공/빈 dict → 모든 요구 미충족(현 evidence/gold/merge 부재 현실). 모든 요구 충족이어도 runtime_enabled=False
    (public post runtime 은 후속 ADR 별도 gate). hotness/community buzz/official 단독/LLM headline 어느 것도 게시 불가."""
    draft = dict(draft or {})
    readiness = evaluate_hot_post_readiness(draft)
    reqs = _evaluate_requirements(draft, readiness)

    missing = [name for name in HOT_POST_GATE_REQUIREMENTS if not reqs[name]]
    public_readiness = len(missing) == 0
    status = GATE_REQUIREMENTS_MET_RUNTIME_DISABLED if public_readiness else GATE_REQUIREMENTS_UNMET

    out = {
        "operation_name": OPERATION_NAME,
        "hot_post_gate_status": status,
        # public_readiness = 11개 요구 전부 충족(현재 False). runtime 은 별개 latch(아래 항상 False).
        "public_readiness": public_readiness,
        "requirements": list(HOT_POST_GATE_REQUIREMENTS),
        "requirement_count": len(HOT_POST_GATE_REQUIREMENTS),
        "requirements_met": {k: reqs[k] for k in HOT_POST_GATE_REQUIREMENTS},
        "missing_requirements": missing,
        "missing_requirement_count": len(missing),
        # ── runtime No-Go(항상·요구 충족과 무관) ──
        "runtime_enabled": False,
        "public_post_body_generated": False,
        "comment_reply_generation": False,
        "publishable": False,                      # public_readiness ∧ runtime — 항상 False(runtime off).
        # ── §13 게시 불가 규칙(정직·constant) ──
        "hotness_alone_publishable": False,
        "community_buzz_publishable": False,
        "official_record_alone_publishable": False,
        "llm_headline_publishable": False,
        # ── No-Go 경계 ──
        "merge_allowed": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="hot_post_gate_alignment_output")
    return out


def sanitized_hot_post_gate_alignment(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status/readiness/missing count 만)."""
    return {
        "hot_post_gate_status": out["hot_post_gate_status"],
        "hot_post_public_readiness": out["public_readiness"],
        "missing_requirement_count": out["missing_requirement_count"],
        "runtime_enabled": out["runtime_enabled"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#91 Hot Post gate alignment (public_readiness 를 R1 gold·R2 MERGE_GATE·evidence·source-role·"
                     "community 경계에 결속; runtime 0·public post 0·comment reply 0·hotness/community/official 단독 게시 0)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(빈 draft → 전 요구 미충족).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_hot_post_gate_alignment()
    if ns.json:
        print(json.dumps(sanitized_hot_post_gate_alignment(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['hot_post_gate_status']} "
          f"public_readiness={out['public_readiness']}")
    print(f"- requirements ({out['requirement_count']}): met "
          f"{out['requirement_count'] - out['missing_requirement_count']}/{out['requirement_count']}")
    print(f"- missing_requirements: {out['missing_requirements']}")
    print(f"- runtime: enabled={out['runtime_enabled']} public_post_body={out['public_post_body_generated']} "
          f"comment_reply={out['comment_reply_generation']} publishable={out['publishable']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
