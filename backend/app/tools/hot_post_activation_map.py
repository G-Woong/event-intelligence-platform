"""ADR#93 §13 — Hot Post 공개 runtime 활성화 맵(R1→R2 후 공개가 열리는 단계 순서를 계약으로 고정·runtime 0).

이 모듈은 "R1(gold) 다음 R2(merge) 가 끝난 뒤, Hot Post 공개 runtime 이 *어떤 순서의 게이트* 로 열리는가"를
계약으로만 기술한다(runtime 은 이번 턴에도 DISABLED). 단계는 9개다:
  preview 차단 → R1 gold → R2 merge → public readiness → preview 허용 → publish candidate → operator 승인 →
  community reaction → comment reply gate.

**community_posting_roadmap_contract 와의 차이(명시·DISTINCT)**: community_posting_roadmap_contract 는 제품
*LIFECYCLE*(evidence→label→post→reaction→reply)를 8단계로 고정한다. 이 모듈은 그 lifecycle 이 아니라 **공개 runtime
ACTIVATION GATE SEQUENCE** — 어떤 게이트가 충족돼야 내부 preview→공개 게시→댓글 응답이 *열리는지* 의 게이트 순서 —
를 고정한다. 두 모듈은 목적이 다르며, 이 모듈은 게이트 요구를 **재선언하지 않고** 기존 상수/빌더를 COMPOSE 한다.

COMPOSE(재구현·재선언 0):
  - public-readiness 단계는 `HOT_POST_GATE_REQUIREMENTS`(R1 production_gold_available + R2 merge_gate_passed 포함
    11-tuple)와 `build_hot_post_gate_alignment()` 의 public_readiness/missing_requirements 를 참조(11 게이트 재나열 0).
  - stage_0(preview 차단)은 `build_hot_post_preview_guard()`(preview_publishable False·public 항상 차단)로 증명.
  - comment-reply 단계는 `build_community_interaction_future_gate()['all_requirements_met']` 를 precondition 으로 참조.
  - community-reaction-attach 단계의 anchor 금지는 `is_valid_anchor_role`(official/news only)로 결속.

절대 불변(§13): runtime 0 · public post body 0 · comment reply 0 · community anchor 0 · hotness 단독 게시 0 ·
publish 는 R1 AND R2 필요 · operator 승인 필요 · merge 0 · public IU 0 · same_event 단정 0 · LLM 0 ·
이 모듈은 게시·응답하지 않는다(계약 정의만·`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.community_interaction_future_gate import (
    COMMUNITY_GATE_REQUIREMENTS,
    build_community_interaction_future_gate,
)
from backend.app.tools.hot_intelligence_post_contract import is_valid_anchor_role
from backend.app.tools.hot_post_gate_alignment import (
    HOT_POST_GATE_REQUIREMENTS,
    build_hot_post_gate_alignment,
)
from backend.app.tools.hot_post_preview_guard import build_hot_post_preview_guard
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "hot_post_activation_map"
CONTRACT_VERSION = "hot_post_activation_map_v1"

HPA_DEFINED_RUNTIME_DISABLED = "hot_post_activation_map_defined_runtime_disabled"

# 9단계 공개 runtime 활성화 게이트 순서(stage_0..stage_8). 각 단계는 7필드(entry/allowed/forbidden/required_evidence/
# runtime_status/next_gate). 모든 단계 runtime_status 는 "runtime_disabled" 를 포함한다(전 단계 No-Go·이번 턴 게시 0).
_STAGES: tuple[dict, ...] = (
    {
        "stage": "stage_0_internal_preview_blocked",
        "entry_conditions": ["default state before R1 gold and R2 MERGE_GATE",
                             "build_hot_post_preview_guard: preview_publishable False, hot_post_preview_public_blocked True"],
        "allowed_actions": ["internal evidence collection + overlap diagnostics (reviewer-routing only)"],
        "forbidden_actions": ["internal preview render", "public post body generation", "publish", "comment reply"],
        "required_evidence": ["none yet — preview is blocked before structural readiness"],
        "runtime_status": "runtime_disabled_preview_blocked",
        "next_gate": "stage_1_r1_gold_available",
    },
    {
        "stage": "stage_1_r1_gold_available",
        "entry_conditions": ["R1 production_gold_available (reviewer gold floor: live >=200 / KO >=50)"],
        "allowed_actions": ["record R1 production_gold_available = True (gate evaluation only)"],
        "forbidden_actions": ["public post body before R1 production_gold_available AND R2 merge_gate_passed",
                             "publish", "merge"],
        "required_evidence": ["production gold provenance (reviewer-labeled; model/self/LLM labels are not gold)"],
        "runtime_status": "runtime_disabled",
        "next_gate": "stage_2_r2_merge_gate_passed",
    },
    {
        "stage": "stage_2_r2_merge_gate_passed",
        "entry_conditions": ["R2 merge_gate_passed (MERGE_GATE precision >=0.98 / FPR <=0.01 / hard-neg FP=0)"],
        "allowed_actions": ["record R2 merge_gate_passed = True (gate evaluation only)"],
        "forbidden_actions": ["public post body before R1 production_gold_available AND R2 merge_gate_passed",
                             "auto-merge", "publish"],
        "required_evidence": ["MERGE_GATE adversarial review record"],
        "runtime_status": "runtime_disabled",
        "next_gate": "stage_3_hot_post_public_readiness_check",
    },
    {
        "stage": "stage_3_hot_post_public_readiness_check",
        "entry_conditions": ["build_hot_post_gate_alignment public_readiness True — all HOT_POST_GATE_REQUIREMENTS "
                             "satisfied (missing_requirements empty)"],
        "allowed_actions": ["evaluate Hot Post public readiness (gate only)"],
        "forbidden_actions": ["publish on hotness alone", "publish on community buzz alone",
                             "publish on official record alone", "publish before an explicit runtime ADR"],
        "required_evidence": ["all HOT_POST_GATE_REQUIREMENTS met (incl. R1 production_gold_available + "
                             "R2 merge_gate_passed)"],
        "runtime_status": "runtime_disabled_gate_only",
        "next_gate": "stage_4_internal_preview_allowed",
    },
    {
        "stage": "stage_4_internal_preview_allowed",
        "entry_conditions": ["public_readiness True",
                             "structural preview checks pass (official evidence anchor + uncertainty + "
                             "community reaction-only + source role)"],
        "allowed_actions": ["render internal-only preview for reviewer/operator"],
        "forbidden_actions": ["public publish from the internal preview", "treat the internal preview as a public post"],
        "required_evidence": ["internal-only preview; public surface stays blocked (hot_post_preview_public_blocked True)"],
        "runtime_status": "runtime_disabled_internal_preview_only",
        "next_gate": "stage_5_public_publish_candidate",
    },
    {
        "stage": "stage_5_public_publish_candidate",
        "entry_conditions": ["internal preview allowed",
                             "R1 production_gold_available AND R2 merge_gate_passed both True"],
        "allowed_actions": ["assemble a public publish candidate (contract only — body not emitted)"],
        "forbidden_actions": ["public post body before R1 production_gold_available AND R2 merge_gate_passed",
                             "auto-publish without operator approval", "LLM headline"],
        "required_evidence": ["R1 gold + R2 MERGE_GATE + Hot Post public_readiness all present"],
        "runtime_status": "runtime_disabled",
        "next_gate": "stage_6_public_publish_requires_operator_approval",
    },
    {
        "stage": "stage_6_public_publish_requires_operator_approval",
        "entry_conditions": ["a public publish candidate exists",
                             "R1 production_gold_available AND R2 merge_gate_passed both True"],
        "allowed_actions": ["request explicit operator approval for the publish candidate (manual, audited)"],
        "forbidden_actions": ["public post body before R1 production_gold_available AND R2 merge_gate_passed",
                             "publish without explicit operator approval", "auto-publish"],
        "required_evidence": ["explicit operator approval record (manual; not automated)"],
        "runtime_status": "runtime_disabled_requires_operator_approval",
        "next_gate": "stage_7_community_reaction_attachment",
    },
    {
        "stage": "stage_7_community_reaction_attachment",
        "entry_conditions": ["a verified, operator-approved public post exists (future)"],
        "allowed_actions": ["attach community reaction as a reaction_to layer only"],
        "forbidden_actions": ["use community reaction as an evidence anchor (is_valid_anchor_role: official/news only)",
                             "promote community to an anchor role"],
        "required_evidence": ["community reaction is reaction_to, never an anchor "
                             "(is_valid_anchor_role('community') is False)"],
        "runtime_status": "runtime_disabled_reaction_to_only",
        "next_gate": "stage_8_comment_reply_gate",
    },
    {
        "stage": "stage_8_comment_reply_gate",
        # terminal: community_interaction_future_gate.all_requirements_met 를 precondition 으로 참조(11요구 재나열 0).
        "entry_conditions": ["community_interaction_future_gate.all_requirements_met (the 11-requirement gate)"],
        "allowed_actions": ["(future) comment reply with provenance + citation + uncertainty"],
        "forbidden_actions": ["comment reply before the community_interaction_future_gate passes",
                             "LLM reply now", "reply without provenance"],
        "required_evidence": ["reply provenance + source citation + uncertainty policy + moderation + audit log"],
        "runtime_status": "runtime_disabled_comment_reply_blocked",
        "next_gate": "",
    },
)

STAGE_ORDER: tuple[str, ...] = tuple(s["stage"] for s in _STAGES)


def build_hot_post_activation_map() -> dict:
    """Hot Post 공개 runtime 활성화 게이트 순서 계약(9단계·runtime 0·게시 0). 게시·응답하지 않는다.

    public-readiness 단계는 HOT_POST_GATE_REQUIREMENTS / build_hot_post_gate_alignment 을, stage_0 은
    build_hot_post_preview_guard 를, comment-reply 단계는 build_community_interaction_future_gate 의
    all_requirements_met 를, community-reaction 단계는 is_valid_anchor_role 를 COMPOSE 한다(게이트 요구 재선언 0).
    모든 단계 runtime disabled — public post / comment reply 는 후속 ADR 의 별도 auth/safety gate 후에만 열린다."""
    gate = build_hot_post_gate_alignment()
    preview = build_hot_post_preview_guard()
    community = build_community_interaction_future_gate()

    # public_readiness 는 R1(gold) AND R2(merge) 를 요구한다 — 그 두 요구가 HOT_POST_GATE_REQUIREMENTS 의 멤버임으로 결속.
    public_readiness_requires_r1 = "production_gold_available" in HOT_POST_GATE_REQUIREMENTS
    public_readiness_requires_r2 = "merge_gate_passed" in HOT_POST_GATE_REQUIREMENTS
    # community 는 evidence anchor 가 될 수 없음(official/news only) — 상수 재선언이 아니라 is_valid_anchor_role 로 파생.
    community_reaction_anchor = is_valid_anchor_role("community")

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "hot_post_activation_map_status": HPA_DEFINED_RUNTIME_DISABLED,
        "activation_stages": [dict(s) for s in _STAGES],
        "stage_order": list(STAGE_ORDER),
        "stage_count": len(_STAGES),
        # ── hot_post_gate_alignment 참조(11요구는 그 모듈 단일 출처·재나열 0) ──
        "references_hot_post_gate_requirements": True,
        "hot_post_gate_requirements_count": len(HOT_POST_GATE_REQUIREMENTS),
        "public_readiness_requires_r1": public_readiness_requires_r1,
        "public_readiness_requires_r2": public_readiness_requires_r2,
        "hot_post_public_readiness": bool(gate["public_readiness"]),
        "hot_post_missing_requirement_count": gate["missing_requirement_count"],
        # ── preview guard 참조(stage_0 증명: 빈 draft → preview 차단·public 항상 차단) ──
        "preview_blocked_status": preview["hot_post_preview_status"],
        # ── community interaction gate 참조(comment reply 전제·11요구 재나열 0) ──
        "references_community_interaction_gate": True,
        "comment_gate_requirements_count": len(COMMUNITY_GATE_REQUIREMENTS),
        "comment_gate_all_requirements_met": bool(community["all_requirements_met"]),
        # ── runtime No-Go(전 단계·항상) ──
        "runtime_enabled": False,
        "public_post_runtime_enabled": False,
        "public_post_body_generated": False,
        "comment_reply_generated": False,
        "comment_reply_runtime_open": False,
        # ── §13 정직 불변(constant) ──
        "community_reaction_anchor": community_reaction_anchor,   # is_valid_anchor_role('community') → False.
        "hotness_alone_publishable": False,
        "publish_requires_r1_r2": True,
        "merge_allowed": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
        "llm_invoked": False,
        "r2_r7_no_go": True,
        "next_action": ("the Hot Post public runtime stays disabled — the activation map opens internal preview, "
                        "public publish, and comment reply only after R1 production gold, R2 MERGE_GATE, Hot Post "
                        "public_readiness, an internal-only preview, a publish candidate, explicit operator approval, "
                        "and the community interaction gate; this map is contract-only and does not publish or reply"),
    }
    _assert_pii_safe(out, _path="hot_post_activation_map_output")
    return out


def sanitized_hot_post_activation_map(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(stage 본문 제외·status/count/flag 만)."""
    return {
        "hot_post_activation_map_status": out["hot_post_activation_map_status"],
        "stage_count": out["stage_count"],
        "runtime_enabled": out["runtime_enabled"],
        "comment_reply_generated": out["comment_reply_generated"],
        "publish_requires_r1_r2": out["publish_requires_r1_r2"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 Hot Post activation map (공개 runtime 활성화 게이트 9단계 순서·runtime 0·public post 0·"
                     "comment reply 0·community anchor 0·publish 는 R1 AND R2 + operator 승인 필요)."))
    parser.add_argument("--json", action="store_true", help="activation map JSON 출력(stage 본문 포함).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_hot_post_activation_map()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['hot_post_activation_map_status']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- stages ({out['stage_count']}):")
    for s in out["activation_stages"]:
        print(f"    - {s['stage']} [runtime={s['runtime_status']}] -> {s['next_gate'] or '(terminal)'}")
    print(f"- public_readiness_requires_r1={out['public_readiness_requires_r1']} "
          f"public_readiness_requires_r2={out['public_readiness_requires_r2']} "
          f"publish_requires_r1_r2={out['publish_requires_r1_r2']}")
    print(f"- references hot_post_gate_requirements={out['references_hot_post_gate_requirements']} "
          f"(count={out['hot_post_gate_requirements_count']}) preview_blocked_status={out['preview_blocked_status']} "
          f"comment_gate_requirements_count={out['comment_gate_requirements_count']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
