"""ADR#92 §13 — Hot Post preview guard (내부 preview 가 public post 와 혼동되지 않게 보호·body 생성 0·게시 0).

문제(제품 방향): 최종 목표는 커뮤니티형 Hot Intelligence Post 지만, R1/R2 전에는 public 게시가 없다. 운영 중 내부
preview(reviewer/operator 가 보는 draft)가 생기더라도 그것이 public post 와 혼동되거나 실수로 게시되면 안 된다.

이 모듈은 그 경계를 지키는 **preview guard** 다(hot_post_gate_alignment + community_interaction_future_gate +
is_valid_anchor_role 합성·재구현 0):
  - public_post_body_generated=False · comment_reply_generated=False (지금은 body 생성 0·placeholder only).
  - preview 는 게시 불가(preview_publishable=False·public 항상 차단) — R1 gold·MERGE_GATE·public_readiness 필요.
  - preview 는 same_event 단정 불가 · community 를 anchor 로 사용 불가 · uncertainty 필수.
  - structural 검사(official evidence anchor·uncertainty·community reaction-only·source role)를 통과해야 internal-only
    preview 가 허용되며, 통과해도 public 은 막힌다. hotness/community 단독으로는 preview 도 불가.
  불변: runtime 0 · public post 0 · comment reply 0 · merge 0 · same_event 단정 0 · secret/PII 0(`_assert_pii_safe`).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.community_interaction_future_gate import (
    build_community_interaction_future_gate,
)
from backend.app.tools.hot_intelligence_post_contract import is_valid_anchor_role
from backend.app.tools.hot_post_gate_alignment import build_hot_post_gate_alignment
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "hot_post_preview_guard"

# hot_post_preview_status.
HPV_BLOCKED = "preview_blocked_fix_draft"                  # structural 미충족 → preview 불가.
HPV_INTERNAL_ONLY = "preview_internal_only_public_blocked"  # structural 충족 → internal-only(public 차단).


def build_hot_post_preview_guard(draft: Optional[dict] = None) -> dict:
    """Hot Post draft → preview guard(internal-only 허용 여부 + public 항상 차단·body 생성 0·게시 0).

    gate alignment(11요구) + community gate(comment reply 0) + anchor role 검사를 합성한다. structural 검사
    (official evidence·uncertainty·community reaction-only·source role)를 통과하면 internal-only preview 허용,
    통과해도 public 게시는 R1 gold·MERGE_GATE·public_readiness 전까지 차단. hotness/community 단독은 preview 불가."""
    gate = build_hot_post_gate_alignment(draft)
    community = build_community_interaction_future_gate()
    reqs = gate["requirements_met"]

    source_role_guard_passed = bool(reqs["source_role_guard_passed"])
    community_layer_reaction_to_only = bool(reqs["community_layer_reaction_to_only"])
    uncertainty_summary_present = bool(reqs["uncertainty_summary_present"])
    official_evidence_present = bool(reqs["official_evidence_present"])

    structural_ok = (
        source_role_guard_passed and community_layer_reaction_to_only
        and uncertainty_summary_present and official_evidence_present)
    preview_allowed_internal_only = structural_ok

    requires_r1_gold = not bool(reqs["production_gold_available"])
    requires_merge_gate = not bool(reqs["merge_gate_passed"])
    requires_public_readiness = not bool(gate["public_readiness"])

    anchor_role = str((draft or {}).get("anchor_role") or "")
    community_used_as_anchor = bool(anchor_role) and not is_valid_anchor_role(anchor_role)

    structural_reasons: list[str] = []
    if not official_evidence_present:
        structural_reasons.append("no official evidence anchor (hotness/community alone cannot preview)")
    if community_used_as_anchor or not community_layer_reaction_to_only:
        structural_reasons.append("community/non-anchor role used as anchor (community is reaction_to only)")
    if not source_role_guard_passed:
        structural_reasons.append("source role guard failed (anchor must be official/news)")
    if not uncertainty_summary_present:
        structural_reasons.append("uncertainty summary required before any preview")

    if structural_ok:
        status = HPV_INTERNAL_ONLY
        public_reasons: list[str] = []
        if requires_r1_gold:
            public_reasons.append("R1 production gold floor")
        if requires_merge_gate:
            public_reasons.append("R2 MERGE_GATE")
        if requires_public_readiness:
            public_reasons.append("Hot Post public_readiness (11 requirements)")
        blocked_reason = (
            "internal-only preview allowed; public publishing blocked — requires " + ", ".join(public_reasons)
            if public_reasons else "internal-only preview allowed; public publishing blocked")
    else:
        status = HPV_BLOCKED
        blocked_reason = structural_reasons[0]

    out = {
        "operation_name": OPERATION_NAME,
        "hot_post_preview_status": status,
        "preview_allowed_internal_only": preview_allowed_internal_only,
        # body/reply 생성 0(gate/community gate passthrough — 항상 False).
        "public_post_body_generated": bool(gate["public_post_body_generated"]),
        "comment_reply_generated": bool(community["comment_reply_generation"]),
        "requires_r1_gold": requires_r1_gold,
        "requires_merge_gate": requires_merge_gate,
        "requires_public_readiness": requires_public_readiness,
        "blocked_reason": blocked_reason,
        "all_blockers": structural_reasons,
        # §14 frontier field — public 은 이 턴 항상 차단.
        "hot_post_preview_public_blocked": True,
        # structural 검사(투명).
        "source_role_guard_passed": source_role_guard_passed,
        "community_layer_reaction_to_only": community_layer_reaction_to_only,
        "uncertainty_summary_present": uncertainty_summary_present,
        "official_evidence_present": official_evidence_present,
        "community_used_as_anchor": community_used_as_anchor,
        # ── 불변 경계(정직·constant) ──
        "preview_publishable": False,
        "preview_asserts_same_event": False,
        "hotness_alone_preview": False,
        "runtime_enabled": False,
        "merge_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="hot_post_preview_guard_output")
    return out


def sanitized_hot_post_preview_guard(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(status + public 차단 + body/reply 생성 0)."""
    return {
        "hot_post_preview_status": out["hot_post_preview_status"],
        "hot_post_preview_public_blocked": out["hot_post_preview_public_blocked"],
        "preview_allowed_internal_only": out["preview_allowed_internal_only"],
        "public_post_body_generated": out["public_post_body_generated"],
        "comment_reply_generated": out["comment_reply_generated"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#92 Hot Post preview guard (internal preview 를 public post 와 분리; body 생성 0·comment reply 0·"
                     "게시 0·same_event 단정 0·community anchor 0·uncertainty 필수·R1/R2 전 public 차단)."))
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(빈 draft → preview blocked).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_hot_post_preview_guard()
    if ns.json:
        print(json.dumps(sanitized_hot_post_preview_guard(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['hot_post_preview_status']} "
          f"internal_only={out['preview_allowed_internal_only']}")
    print(f"- public_post_body_generated={out['public_post_body_generated']} "
          f"comment_reply_generated={out['comment_reply_generated']} "
          f"public_blocked={out['hot_post_preview_public_blocked']}")
    print(f"- requires_r1_gold={out['requires_r1_gold']} requires_merge_gate={out['requires_merge_gate']} "
          f"requires_public_readiness={out['requires_public_readiness']}")
    print(f"- blocked_reason: {out['blocked_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
