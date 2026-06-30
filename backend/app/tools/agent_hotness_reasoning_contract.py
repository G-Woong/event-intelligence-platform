"""ADR#90 — agent hotness reasoning contract (어떤 사건이 '사람이 흥미로워할' 것인지 고르는 기준·runtime 금지).

미래의 에이전트는 전세계 사건 중 **사람이 흥미로워할 것**을 스스로 골라 수집·정제·게시하려 한다. 그 선정 기준이
없으면 (a) 흥미를 LLM 환각으로 지어내거나, (b) community buzz 를 증거로 둔갑시키거나, (c) hotness 만으로 게시하는
위험이 있다. `19_SPEC §2.4 heat`(decay/ranking score)는 *랭킹* 신호일 뿐 *human-interest 선정 rubric* 이 아니다.

이 모듈은 그 **선정 reasoning 계약** 이다(runtime 0·contract only):
  - criteria: novelty·stakes·social impact·conflict·controversy·human curiosity·community reaction potential·
    official evidence availability·cross-source corroboration·time sensitivity·follow-up potential·local/global
    relevance·uncertainty/risk·safety sensitivity.
  - output: hotness_candidate·hotness_reasoning_summary·evidence_requirements·source_requirements·
    community_layer_requirements·publish_blockers·next_collection_actions.
  - **hotness ≠ publish ≠ truth**: hotness 는 *수집/우선순위* 신호일 뿐. 게시는 official 증거·human label·MERGE_GATE
    뒤에만(publish_blockers 가 항상 그 선행 게이트를 명시). community buzz 는 anchor 아님(reaction_to only).

절대 불변(§13·§19): hotness 만으로 게시 0 · hotness 를 truth 로 0 · community buzz 를 evidence anchor 로 0 · LLM 으로
흥미 환각 0 · runtime 0 · merge 0 · same_event 단정 0 · secret/PII/score 미노출. **이 모듈은 고르되 게시하지 않는다.**
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "agent_hotness_reasoning_contract"
CONTRACT_VERSION = "agent_hotness_reasoning_v1"

# §13 human-interest 선정 criteria.
HOTNESS_CRITERIA: tuple[str, ...] = (
    "novelty", "stakes", "social_impact", "conflict", "controversy", "human_curiosity",
    "community_reaction_potential", "official_evidence_availability", "cross_source_corroboration",
    "time_sensitivity", "follow_up_potential", "local_relevance", "global_relevance",
    "uncertainty_risk", "safety_sensitivity",
)

# §13 output 필드.
HOTNESS_OUTPUT_FIELDS: tuple[str, ...] = (
    "hotness_candidate", "hotness_reasoning_summary", "evidence_requirements", "source_requirements",
    "community_layer_requirements", "publish_blockers", "next_collection_actions",
)

# §13 forbidden.
HOTNESS_FORBIDDEN: tuple[str, ...] = (
    "publish based on hotness alone",
    "treat hotness as truth",
    "use community buzz as an evidence anchor",
    "use an LLM to hallucinate interest",
)

# 게시 전 항상 요구되는 선행 게이트(hotness 가 아무리 높아도 이걸 건너뛸 수 없다).
_PUBLISH_BLOCKERS_ALWAYS: tuple[str, ...] = (
    "hotness_alone_does_not_publish",
    "requires_official_evidence",
    "requires_cross_source_corroboration",
    "requires_human_label_provenance",
    "requires_merge_gate",
    "requires_public_iu_gate",
)


def build_agent_hotness_reasoning_contract() -> dict:
    """human-interest 선정 reasoning 계약(runtime 0·contract only). 고르되 게시하지 않는다."""
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "runtime_enabled": False,
        "criteria": list(HOTNESS_CRITERIA),
        "criteria_count": len(HOTNESS_CRITERIA),
        "output_fields": list(HOTNESS_OUTPUT_FIELDS),
        "forbidden": list(HOTNESS_FORBIDDEN),
        # ── 불변 경계 ──
        "hotness_is_truth": False,
        "can_publish_on_hotness_alone": False,
        "community_buzz_is_evidence_anchor": False,
        "llm_invoked": False,
        "merge_allowed": False,
        "public_iu_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="agent_hotness_reasoning_contract_output")
    return out


def evaluate_hotness_candidate(signals: Optional[dict] = None) -> dict:
    """criteria 신호(dict·옵션) → hotness 후보 reasoning + 선행 요구/게시 blocker(runtime 0·게시 0).

    signals 는 criteria→신호(예: novelty=0.8·stakes='high') 맵. 이 함수는 *어떤 criteria 가 흥미를 시사하는지* 를
    요약하고, **게시 전 반드시 필요한 evidence/source/community 요구** 와 **publish_blockers**(항상 비어있지 않음)를
    낸다. hotness 가 아무리 높아도 publishable 아님(official 증거·human label·MERGE_GATE 뒤에만). community 는 reaction_to."""
    signals = signals or {}
    fired = [c for c in HOTNESS_CRITERIA if signals.get(c)]
    summary = ("hotness signals present: " + ", ".join(fired)) if fired else "no hotness signals provided"
    out = {
        "operation_name": OPERATION_NAME,
        "runtime_enabled": False,
        # hotness 후보(수집/우선순위 신호일 뿐·truth/publish 아님).
        "hotness_candidate": bool(fired),
        "fired_criteria": fired,
        "fired_criteria_count": len(fired),
        "hotness_reasoning_summary": summary,
        # 게시 전 선행 요구(항상 비어있지 않음).
        "evidence_requirements": [
            "official_evidence (e.g. Federal Register / authoritative record)",
            "cross_source_corroboration (independent news reporting)",
            "uncertainty made visible",
        ],
        "source_requirements": [
            "anchor role must be official or news (community/market/catalog are NOT anchors)",
            "search URL candidates are not truth until fetched",
        ],
        "community_layer_requirements": [
            "community reaction attaches as reaction_to AFTER a verified event (never an anchor)",
        ],
        "publish_blockers": list(_PUBLISH_BLOCKERS_ALWAYS),
        "next_collection_actions": [
            "collect the official record for the candidate event",
            "collect independent news corroboration in the same window",
            "route plausible official×news pairs to human reviewers (not a same-event assertion)",
        ],
        # ── 불변 경계 ──
        "can_publish_on_hotness_alone": False,
        "community_buzz_is_evidence_anchor": False,
        "hotness_is_truth": False,
        "llm_invoked": False,
        "merge_allowed": False,
        "r2_r7_no_go": True,
    }
    _assert_pii_safe(out, _path="hotness_candidate_output")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 agent hotness reasoning contract (human-interest 선정 기준·runtime 0·hotness 만으로 게시 0·"
                     "hotness=truth 0·community buzz anchor 0·LLM 흥미 환각 0)."))
    parser.add_argument("--json", action="store_true", help="contract JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_agent_hotness_reasoning_contract()
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} version={out['contract_version']} "
          f"runtime_enabled={out['runtime_enabled']}")
    print(f"- criteria ({out['criteria_count']}): {', '.join(out['criteria'])}")
    print(f"- output_fields: {', '.join(out['output_fields'])}")
    print(f"- can_publish_on_hotness_alone={out['can_publish_on_hotness_alone']} "
          f"hotness_is_truth={out['hotness_is_truth']} community_buzz_anchor={out['community_buzz_is_evidence_anchor']}")
    print("- forbidden:")
    for f in out["forbidden"]:
        print(f"    - {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
