"""ADR#90 — community interaction future gate (유저 댓글/에이전트 응답 runtime 개방 게이트·runtime 금지).

미래 제품에서는 유저가 intelligence post 에 댓글을 달고, 에이전트가 응답하고, 반응을 보고 후속 수집/글을 갱신한다.
그러나 그 runtime 은 안전·증거·프라이버시 게이트 없이 열면 안 된다(rumor/fact 혼합·환각 응답·PII/abuse 위험).

이 모듈은 그 **개방 게이트 계약** 이다(runtime 0·contract only):
  - 선행 요구: verified event · public-IU gate · moderation · abuse/spam guard · privacy/user-data · reply provenance ·
    source citation · uncertainty policy · human override · rate limit · audit log.
  - 현 상태: **전부 미충족·runtime_enabled=False·comment_reply_generation=False**(이 단계에서 댓글 응답 생성 0).

절대 불변(§14·§19): comment auto-reply 0 · LLM 0 · public post 0 · merge 0 · community 를 evidence anchor 로 0 ·
PII/secret 미노출. **이 모듈은 게이트를 정의할 뿐 — 어떤 댓글도 생성·발송하지 않는다.**
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "community_interaction_future_gate"
CONTRACT_VERSION = "community_interaction_future_gate_v1"

GATE_RUNTIME_DISABLED = "community_interaction_runtime_disabled"
GATE_REQUIREMENTS_UNMET = "community_interaction_requirements_unmet"

# §14 runtime 개방 전 선행 요구(전부 충족 + public-IU/MERGE_GATE 뒤에만 runtime 가능).
COMMUNITY_GATE_REQUIREMENTS: tuple[str, ...] = (
    "verified_event",                  # MERGE_GATE 통과 verified event 위에서만.
    "public_iu_gate_passed",           # RAG_KG_ENTITY_GATE_CONTRACT §5.
    "moderation_policy",
    "abuse_spam_guard",
    "privacy_user_data_policy",
    "reply_provenance",                # 응답 근거 출처 추적.
    "source_citation_policy",
    "uncertainty_policy",              # 불확실성 표기 강제.
    "human_override",
    "rate_limit",
    "audit_log",
)


def build_community_interaction_future_gate(*, passed: Optional[dict] = None) -> dict:
    """community 댓글/응답 runtime 개방 게이트(runtime 0·contract only). 어떤 댓글도 생성하지 않는다.

    passed 는 requirement→충족여부 맵(옵션). 현 단계에서는 어떤 조합이라도 runtime_enabled=False·comment_reply_
    generation=False 고정(public-IU/MERGE_GATE 가 아직 No-Go). all_requirements_met 은 진단 표면일 뿐 runtime 개방 아님."""
    passed = passed or {}
    met = [r for r in COMMUNITY_GATE_REQUIREMENTS if passed.get(r)]
    unmet = [r for r in COMMUNITY_GATE_REQUIREMENTS if not passed.get(r)]
    all_met = len(unmet) == 0
    status = GATE_RUNTIME_DISABLED if all_met else GATE_REQUIREMENTS_UNMET
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "community_interaction_gate_status": status,
        # ── runtime guard(현 단계 No-Go·all_met 이어도 runtime 0) ──
        "runtime_enabled": False,
        "comment_reply_generation": False,
        "comment_auto_reply_enabled": False,
        "user_comment_runtime_open": False,
        # requirements 진단(개방 아님).
        "requirements": list(COMMUNITY_GATE_REQUIREMENTS),
        "requirement_count": len(COMMUNITY_GATE_REQUIREMENTS),
        "requirements_met": met,
        "requirements_unmet": unmet,
        "all_requirements_met": all_met,
        # ── 불변 경계 ──
        "community_is_evidence_anchor": False,
        "llm_invoked": False,
        "merge_allowed": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
        "next_action": (
            "community interaction runtime stays disabled — it opens only after a verified event, the public-IU gate, "
            "moderation/abuse/privacy policies, reply provenance, rate limit, and audit log are all in place"),
    }
    _assert_pii_safe(out, _path="community_interaction_future_gate_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 community interaction future gate (유저 댓글/에이전트 응답 runtime 개방 게이트·runtime 0·"
                     "comment reply 생성 0·community anchor 0·public post 0)."))
    parser.add_argument("--json", action="store_true", help="gate contract JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_community_interaction_future_gate()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['community_interaction_gate_status']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- requirements ({out['requirement_count']}): {', '.join(out['requirements'])}")
    print(f"- all_requirements_met={out['all_requirements_met']} comment_reply_generation={out['comment_reply_generation']} "
          f"user_comment_runtime_open={out['user_comment_runtime_open']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
