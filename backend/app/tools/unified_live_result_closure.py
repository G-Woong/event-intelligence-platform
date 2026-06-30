"""ADR#94 — unified live result closure (한 번의 bounded live 결과를 단일 closure 로 묶는 diagnostic·closure only·truth/gold 아님·network 0).

문제(ADR#90~#93 실측): bounded live 를 한 번 돌리면 그 결과를 해석하는 도구가 여섯 개로 흩어져 있다 —
no-yield taxonomy(ADR#90), overlap diagnostics(ADR#91), news breadth trigger(ADR#92 §10), next provider
expansion pack(ADR#93 §15), first freeze package hardening(ADR#92 §11), freeze→R1 executable checklist(ADR#93 §12).
operator 는 "이번 live 가 무엇을 남겼고(payload? no-yield? freeze 후보?) 다음에 무엇을 해야 하는가"를 한 화면에서
받지 못한다.

이 모듈은 그 여섯 단일 출처를 **의존 순서대로 합성(compose)** 해 하나의 closure 로 닫는다(재구현 0·thin orchestration):
  taxonomy → overlap diagnostics → news breadth trigger → next provider expansion → freeze hardening → freeze→R1.
closure 는 dominant gap(payload / news / official / overlap / freeze)을 골라 recommended_iteration 과 operator/R1
next action 을 낸다.

절대 규칙(상속·constant):
  - **no live result without payload**: real payload 가 없으면 closure 는 missing-payload 로 닫고 operator-confirmed-ready
    package 작성을 권한다(live 결과를 단정하지 않는다).
  - **no candidate → no freeze**: freeze 후보(artifact)가 없으면 freeze 는 일어나지 않는다(hardening 은 no_artifact).
  - **closure 는 truth 가 아니고 gold 가 아니다**: same_event 단정 0 · merge 0 · production_gold_count 0 · gold 증가 0 ·
    LLM 0 · network 0 · secret/disk-write 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.first_freeze_package_hardening import (
    build_first_freeze_package_hardening,
)
from backend.app.tools.freeze_to_r1_executable_checklist import (
    build_freeze_to_r1_executable_checklist,
)
from backend.app.tools.live_no_yield_taxonomy import build_live_no_yield_taxonomy
from backend.app.tools.news_breadth_trigger import (
    NBT_FREEZE_SAFETY,
    NBT_OFFICIAL_FIRST,
    NBT_OVERLAP_REFINE,
    NBT_RECOMMEND_NEWS_BREADTH,
    NBT_RECOMMEND_PROVIDER_DATE,
    build_news_breadth_trigger,
)
from backend.app.tools.next_provider_expansion_pack import (
    build_next_provider_expansion_pack,
)
from backend.app.tools.official_news_overlap_diagnostics import (
    build_official_news_overlap_diagnostics,
)
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "unified_live_result_closure"

# dominant gap(이번 live 가 막힌 한 지점·closure 분기의 단일 출처).
GAP_PAYLOAD = "missing_payload"
GAP_NEWS = "news_side_gap"
GAP_OFFICIAL = "official_side_gap"
GAP_OVERLAP = "overlap_gap"
GAP_FREEZE = "freeze_candidate"
GAP_NONE = "no_dominant_gap"

# dominant gap → 다음 iteration 권고 한 줄(operator 가 다음에 시도할 수정). 상위 단일 출처(trigger/pack/hardening)를
# 인용·요약할 뿐 새 정책을 만들지 않는다.
_GAP_TO_ITERATION: dict[str, str] = {
    GAP_PAYLOAD: (
        "compose an operator-confirmed-ready payload and approve a bounded live run "
        "(no live result without a real payload)"),
    GAP_NEWS: (
        "expand the news provider or adjust the date strategy "
        "(next_provider_expansion_pack: GDELT / AP-Reuters-like / window-honoring source)"),
    GAP_OFFICIAL: (
        "adjust the official query/window or broaden the official source first "
        "(official-side gap — do not expand news breadth first)"),
    GAP_OVERLAP: (
        "refine the query overlap (named entity/action) and tighten the date window "
        "so both records fall in-window"),
    GAP_FREEZE: (
        "harden the freeze artifact (first_freeze_package_hardening), then execute the freeze->R1 checklist"),
    GAP_NONE: (
        "no dominant gap detected — re-confirm inputs or run a bounded live with a confirmed operator payload"),
}


def _dominant_gap(*, real_payload_present: bool, freeze_artifact_present: bool, trigger_status: str) -> str:
    """이번 live 가 막힌 지배적 지점(closure 분기). payload 부재 우선 → freeze 후보 → trigger status(official/news/overlap).

    payload 가 없으면 다른 gap 을 단정하지 않는다(live 결과 없음). freeze 후보(artifact)가 있으면 freeze hardening 이
    지배 gap 이다. 그 외에는 news_breadth_trigger 의 분류(NBT_*)를 그대로 인용해 official/news/overlap 으로 가른다."""
    if not real_payload_present:
        return GAP_PAYLOAD
    if freeze_artifact_present:
        return GAP_FREEZE
    if trigger_status == NBT_OFFICIAL_FIRST:
        return GAP_OFFICIAL
    if trigger_status in (NBT_RECOMMEND_NEWS_BREADTH, NBT_RECOMMEND_PROVIDER_DATE):
        return GAP_NEWS
    if trigger_status in (NBT_OVERLAP_REFINE, NBT_FREEZE_SAFETY):
        return GAP_OVERLAP
    return GAP_NONE


def build_unified_live_result_closure(
    *, live_query_executed: bool = False, acquisition_out: Optional[dict] = None,
    payload_entrypoint_out: Optional[dict] = None, overlap_candidates: Optional[list] = None,
    seed: Optional[dict] = None, official_records_count: int = 0, news_records_count: int = 0,
    in_window_news_count: int = 0, bridge_candidate_count: int = 0,
    freeze_artifact: Optional[dict] = None, real_payload_present: bool = False,
    batch_id: Optional[str] = None,
) -> dict:
    """한 번의 bounded live 결과를 여섯 단일 출처로 합성해 단일 closure 로 닫는다(diagnostic·closure only·truth/gold 아님).

    의존 순서: live_no_yield_taxonomy → official_news_overlap_diagnostics → news_breadth_trigger →
    next_provider_expansion_pack → first_freeze_package_hardening → freeze_to_r1_executable_checklist. 각 builder 는
    재구현하지 않고 그대로 호출해 status/next_action 만 인용한다. dominant gap 을 골라 recommended_iteration 과
    operator/R1 next action 을 낸다. 어떤 경로도 merge/gold/LLM/network/secret/disk-write 를 건드리지 않는다."""
    # 1) live no-yield taxonomy — 이번 live 가 왜 candidate 0 인지(payload/official/news/overlap/freeze 세분).
    tax = build_live_no_yield_taxonomy(acquisition_out, payload_entrypoint_out=payload_entrypoint_out)
    tax_status = str(tax["live_no_yield_taxonomy_status"])
    taxonomy_next_action = str(tax["current"]["next_action"])

    # 2) official×news overlap diagnostics — 후보가 있으면 차원별 분해(없으면 not_run·blocked_dimension 빈값).
    ov = build_official_news_overlap_diagnostics(candidates=overlap_candidates, seed=seed)
    overlap_diagnostic_status = str(ov["overlap_diagnostic_status"])
    overlap_blocked_dimension = str(ov["blocked_dimension"])

    # 3) news breadth trigger — taxonomy + overlap dimension + counts → source 확장 필요성(official-first 우선).
    trig = build_news_breadth_trigger(
        live_no_yield_taxonomy_status=tax_status, overlap_blocked_dimension=overlap_blocked_dimension,
        official_records_count=official_records_count, news_records_count=news_records_count,
        in_window_news_count=in_window_news_count, bridge_candidate_count=bridge_candidate_count)
    news_breadth_trigger_status = str(trig["news_breadth_trigger_status"])

    # 4) next provider expansion pack — taxonomy 키 그대로 받아 다음 provider 권고(PLANNING ONLY·실행 0).
    exp = build_next_provider_expansion_pack(
        no_yield_reason=tax_status, news_records_count=news_records_count,
        official_records_count=official_records_count, in_window_news_count=in_window_news_count)
    next_provider_expansion_status = str(exp["next_provider_expansion_status"])

    # 5) first freeze package hardening — freeze 후보 artifact 가 reviewer-facing safe 한지(없으면 no_artifact).
    hard = build_first_freeze_package_hardening(artifact=freeze_artifact)
    freeze_readiness_status = str(hard["freeze_package_hardening_status"])
    freeze_artifact_safe = bool(hard["freeze_artifact_safe"])

    # 6) freeze→R1 executable checklist — freeze 후 contact→label→gold 의 실행 가능한 다음 한 걸음(전송 0·gold 0).
    fr1 = build_freeze_to_r1_executable_checklist(
        freeze_artifact=freeze_artifact, batch_id=batch_id or DEFAULT_BATCH_ID)
    r1_next_action = str(fr1["next_action"])
    freeze_to_r1_status = str(fr1["freeze_to_r1_status"])

    # ── closure 합성 ──
    dominant_gap = _dominant_gap(
        real_payload_present=real_payload_present, freeze_artifact_present=freeze_artifact is not None,
        trigger_status=news_breadth_trigger_status)
    recommended_iteration = _GAP_TO_ITERATION[dominant_gap]

    # operator next action: payload 없으면 ready package 작성; 있으면 freeze/overlap/taxonomy 파생(상위 출처 인용).
    if not real_payload_present:
        operator_next_action = (
            "provide operator-confirmed-ready payload (compose operator_confirmed_ready_package)")
    elif freeze_artifact is not None:
        operator_next_action = str(hard["operator_next_action"])
    elif overlap_blocked_dimension:
        operator_next_action = str(ov["next_action"])
    else:
        operator_next_action = taxonomy_next_action

    # closure status: missing payload > freeze candidate > no-yield(taxonomy 키).
    if not real_payload_present:
        unified_live_closure_status = "closed_missing_payload"
    elif freeze_artifact is not None:
        unified_live_closure_status = "closed_freeze_candidate"
    else:
        unified_live_closure_status = f"closed_no_yield_{tax_status}"

    out = {
        "operation_name": OPERATION_NAME,
        "unified_live_closure_status": unified_live_closure_status,
        "live_query_executed": bool(live_query_executed),
        "real_payload_present": bool(real_payload_present),
        "dominant_gap": dominant_gap,
        # ── 합성한 여섯 단일 출처의 status/next_action(재구현 0·인용). ──
        "live_no_yield_taxonomy_status": tax_status,
        "taxonomy_next_action": taxonomy_next_action,
        "overlap_diagnostic_status": overlap_diagnostic_status,
        "overlap_blocked_dimension": overlap_blocked_dimension,
        "news_breadth_trigger_status": news_breadth_trigger_status,
        "next_provider_expansion_status": next_provider_expansion_status,
        "freeze_readiness_status": freeze_readiness_status,
        "freeze_artifact_safe": freeze_artifact_safe,
        "freeze_to_r1_status": freeze_to_r1_status,
        "r1_next_action": r1_next_action,
        # ── closure 권고. ──
        "operator_next_action": operator_next_action,
        "recommended_iteration": recommended_iteration,
        # ── 규칙(정직·constant). ──
        "no_live_result_without_payload": True,
        "no_candidate_no_freeze": True,
        # ── 불변 경계(하드코딩·closure 는 truth/gold 아님). ──
        "is_truth": False,
        "same_event_asserted": False,
        "merge_allowed": False,
        "llm_invoked": False,
        "network_invoked": False,
        "production_gold_count": 0,
        "increases_gold": False,
    }
    _assert_pii_safe(out, _path="unified_live_result_closure_output")
    return out


def sanitized_unified_live_result_closure(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status + 권고 + 핵심 불변·prose next_action 1개만)."""
    return {
        "unified_live_closure_status": out["unified_live_closure_status"],
        "live_query_executed": out["live_query_executed"],
        "dominant_gap": out["dominant_gap"],
        "live_no_yield_taxonomy_status": out["live_no_yield_taxonomy_status"],
        "overlap_diagnostic_status": out["overlap_diagnostic_status"],
        "news_breadth_trigger_status": out["news_breadth_trigger_status"],
        "next_provider_expansion_status": out["next_provider_expansion_status"],
        "freeze_readiness_status": out["freeze_readiness_status"],
        "freeze_to_r1_status": out["freeze_to_r1_status"],
        "recommended_iteration": out["recommended_iteration"],
        "is_truth": out["is_truth"],
        "production_gold_count": out["production_gold_count"],
        "increases_gold": out["increases_gold"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 unified live result closure (한 번의 bounded live 결과를 여섯 단일 출처로 합성해 단일 "
                     "closure 로 닫음; diagnostic·closure only·truth/gold 아님·merge 0·LLM 0·network 0·전송 0)."))
    parser.add_argument("--real-payload", action="store_true",
                        help="real operator payload present(미지정 시 missing-payload closure).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_unified_live_result_closure(real_payload_present=ns.real_payload)
    if ns.json:
        print(json.dumps(sanitized_unified_live_result_closure(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['unified_live_closure_status']} "
          f"dominant_gap={out['dominant_gap']}")
    print(f"- taxonomy={out['live_no_yield_taxonomy_status']} overlap={out['overlap_diagnostic_status']}"
          f"({out['overlap_blocked_dimension'] or 'none'}) trigger={out['news_breadth_trigger_status']} "
          f"expansion={out['next_provider_expansion_status']}")
    print(f"- freeze: readiness={out['freeze_readiness_status']} safe={out['freeze_artifact_safe']} "
          f"r1={out['freeze_to_r1_status']}")
    print(f"- recommended_iteration: {out['recommended_iteration']}")
    print(f"- operator_next_action: {out['operator_next_action']}")
    print(f"- r1_next_action: {out['r1_next_action']}")
    print(f"- invariants: is_truth={out['is_truth']} same_event={out['same_event_asserted']} "
          f"merge={out['merge_allowed']} llm={out['llm_invoked']} network={out['network_invoked']} "
          f"production_gold_count={out['production_gold_count']} increases_gold={out['increases_gold']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
