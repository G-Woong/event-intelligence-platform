"""ADR#91 §14 — community posting roadmap contract (최종 커뮤니티형 제품 방향을 8단계 순서로 안전하게 고정·runtime 0).

이 프로젝트의 최종 목표는 에이전트가 사람이 흥미로워할 사건을 찾아 공식/뉴스/커뮤니티/시장 증거로 검증해 **커뮤니티형
intelligence post 로 게시하고, 유저 댓글/반응과 상호작용하며 후속 정보를 갱신** 하는 것이다. 그러나 그 길을 한 번에
열면 안 된다 — 증거/gold/merge → 게시 → 커뮤니티 반응 → moderation → 댓글 응답 → 후속 수집의 순서가 있어야 한다.

이 모듈은 그 순서를 **8단계 roadmap 계약** 으로 박는다(runtime 0·docs/contract only). 기존 `community_interaction_
future_gate`(11개 요구 flat checklist)와 **DISTINCT** — 이 모듈은 *순서* 를 정의하고, terminal 단계(comment reply·
agent followup)는 그 gate 의 `all_requirements_met` 를 **precondition 으로 참조** 한다(11개 요구를 재나열하지 않는다).

절대 불변(§14·§19): 단계 순서 고정 · public readiness 전 게시 0 · moderation 전 댓글 응답 0 · community reaction 은
reaction_to only(anchor 0) · agent follow-up 은 사실 날조 0 · privacy/user-data gate 필수 · moderation gate 필수 ·
audit log 필수 · comment reply runtime disabled · 이 모듈은 게시·응답하지 않는다(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.community_interaction_future_gate import (
    build_community_interaction_future_gate,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "community_posting_roadmap_contract"
CONTRACT_VERSION = "community_posting_roadmap_v1"

ROADMAP_DEFINED_RUNTIME_DISABLED = "community_posting_roadmap_defined_runtime_disabled"

# 8단계 순서(stage_0..stage_7). 각 단계는 7필드(entry/allowed/forbidden/evidence/human_label/runtime/next_gate) +
# publish/comment_reply runtime(검증용)을 갖는다. runtime 은 전 단계 disabled(현 단계 No-Go).
_STAGES: tuple[dict, ...] = (
    {
        "stage": "stage_0_internal_evidence_pipeline",
        "entry_conditions": ["operator-confirmed event or autonomous discovery candidate",
                             "source role separation (official/news/community/market/catalog/search)"],
        "allowed_actions": ["collect official/news records in window",
                           "build official×news bridge candidates (reviewer-routing only)",
                           "run overlap diagnostics"],
        "forbidden_actions": ["merge", "publish", "same_event assertion", "LLM/embedding runtime"],
        "evidence_requirements": ["official record + news record in the date window"],
        "human_label_requirements": ["none yet (collection stage)"],
        "runtime_status": "internal_only",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_1_reviewer_gold_and_merge_gate",
    },
    {
        "stage": "stage_1_reviewer_gold_and_merge_gate",
        "entry_conditions": ["bridge candidates frozen as a reviewer worklist"],
        "allowed_actions": ["reviewer labeling", "2-reviewer agreement", "human-only conflict adjudication"],
        "forbidden_actions": ["auto-majority gold", "single-reviewer gold", "merge before MERGE_GATE", "publish"],
        "evidence_requirements": ["≥2 reviewer decisive labels on live_derived pairs"],
        "human_label_requirements": ["R1 production gold floor (live ≥200 / KO ≥50)",
                                    "R2 MERGE_GATE precision ≥0.98 / FPR ≤0.01 / hard-neg FP=0"],
        "runtime_status": "internal_only",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_2_hot_intelligence_post_draft_contract",
    },
    {
        "stage": "stage_2_hot_intelligence_post_draft_contract",
        "entry_conditions": ["R1 gold available AND MERGE_GATE passed"],
        "allowed_actions": ["assemble Hot Intelligence Post draft fields (contract only)"],
        "forbidden_actions": ["public post body generation", "LLM headline", "publish"],
        "evidence_requirements": ["official evidence + news corroboration + uncertainty summary"],
        "human_label_requirements": ["production gold provenance"],
        "runtime_status": "draft_contract_only",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_3_public_readiness_gate",
    },
    {
        "stage": "stage_3_public_readiness_gate",
        "entry_conditions": ["hot_post_gate_alignment public_readiness requirements all met"],
        "allowed_actions": ["evaluate public readiness (gate only)"],
        "forbidden_actions": ["publish before an explicit runtime ADR", "hotness-alone publish",
                             "community-buzz publish", "official-record-alone publish"],
        "evidence_requirements": ["all 11 hot_post_gate requirements"],
        "human_label_requirements": ["production gold available"],
        "runtime_status": "gate_only_runtime_disabled",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_4_community_reaction_attachment",
    },
    {
        "stage": "stage_4_community_reaction_attachment",
        "entry_conditions": ["a publish-eligible post exists (future)"],
        "allowed_actions": ["attach community reaction as a reaction_to layer only"],
        "forbidden_actions": ["use community reaction as an evidence anchor",
                             "promote community to an anchor role"],
        "evidence_requirements": ["community reaction is reaction_to, never an anchor"],
        "human_label_requirements": ["n/a"],
        "runtime_status": "reaction_to_only_runtime_disabled",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_5_moderation_and_safety_gate",
    },
    {
        "stage": "stage_5_moderation_and_safety_gate",
        "entry_conditions": ["moderation + abuse/spam + privacy/user-data policies in place"],
        "allowed_actions": ["moderation review", "safety review"],
        "forbidden_actions": ["comment reply before moderation", "store raw user PII"],
        "evidence_requirements": ["moderation_policy", "abuse_spam_guard", "privacy_user_data_policy"],
        "human_label_requirements": ["human override available"],
        "runtime_status": "moderation_required_runtime_disabled",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_6_comment_reply_gate",
    },
    {
        "stage": "stage_6_comment_reply_gate",
        # terminal-side: community_interaction_future_gate.all_requirements_met 를 precondition 으로 참조(11요구 재나열 0).
        "entry_conditions": ["community_interaction_future_gate.all_requirements_met (the 11-requirement gate)"],
        "allowed_actions": ["(future) comment reply with provenance + citation + uncertainty"],
        "forbidden_actions": ["comment auto-reply runtime now", "LLM reply now", "reply without provenance"],
        "evidence_requirements": ["reply_provenance", "source_citation_policy", "uncertainty_policy"],
        "human_label_requirements": ["human override + audit log"],
        "runtime_status": "comment_reply_runtime_disabled",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "stage_7_agent_followup_collection",
    },
    {
        "stage": "stage_7_agent_followup_collection",
        "entry_conditions": ["comment reply gate passed (future)", "source policy + rate limit in place"],
        "allowed_actions": ["(future) agent follow-up collection of new sourced evidence"],
        "forbidden_actions": ["fabricate facts", "collect without source policy/rate limit",
                             "bypass robots.txt / ToS"],
        "evidence_requirements": ["new evidence must be sourced and verified (no fabrication)"],
        "human_label_requirements": ["audit log of follow-up actions"],
        "runtime_status": "followup_runtime_disabled",
        "publish_runtime": "disabled",
        "comment_reply_runtime": "disabled",
        "next_gate": "",
    },
)

STAGE_ORDER: tuple[str, ...] = tuple(s["stage"] for s in _STAGES)


def build_community_posting_roadmap_contract() -> dict:
    """최종 커뮤니티형 제품의 8단계 게시 roadmap 계약(runtime 0·docs/contract only). 게시·응답하지 않는다.

    terminal 단계(comment reply·agent followup)는 community_interaction_future_gate 를 precondition 으로 참조한다
    (11개 요구는 그 gate 가 단일 출처). 모든 단계 runtime disabled — public post / comment reply 는 후속 ADR 의 gate 후에만."""
    gate = build_community_interaction_future_gate()
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "community_posting_roadmap_status": ROADMAP_DEFINED_RUNTIME_DISABLED,
        "roadmap_stages": [dict(s) for s in _STAGES],
        "stage_order": list(STAGE_ORDER),
        "stage_count": len(_STAGES),
        # community_interaction_future_gate 참조(11요구는 그 gate 단일 출처·재나열 0).
        "references_community_interaction_gate": True,
        "community_interaction_gate_status": gate["community_interaction_gate_status"],
        "community_interaction_all_requirements_met": gate["all_requirements_met"],
        # ── runtime No-Go(전 단계·항상) ──
        "runtime_enabled": False,
        "public_post_runtime_enabled": False,
        "comment_reply_generation": False,
        "comment_reply_runtime_open": False,
        # ── §14 불변 경계(정직·constant) ──
        "community_reaction_anchor": False,           # community 는 reaction_to only.
        "agent_followup_fabricates_facts": False,     # 후속 수집은 사실 날조 0.
        "privacy_user_data_gate_required": True,
        "moderation_gate_required": True,
        "audit_log_required": True,
        "publish_requires_r1_r2": True,
        "merge_allowed": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
        "llm_invoked": False,
        "r2_r7_no_go": True,
        "next_action": ("the community posting roadmap is contract-only — public post and comment reply runtime open "
                        "only after R1 gold, MERGE_GATE, the public-IU gate, and the community interaction gate pass"),
    }
    _assert_pii_safe(out, _path="community_posting_roadmap_contract_output")
    return out


def sanitized_community_posting_roadmap(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(stage 본문 제외·status/count/flag 만)."""
    return {
        "community_posting_roadmap_status": out["community_posting_roadmap_status"],
        "stage_count": out["stage_count"],
        "runtime_enabled": out["runtime_enabled"],
        "comment_reply_generation": out["comment_reply_generation"],
        "publish_requires_r1_r2": out["publish_requires_r1_r2"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#91 community posting roadmap contract (8단계 게시 roadmap·runtime 0·public post 0·comment "
                     "reply 0·community anchor 0·agent followup 사실 날조 0)."))
    parser.add_argument("--json", action="store_true", help="contract JSON 출력(stage 본문 포함).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_community_posting_roadmap_contract()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['community_posting_roadmap_status']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- stages ({out['stage_count']}):")
    for s in out["roadmap_stages"]:
        print(f"    - {s['stage']} [runtime={s['runtime_status']}] -> {s['next_gate'] or '(terminal)'}")
    print(f"- references community_interaction_future_gate: {out['references_community_interaction_gate']} "
          f"(all_met={out['community_interaction_all_requirements_met']})")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
