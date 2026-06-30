"""ADR#93 §14 — community feedback loop contract (유저 댓글 ↔ 에이전트 후속 갱신 LOOP 순서 계약·runtime 0).

미래 제품의 핵심 루프: 유저가 intelligence post 에 댓글을 남기면 → 분류 → moderation → 질문/반응 판별 →
(질문이면) 에이전트가 출처 있는 후속 증거를 수집 → post 갱신/응답 후보 조립 → 사람/정책 리뷰 → (미래)
응답 게시 → 전 과정을 audit log 에 남긴다. 이 모듈은 그 **LOOP SEQUENCE 계약**(11단계 순서·runtime 0·
docs/contract only)이다 — 어떤 댓글도 생성·발송하지 않는다.

**COMPOSE, not re-declare**: 이 루프의 *선행 조건*(moderation/privacy/audit/source-citation/reply-provenance/
uncertainty/rate-limit/human-override/verified-event/public-IU 등 11개 요구)은 전부 `community_interaction_
future_gate` 가 단일 출처다. 이 모듈은 그 요구를 **재선언하지 않고** `COMMUNITY_GATE_REQUIREMENTS` 를 참조하며,
"응답 생성 0 / runtime disabled" 증거도 gate 의 `comment_reply_generation`·`runtime_enabled`(둘 다 항상 False)를
**passthrough** 한다. gate 는 *무엇이 충족돼야 하나*(flat checklist)를, 이 모듈은 *어떤 순서로 흐르나*(loop
sequence)를 정의한다(DISTINCT). 각 단계의 선행 조건은 community_interaction_future_gate 에 산다.

절대 불변(§14·§20): 댓글 auto-reply 0 · 응답 생성 0 · privacy gate 없이 user-data 저장 0 · moderation 필수 ·
privacy 필수 · audit log 필수 · source citation 필수 · uncertainty 필수 · 에이전트 후속은 사실 날조 0 ·
community 는 reaction_to only(anchor 0) · merge 0 · public IU 0 · LLM 0 · same_event 확정 0 ·
**이 모듈은 어떤 댓글도 생성·발송하지 않는다**(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.community_interaction_future_gate import (
    COMMUNITY_GATE_REQUIREMENTS,
    GATE_RUNTIME_DISABLED,
    build_community_interaction_future_gate,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "community_feedback_loop_contract"
CONTRACT_VERSION = "community_feedback_loop_v1"

CFL_DEFINED_RUNTIME_DISABLED = "community_feedback_loop_defined_runtime_disabled"

# 11단계 LOOP 순서(user_comment_received..audit_log). 각 단계 5필드(step/description/requires/forbidden_now/
# runtime_status). requires 는 COMMUNITY_GATE_REQUIREMENTS 의 이름만 참조(재선언 0). 응답 단계(reply_candidate·
# reply_publish_gate)의 runtime_status 는 community_interaction_future_gate 의 runtime-disabled 상태를 그대로 단다.
_LOOP_STEPS: tuple[dict, ...] = (
    {
        "step": "user_comment_received",
        "description": "유저가 (미래) intelligence post 에 댓글/반응을 남긴다(수신만 — 저장은 privacy gate 뒤에만).",
        "requires": ["privacy_user_data_policy", "rate_limit"],
        "forbidden_now": ["privacy gate 없이 user-data 저장", "raw user PII 저장", "comment auto-reply"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "comment_classification",
        "description": "댓글을 질문/반응/스팸/abuse 로 분류(구조적 — LLM 실호출 0).",
        "requires": ["abuse_spam_guard", "privacy_user_data_policy"],
        "forbidden_now": ["LLM 분류 runtime", "raw user PII 저장"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "safety_moderation",
        "description": "moderation + abuse/spam 게이트 — 통과 전 어떤 후속/응답도 진행 0.",
        "requires": ["moderation_policy", "abuse_spam_guard", "human_override"],
        "forbidden_now": ["moderation 우회", "moderation 전 auto-reply"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "question_or_reaction_detection",
        "description": "질문(출처 후속 필요) vs 단순 반응 구분 — community 반응은 reaction_to only(anchor 0).",
        "requires": ["uncertainty_policy"],
        "forbidden_now": ["community 반응을 evidence anchor 로 사용", "LLM runtime"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "source_followup_needed",
        "description": "답변에 새 출처 증거가 필요한지 판정(verified event 위에서만 · 출처 필수).",
        "requires": ["verified_event", "source_citation_policy"],
        "forbidden_now": ["사실 날조", "출처 없이 답변"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "agent_followup_collection",
        "description": "(미래) 에이전트가 새 출처·검증 증거를 수집 — 사실 날조 0 · rate limit/robots 준수.",
        "requires": ["source_citation_policy", "rate_limit", "reply_provenance"],
        "forbidden_now": ["사실 날조", "source policy/rate limit 없이 수집", "robots.txt/ToS 우회"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "post_update_candidate",
        "description": "수집 증거로 post 갱신 후보를 조립(contract only — merge/public IU 0).",
        "requires": ["verified_event", "source_citation_policy", "uncertainty_policy"],
        "forbidden_now": ["merge", "public IU 생성", "same_event 확정", "LLM headline"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "human_or_policy_review",
        "description": "응답/갱신 게시 전 사람 override 또는 정책 리뷰(자동 게시 0).",
        "requires": ["human_override", "moderation_policy"],
        "forbidden_now": ["사람/정책 리뷰 없이 auto-publish"],
        "runtime_status": "runtime_disabled",
    },
    {
        "step": "reply_candidate",
        "description": "provenance + citation + uncertainty 를 갖춘 응답 후보 조립(contract only — 응답 생성 0).",
        "requires": ["reply_provenance", "source_citation_policy", "uncertainty_policy"],
        "forbidden_now": ["응답 생성", "LLM reply", "provenance/citation/uncertainty 없는 응답", "사실 날조"],
        "runtime_status": GATE_RUNTIME_DISABLED,   # 응답 단계 runtime = community_interaction_future_gate 의 disabled 상태.
    },
    {
        "step": "reply_publish_gate",
        "description": "응답 게시는 community_interaction_future_gate 통과 후에만 — 그래도 현 단계 runtime 0.",
        "requires": ["public_iu_gate_passed", "moderation_policy", "human_override", "audit_log"],
        "forbidden_now": ["comment auto-reply runtime now", "지금 응답 게시"],
        "runtime_status": GATE_RUNTIME_DISABLED,   # 게시 게이트 runtime = community_interaction_future_gate 의 disabled 상태.
    },
    {
        "step": "audit_log",
        "description": "모든 단계와 (미래) 응답/갱신을 audit log 에 기록.",
        "requires": ["audit_log"],
        "forbidden_now": ["audit trail 누락"],
        "runtime_status": "runtime_disabled",
    },
)

LOOP_STEP_ORDER: tuple[str, ...] = tuple(s["step"] for s in _LOOP_STEPS)


def _validate_requires_reference_gate() -> None:
    """각 loop step.requires 가 COMMUNITY_GATE_REQUIREMENTS 안의 이름만 참조함을 보장(재선언 0·드리프트 fail-loud).

    선행 요구의 단일 출처는 community_interaction_future_gate 이므로, 여기서 새 requirement 이름을 발명하면(typo·
    드리프트) 즉시 ValueError 로 실패해 계약이 gate 와 어긋나는 것을 막는다."""
    req_set = frozenset(COMMUNITY_GATE_REQUIREMENTS)
    for s in _LOOP_STEPS:
        unknown = [r for r in s["requires"] if r not in req_set]
        if unknown:
            raise ValueError(
                f"loop step {s['step']!r} requires unknown requirement(s) {unknown} "
                f"— must reference COMMUNITY_GATE_REQUIREMENTS (single source of truth)")


def build_community_feedback_loop_contract() -> dict:
    """유저 댓글 ↔ 에이전트 후속 갱신 LOOP 11단계 순서 계약(runtime 0·docs/contract only). 어떤 댓글도 생성·발송하지 않는다.

    선행 요구(moderation/privacy/audit/citation/provenance/uncertainty/rate/human/verified/public-IU 등 11개)는
    community_interaction_future_gate 가 단일 출처 — 이 모듈은 그것을 재선언하지 않고 COMMUNITY_GATE_REQUIREMENTS 를
    참조하며, "응답 생성 0 / runtime disabled" 증거는 gate 의 comment_reply_generation·runtime_enabled(둘 다 항상 False)를
    passthrough 한다(단일 출처)."""
    _validate_requires_reference_gate()
    gate = build_community_interaction_future_gate()
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "community_feedback_loop_status": CFL_DEFINED_RUNTIME_DISABLED,
        "loop_steps": [dict(s) for s in _LOOP_STEPS],
        "loop_step_order": list(LOOP_STEP_ORDER),
        "loop_step_count": len(_LOOP_STEPS),
        # ── community_interaction_future_gate 를 COMPOSE(11요구는 그 gate 단일 출처·재선언 0) ──
        "references_community_interaction_gate": True,
        "community_interaction_gate_status": gate["community_interaction_gate_status"],
        "community_gate_requirements_count": len(COMMUNITY_GATE_REQUIREMENTS),
        # ── 선행 요구의 LOOP 필수 표면(정책 자체는 gate 가 강제·정직 상수) ──
        "moderation_required": True,
        "privacy_gate_required": True,
        "audit_log_required": True,
        "source_citation_required": True,
        "uncertainty_required": True,
        # ── runtime/응답 생성 No-Go: gate passthrough(단일 출처·둘 다 항상 False) ──
        "runtime_enabled": gate["runtime_enabled"],            # 항상 False(gate 단일 출처).
        "reply_generated": gate["comment_reply_generation"],   # 항상 False(gate 단일 출처) — 응답 생성 0.
        # ── §14 불변 경계(정직·constant) ──
        "comment_auto_reply_enabled": False,
        "user_comment_runtime_open": False,
        "community_is_evidence_anchor": False,        # community 는 reaction_to only.
        "agent_followup_can_fabricate_facts": False,  # 후속 수집은 사실 날조 0.
        "merge_allowed": False,
        "public_iu_allowed": False,
        "llm_invoked": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
        "next_action": (
            "the community feedback loop is sequence-contract-only — user-comment ↔ agent-followup runtime opens "
            "only after the community_interaction_future_gate (moderation/privacy/abuse/audit/citation/provenance/"
            "uncertainty/rate-limit/human-override/verified-event/public-IU) passes"),
    }
    _assert_pii_safe(out, _path="community_feedback_loop_contract_output")
    return out


def sanitized_community_feedback_loop_contract(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(loop step 본문 제외 — status/count/flag 만)."""
    return {
        "community_feedback_loop_status": out["community_feedback_loop_status"],
        "loop_step_count": out["loop_step_count"],
        "runtime_enabled": out["runtime_enabled"],
        "reply_generated": out["reply_generated"],
        "moderation_required": out["moderation_required"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#93 community feedback loop contract (유저 댓글 ↔ 에이전트 후속 갱신 11단계 LOOP 순서·"
                     "runtime 0·응답 생성 0·moderation/privacy/audit/citation/uncertainty 필수·사실 날조 0)."))
    parser.add_argument("--json", action="store_true", help="contract JSON 출력(loop step 본문 포함).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_community_feedback_loop_contract()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['community_feedback_loop_status']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- loop steps ({out['loop_step_count']}):")
    for s in out["loop_steps"]:
        print(f"    - {s['step']} [runtime={s['runtime_status']}] requires={s['requires']}")
    print(f"- references community_interaction_future_gate: {out['references_community_interaction_gate']} "
          f"(status={out['community_interaction_gate_status']} reqs={out['community_gate_requirements_count']})")
    print(f"- gates: reply_generated={out['reply_generated']} comment_auto_reply_enabled={out['comment_auto_reply_enabled']} "
          f"moderation_required={out['moderation_required']} privacy_gate_required={out['privacy_gate_required']} "
          f"audit_log_required={out['audit_log_required']} fabricate_facts={out['agent_followup_can_fabricate_facts']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
