"""ADR#95 §15 (option H) — ai-replies comment/reply runtime gate-design contract (FUTURE·runtime 0·LLM 0).

ADR#94(`ai_replies_guard_audit`)는 `POST /api/ai-replies/request` 가 admin-token 없이 마운트된 ungated·mock
엔드포인트라는 **사실을 정적 감사**한다. 그러나 그 감사는 "무엇이 미흡한가"만 말하고, 실제 comment/reply runtime 을
열기 위해 **반드시 통과해야 할 게이트 집합**을 하나의 계약으로 열거하지는 않는다.

이 모듈은 그 결손을 메우는 **미래 gate-design 계약**이다(정적 감사를 한 걸음 넘어선다):
  - 필요한 게이트 10개를 열거하고(must_pass=True), 각 게이트의 충족 여부와 출처(ai_replies_guard_audit /
    community_gate / net_new)를 표면화한다.
  - 4개 **차단 게이트**(public_readiness/moderation/privacy/audit_log) 중 하나라도 미충족이면 BLOCKED 다.
  - 현재 라이브 라우트의 사실(`current_endpoint_status`)을 `ai_replies_guard_audit` 결과에서 그대로 가져온다 —
    ungated 면 "ungated_mock_endpoint".

절대 불변: **runtime_enabled=False·reply_generation_enabled=False** 고정. LLM 0·prompt 0·network 0·public post 0·
production_gold 0. **이 모듈은 게이트를 설계할 뿐 — ai_replies.py 엔드포인트를 import 하지도 수정하지도 않고, 어떤
reply 도 생성하지 않는다.**
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.ai_replies_guard_audit import build_ai_replies_guard_audit
from backend.app.tools.community_interaction_future_gate import COMMUNITY_GATE_REQUIREMENTS
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "ai_replies_gate_design"
CONTRACT_VERSION = "ai_replies_gate_design_v1"

# ai_replies_gate_design_status — 차단 게이트가 모두 충족이면 READY(그래도 runtime_disabled), 하나라도 미충족이면 BLOCKED.
GATE_DESIGN_READY = "gate_design_ready_runtime_disabled"
GATE_DESIGN_BLOCKED = "gate_design_blocked_required_gate_missing"

# 출처별 필요한 게이트 — 출력 순서 = 아래 순서(차단 4개가 선두). ai_replies_guard_audit 의 requires_* 6개에 대응.
_AUDIT_DERIVED_GATES: tuple[str, ...] = (
    "public_readiness_gate",
    "moderation_gate",
    "privacy_gate",
    "audit_log_gate",
    "source_citation_gate",
    "uncertainty_policy_gate",
)
# community_interaction_future_gate 의 requirement 에서 파생(게이트 이름 = "<req>_gate"). 단일 출처가 해당
# requirement 를 더는 제공하지 않으면 import 시 fail-loud(미래 드리프트 차단). 순서 = 요구된 출력 순서.
_COMMUNITY_DERIVED_REQUIREMENTS: tuple[str, ...] = ("rate_limit", "human_override")
for _req in _COMMUNITY_DERIVED_REQUIREMENTS:
    if _req not in COMMUNITY_GATE_REQUIREMENTS:
        raise RuntimeError(
            f"ai_replies_gate_design: community requirement {_req!r} missing from COMMUNITY_GATE_REQUIREMENTS")
_COMMUNITY_DERIVED_GATES: tuple[str, ...] = tuple(f"{_req}_gate" for _req in _COMMUNITY_DERIVED_REQUIREMENTS)
# 기존 어떤 출처에도 없던 신규 게이트(실제 LLM 호출 전 반드시 필요).
_NET_NEW_GATES: tuple[str, ...] = ("llm_provider_gate", "prompt_safety_gate")

# 차단 게이트(하나라도 미충족 → BLOCKED).
BLOCKING_GATES: tuple[str, ...] = (
    "public_readiness_gate",
    "moderation_gate",
    "privacy_gate",
    "audit_log_gate",
)

_RECOMMENDED_NEXT_STEPS: tuple[str, ...] = (
    "implement public_readiness/moderation/privacy/audit_log blocking gates before any runtime is enabled",
    "wire source_citation + uncertainty policy into reply construction",
    "add rate_limit + human_override controls derived from community_interaction_future_gate",
    "add llm_provider gate + prompt_safety gate (net_new) before invoking any LLM",
    "keep runtime_enabled=False and reply_generation_enabled=False until every blocking gate passes and a reviewer approves",
)


def _current_endpoint_status(audit: dict) -> str:
    """live 라우트의 사실을 ai_replies_guard_audit 결과에서 파생. ungated(runtime_enabled True)이면
    "ungated_mock_endpoint"(현재 commit 된 라우트의 사실), gated 면 "gated_mock_endpoint", 미탐지면 "endpoint_absent".
    runtime_enabled 가 권위 신호이고 ungated_risk 가 이를 보강한다(둘 다 audit 출력에서 읽음)."""
    if audit.get("runtime_enabled"):
        return "ungated_mock_endpoint"
    if audit.get("endpoint_detected"):
        return "gated_mock_endpoint"
    return "endpoint_absent"


def build_ai_replies_gate_design(*, satisfied: Optional[dict] = None) -> dict:
    """comment/reply runtime 을 열기 위한 gate-design 계약(runtime 0·LLM 0·엔드포인트 미수정).

    satisfied 는 gate_name→충족여부 맵(옵션·None=전부 미충족). 차단 게이트(public_readiness/moderation/privacy/
    audit_log) 중 하나라도 미충족이면 status=GATE_DESIGN_BLOCKED, 전부 충족이면 GATE_DESIGN_READY(그래도
    runtime_enabled=False 고정). current_endpoint_status·ai_replies_guard_audit_status 는 ai_replies_guard_audit 를
    1회 호출해(정적 텍스트 reader — ai_replies.py 를 import 하지 않음) 그대로 가져온다."""
    satisfied = satisfied or {}

    # 현재 엔드포인트 사실(정적 감사 — import 0·LLM 0·network 0).
    audit = build_ai_replies_guard_audit()
    ai_replies_guard_audit_status = audit["ai_replies_guard_audit_status"]
    current_endpoint_status = _current_endpoint_status(audit)

    required_gates: list[dict] = []
    for gate in _AUDIT_DERIVED_GATES:
        required_gates.append({
            "gate": gate, "must_pass": True,
            "satisfied": bool(satisfied.get(gate)), "source": "ai_replies_guard_audit",
        })
    for gate in _COMMUNITY_DERIVED_GATES:
        required_gates.append({
            "gate": gate, "must_pass": True,
            "satisfied": bool(satisfied.get(gate)), "source": "community_gate",
        })
    for gate in _NET_NEW_GATES:
        required_gates.append({
            "gate": gate, "must_pass": True,
            "satisfied": bool(satisfied.get(gate)), "source": "net_new",
        })

    unmet_blocking_gates = [g for g in BLOCKING_GATES if not satisfied.get(g)]
    status = GATE_DESIGN_BLOCKED if unmet_blocking_gates else GATE_DESIGN_READY

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "ai_replies_gate_design_status": status,
        # ── 필요한 게이트(must_pass=True·충족여부·출처) ──
        "required_gates": required_gates,
        "required_gate_count": len(required_gates),
        "blocking_gates": list(BLOCKING_GATES),
        "unmet_blocking_gates": unmet_blocking_gates,
        # ── 현재 라이브 라우트 사실(ai_replies_guard_audit passthrough) ──
        "current_endpoint_status": current_endpoint_status,
        "ai_replies_guard_audit_status": ai_replies_guard_audit_status,
        # ── runtime guard(이 계약은 어떤 runtime 도 열지 않는다) ──
        "runtime_enabled": False,
        "reply_generation_enabled": False,
        "recommended_next_steps": list(_RECOMMENDED_NEXT_STEPS),
        # ── 정직 불변(하드코딩) — 설계만 한다, 만지지 않는다 ──
        "endpoint_modified": False,
        "llm_invoked": False,
        "reply_generated": False,
        "prompt_executed": False,
        "network_invoked": False,
        "public_post_body_generated": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="ai_replies_gate_design_output")
    return out


def sanitized_ai_replies_gate_design(out: dict) -> dict:
    """frontier 용 aggregate-only 투영(상태 + 핵심 카운트/플래그 subset)."""
    return {
        "operation_name": out["operation_name"],
        "contract_version": out["contract_version"],
        "ai_replies_gate_design_status": out["ai_replies_gate_design_status"],
        "required_gate_count": out["required_gate_count"],
        "unmet_blocking_gates": out["unmet_blocking_gates"],
        "current_endpoint_status": out["current_endpoint_status"],
        "ai_replies_guard_audit_status": out["ai_replies_guard_audit_status"],
        "runtime_enabled": out["runtime_enabled"],
        "reply_generation_enabled": out["reply_generation_enabled"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §15 ai-replies comment/reply runtime gate-design contract (FUTURE·runtime 0·LLM 0·"
                     "엔드포인트 미수정·reply 0·network 0·public post 0)."))
    parser.add_argument("--json", action="store_true", help="sanitized gate-design JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_ai_replies_gate_design()
    if ns.json:
        print(json.dumps(sanitized_ai_replies_gate_design(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['ai_replies_gate_design_status']}")
    print(f"- required_gates ({out['required_gate_count']}): "
          f"{', '.join(g['gate'] for g in out['required_gates'])}")
    print(f"- blocking_gates: {', '.join(out['blocking_gates'])}")
    print(f"- unmet_blocking_gates: {out['unmet_blocking_gates']}")
    print(f"- current_endpoint_status={out['current_endpoint_status']} "
          f"ai_replies_guard_audit_status={out['ai_replies_guard_audit_status']}")
    print(f"- runtime_enabled={out['runtime_enabled']} reply_generation_enabled={out['reply_generation_enabled']}")
    print(f"- invariants: endpoint_modified={out['endpoint_modified']} llm_invoked={out['llm_invoked']} "
          f"reply_generated={out['reply_generated']} prompt_executed={out['prompt_executed']} "
          f"network_invoked={out['network_invoked']} public_post_body_generated={out['public_post_body_generated']} "
          f"production_gold_count={out['production_gold_count']}")
    print(f"- next: {out['recommended_next_steps'][0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
