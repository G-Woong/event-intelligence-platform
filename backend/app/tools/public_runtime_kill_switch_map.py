"""ADR#94 — public runtime kill-switch map (모든 public runtime 기본 DISABLED·override 불가·network 0).

미래 제품은 hot post 공개 게시, 댓글 응답, public Intelligence Unit, LLM 생성, embedding, KG, DB write,
실제 발송 같은 **공개 runtime** 을 연다. 그러나 그 어떤 것도 R1(production gold)·R2(MERGE_GATE) 가 끝나고
명시 ADR + tests 가 갖춰지기 전에는 열려선 안 된다. 이 모듈은 그 **kill-switch map** 이다 — 8개 public
runtime 을 한 곳에서 **기본 DISABLED** 로 선언하고, 각 runtime 이 *이미 어디서 강제되는지* 를 단일 출처 게이트로
**COMPOSE/cite** 한다(truth 재선언 0). 이 모듈은 어떤 runtime 도 켜지 않으며 network/DB/LLM/embedding/전송 0.

**COMPOSE, not re-declare**:
  - comment_reply_runtime 의 disabled 는 `community_interaction_future_gate.build_community_interaction_future_gate`
    의 `comment_reply_generation=False`(ADR#90) 에서 **파생**(재선언 0).
  - public_hot_post_runtime 의 disabled 는 `hot_post_gate_alignment.build_hot_post_gate_alignment` 의
    `runtime_enabled=False`·`publishable=False`(ADR#91 §13) 에서 **파생**(재선언 0).
  - 나머지(public_iu/llm/embedding/kg/db_write/actual_sending)는 무거운 모듈(`internal_ops_preflight` 은 호출 시
    filesystem 스캔 + settings 접근으로 **순수하지 않음**)을 *import 하지 않고* 기존 상수를 **static citation 문자열**
    로만 인용한다(config 기본 LLM_PROVIDER/EMBEDDING_PROVIDER='mock' · no_db_write · public IU/KG No-Go ·
    actual_sending_performed=False).

절대 불변(ADR#94): 모든 public runtime 기본 disabled · R1/R2 전 override 0 · override 는 명시 ADR + tests 필요 ·
public post body 0 · comment reply 0 · DB write 0 · LLM/embedding 실호출 0 · 실 발송 0 · merge 0 · public IU 0 ·
network 0 · 이 모듈은 어떤 runtime 도 켜지 않는다(계약/계획 정의만·`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.community_interaction_future_gate import (
    build_community_interaction_future_gate,
)
from backend.app.tools.hot_post_gate_alignment import build_hot_post_gate_alignment
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "public_runtime_kill_switch_map"
CONTRACT_VERSION = "public_runtime_kill_switch_map_v1"

PRKS_ALL_DISABLED = "public_runtime_kill_switch_all_disabled"

# 8개 public runtime 차원(전부 기본 DISABLED·순서 고정).
PUBLIC_RUNTIME_DIMENSIONS: tuple[str, ...] = (
    "public_hot_post_runtime",
    "comment_reply_runtime",
    "public_iu_runtime",
    "llm_generation_runtime",
    "embedding_runtime",
    "kg_runtime",
    "db_write_runtime",
    "actual_sending_runtime",
)


def build_public_runtime_kill_switch_map(
    *, r1_satisfied: bool = False, r2_satisfied: bool = False,
) -> dict:
    """8개 public runtime 을 기본 DISABLED 로 선언하는 kill-switch map(network 0·어떤 runtime 도 켜지 않는다).

    comment_reply / public_hot_post 의 disabled 는 community_interaction_future_gate / hot_post_gate_alignment
    단일 출처 게이트에서 **파생**(재선언 0)하고, 나머지(public_iu/llm/embedding/kg/db_write/actual_sending)는 기존
    상수를 static citation 으로 인용한다. operator override 는 R1(gold) AND R2(MERGE_GATE) AND 명시 ADR AND tests
    가 모두 있어야만 가능 — 이번 턴엔 R1/R2 도 미충족이고 override 전용 ADR/tests 도 없어 **항상 False**."""
    # ── COMPOSE: 2개 차원은 순수(no I/O) 단일-출처 게이트에서 disabled 를 파생 ──
    community = build_community_interaction_future_gate()
    hot_post = build_hot_post_gate_alignment()

    comment_reply_disabled = community["comment_reply_generation"] is False
    public_hot_post_disabled = (
        hot_post["runtime_enabled"] is False and hot_post["publishable"] is False
    )

    disabled_dimensions: list[dict] = [
        {
            "dimension": "public_hot_post_runtime",
            "disabled": public_hot_post_disabled,
            "enforced_by": ("hot_post_gate_alignment.build_hot_post_gate_alignment: "
                            "runtime_enabled=False, publishable=False (ADR#91 §13)"),
        },
        {
            "dimension": "comment_reply_runtime",
            "disabled": comment_reply_disabled,
            "enforced_by": ("community_interaction_future_gate.build_community_interaction_future_gate: "
                            "comment_reply_generation=False (ADR#90 §14)"),
        },
        {
            "dimension": "public_iu_runtime",
            "disabled": True,
            "enforced_by": ("internal_ops_preflight: no_public_intelligence_unit, R7 public IU No-Go "
                            "until all gates pass (ADR#73 §7)"),
        },
        {
            "dimension": "llm_generation_runtime",
            "disabled": True,
            "enforced_by": ("config default LLM_PROVIDER='mock' (no real LLM call); "
                            "internal_ops_preflight llm_invoked=False (ADR#73)"),
        },
        {
            "dimension": "embedding_runtime",
            "disabled": True,
            "enforced_by": ("config default EMBEDDING_PROVIDER='mock' (no real embedding call); "
                            "internal_ops_preflight embedding_invoked=False (ADR#73)"),
        },
        {
            "dimension": "kg_runtime",
            "disabled": True,
            "enforced_by": ("internal_ops_preflight R5 KG edge building No-Go "
                            "(entity provenance absent) (ADR#73 §7)"),
        },
        {
            "dimension": "db_write_runtime",
            "disabled": True,
            "enforced_by": "internal_ops_preflight db_write=False / no_db_write invariant (ADR#73)",
        },
        {
            "dimension": "actual_sending_runtime",
            "disabled": True,
            "enforced_by": ("reviewer_pilot_handoff actual_sending_performed=False "
                            "(operator manual; no email/slack/webhook) (ADR#70)"),
        },
    ]
    # 차원 집합 정합(8개·순서 고정·드리프트 fail-loud).
    if tuple(d["dimension"] for d in disabled_dimensions) != PUBLIC_RUNTIME_DIMENSIONS:
        raise ValueError("disabled_dimensions drifted from PUBLIC_RUNTIME_DIMENSIONS (8 fixed runtimes)")

    all_public_runtime_disabled = all(d["disabled"] for d in disabled_dimensions)
    # 합성한 단일-출처 게이트가 enabled 로 드리프트하면 즉시 fail-loud(이 모듈은 truth 를 재선언하지 않고 게이트를 신뢰).
    if not all_public_runtime_disabled:
        raise ValueError("a composed public runtime reports enabled — kill switch invariant violated")

    # ── override gate: R1(gold) AND R2(merge) AND 명시 ADR AND tests 가 **모두** 필요 ──
    # (r1_satisfied and r2_satisfied) 가 r1/r2 입력을 demonstrably gate 하고, 마지막 항(explicit_adr_and_tests_present)
    # 은 이번 턴 False 라 operator_override_allowed = (r1 and r2) and False → 항상 False.
    gate_inputs_satisfied = bool(r1_satisfied) and bool(r2_satisfied)
    explicit_adr_and_tests_present = False   # 이번 턴: override 전용 ADR/tests 없음(ADR#94 는 contract/planning-only).
    operator_override_allowed = gate_inputs_satisfied and explicit_adr_and_tests_present

    required_gates: list[dict] = [
        {"gate": "r1_production_gold", "must_pass": True, "satisfied": bool(r1_satisfied),
         "enforced_by": "internal_ops_preflight R1 production gold floor (live >=200 / KO >=50)"},
        {"gate": "r2_merge_gate", "must_pass": True, "satisfied": bool(r2_satisfied),
         "enforced_by": "internal_ops_preflight R2 MERGE_GATE precision >=0.98 / FPR <=0.01"},
        {"gate": "explicit_runtime_override_adr", "must_pass": True, "satisfied": False,
         "enforced_by": "no override ADR yet — ADR#94 is contract/planning-only"},
        {"gate": "override_tests", "must_pass": True, "satisfied": False,
         "enforced_by": "override_requires_tests (the override path must ship with passing tests)"},
    ]

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "public_runtime_kill_switch_status": PRKS_ALL_DISABLED,
        "all_public_runtime_disabled": all_public_runtime_disabled,
        "disabled_dimensions": disabled_dimensions,
        "disabled_dimension_count": len(disabled_dimensions),
        "public_runtime_dimensions": list(PUBLIC_RUNTIME_DIMENSIONS),
        # ── COMPOSE passthrough(단일 출처 게이트 상태·재선언 0) ──
        "references_community_interaction_gate": True,
        "community_interaction_gate_status": community["community_interaction_gate_status"],
        "references_hot_post_gate_alignment": True,
        "hot_post_gate_status": hot_post["hot_post_gate_status"],
        # ── override gate(R1/R2/ADR/tests 모두 필요·이번 턴 모두 미충족) ──
        "required_gates": required_gates,
        "r1_satisfied": bool(r1_satisfied),
        "r2_satisfied": bool(r2_satisfied),
        "gate_inputs_satisfied": gate_inputs_satisfied,
        "explicit_adr_and_tests_present": explicit_adr_and_tests_present,
        "operator_override_allowed": operator_override_allowed,
        "override_requires_tests": True,
        "override_requires_explicit_adr": True,
        # ── 이 모듈 자체 불변(정직·constant: 무엇도 실행/생성/전송하지 않음) ──
        "public_post_body_generated": False,
        "comment_reply_generated": False,
        "db_write": False,
        "llm_invoked": False,
        "embedding_invoked": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "network_invoked": False,
        "public_iu_allowed": False,
        "recommended_action": (
            "all 8 public runtimes stay DISABLED by default; an operator override opens nothing until "
            "R1 production gold AND R2 MERGE_GATE AND an explicit runtime-override ADR AND passing override "
            "tests are all present — none are met this turn, so the kill switch holds (contract/planning-only; "
            "opens no public post, comment reply, public IU, LLM, embedding, KG, DB write, or sending)"),
    }
    # 전체 출력 재귀 forbidden-key 가드(PII/secret/score/rationale 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(out, _path="public_runtime_kill_switch_map_output")
    return out


def sanitized_public_runtime_kill_switch_map(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(dimension 본문 제외·status/count/flag 만)."""
    return {
        "public_runtime_kill_switch_status": out["public_runtime_kill_switch_status"],
        "all_public_runtime_disabled": out["all_public_runtime_disabled"],
        "disabled_dimension_count": out["disabled_dimension_count"],
        "operator_override_allowed": out["operator_override_allowed"],
        "override_requires_tests": out["override_requires_tests"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 public runtime kill-switch map (8 public runtime 기본 DISABLED·override 는 R1 gold AND "
                     "R2 MERGE_GATE AND 명시 ADR AND tests 필요·public post 0·comment reply 0·DB 0·LLM 0·전송 0·network 0)."))
    parser.add_argument("--json", action="store_true", help="kill-switch map JSON 출력(dimension 본문 포함).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_public_runtime_kill_switch_map()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['public_runtime_kill_switch_status']} "
          f"all_public_runtime_disabled={out['all_public_runtime_disabled']}")
    print(f"- disabled runtimes ({out['disabled_dimension_count']}):")
    for d in out["disabled_dimensions"]:
        print(f"    - {d['dimension']} [disabled={d['disabled']}] enforced_by={d['enforced_by']}")
    print(f"- override: operator_override_allowed={out['operator_override_allowed']} "
          f"r1_satisfied={out['r1_satisfied']} r2_satisfied={out['r2_satisfied']} "
          f"requires_explicit_adr={out['override_requires_explicit_adr']} requires_tests={out['override_requires_tests']}")
    print(f"- required_gates: {[g['gate'] for g in out['required_gates']]}")
    print(f"- invariants: public_post_body={out['public_post_body_generated']} comment_reply={out['comment_reply_generated']} "
          f"db_write={out['db_write']} llm={out['llm_invoked']} embedding={out['embedding_invoked']} "
          f"sending={out['actual_sending_performed']} network={out['network_invoked']} public_iu={out['public_iu_allowed']}")
    print(f"- recommended_action: {out['recommended_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
