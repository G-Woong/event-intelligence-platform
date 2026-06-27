"""ADR#74 — R1 production gold acquisition operating plan (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#72/#73 이 만든 것: actual input gate(gitignored 입력 스캔·no_actual_input 정직) + internal ops auth/deploy
preflight + R1~R7 readiness matrix. 그러나 R1(production gold floor)은 readiness matrix 의 한 행(`FAIL`)일 뿐 —
"실제 라벨을 얼마나/어떤 분포로 모아야 하고, 지금 무엇이 비어 있으며, operator 가 다음에 무엇을 수동으로 해야
하는가"를 **하나로 집계한 운영 plan**이 없었다. 더 이상 reviewer scaffold 만 늘리지 않는다(Lane A) — actual
returned labels 가 R1 gold floor 의 **유일한 해제 조건**이고, 그것을 얻기 위한 operator-facing acquisition plan 이
이번 턴의 산출물이다.

이 모듈은 **재구현이 아니라 집계 + 재확인 wrapper** 다. 무거운 일은 전부 단일 출처가 한다:
  - actual input 재확인 + production_gold_count/calibration/merge_gate/granular breakdown: 단일 호출
    `reviewer_actual_input_gate.run_actual_input_gate`(재호출 0). 게이트가 gitignored 입력을 스캔(생성 0·날조 0)해
    no_actual_input/external_input_required 를 정직 산출하고, calibration_delta(baseline 없음→delta==current)로
    positive/negative/korean current count 을 노출한다.
  - target floor: canonical 상수 재사용 — `identity_human_labeling.GOLD_MERGE_MIN_LIVE_GOLD`(200)·
    `GOLD_MERGE_MIN_KOREAN_GOLD`(50)·`DEFAULT_REVIEWERS_PER_PAIR`(2). balance/hard-negative per-class floor 만
    ADR#74 가 그 위에서 파생(아래 정책 상수)한다.
  - PII 재귀 가드: `reviewer_pilot_handoff._assert_pii_safe`(재사용).

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **R1 status(§4·4-state)**: blocked_no_labels/collecting/partially_satisfied/satisfied — returned labels·
    production gold·calibration 으로 파생(no_actual_input 을 성공으로 둔갑 0).
  - **gap 산술(§4)**: required − current(production/korean/positive/negative/hard-negative/reviewer) — gap 을
    internal ops API/UI 에서 보이게 하고 operator next manual action 을 도출.
  - **operator-facing acquisition plan(§4·Lane A/B)**: recruitment/placement/contact-evidence/SLA 가 이미
    substrate 에 존재함을 readiness 로 표면화하고 next_manual_actions 로 묶는다(실제 전송 0·파일 생성 0).

절대 불변(상속·상용 안전 계약):
  - **입력 날조 0·production_gold_count exact passthrough**: gold/calibration/merge_gate 는 전부 게이트 결과
    그대로. plan 만으로 증가 0. 실 production human label 파일이 없으면 0(synthetic/test/model 둔갑 0).
  - **target ≠ 충족**: required floor 는 *operating floor* 일 뿐 production truth 가 아니다. R1 satisfied 는
    calibration_ready(전 sub-floor 충족)일 때만.
  - **no merge / no public IU / no DB / no LLM / no embedding / no 전송**: 전 경로 상속(게이트 파생 + 상수).
  - **internal ops ≠ public truth**: gap/next-action 은 workflow 상태만. same_event 확정·verified gold 렌더 0.
  - **secret 0 / raw PII 0 / score·rationale·predicted_status 숨김**: 게이트 파생 + 전체 재귀 가드.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    GOLD_MERGE_MIN_KOREAN_GOLD,
    GOLD_MERGE_MIN_LIVE_GOLD,
)
from backend.app.tools.reviewer_actual_input_gate import run_actual_input_gate
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "r1_gold_acquisition_operating_plan"

# ── §4 R1 status(4-state·acquisition 축) ────────────────────────────────────────────────────────────────
# blocked_no_labels: actual returned labels 0(현재·유일 해제조건 미충족). collecting: 라벨 회수 중이나 총량 floor
# 미달. partially_satisfied: 총량 floor 충족이나 sub-floor(korean/balance/negative) 미충족. satisfied:
# calibration_ready(전 sub-floor 충족·MERGE_GATE review 대상). satisfied 도 자동 merge 아님(adversarial 승인 필요).
R1_BLOCKED_NO_LABELS = "blocked_no_labels"
R1_COLLECTING = "collecting"
R1_PARTIALLY_SATISFIED = "partially_satisfied"
R1_SATISFIED = "satisfied"
R1_STATES = frozenset({R1_BLOCKED_NO_LABELS, R1_COLLECTING, R1_PARTIALLY_SATISFIED, R1_SATISFIED})

# ── §5 R1 target floor(canonical 재사용 + ADR#74 파생 정책) ──────────────────────────────────────────────
# canonical(단일 출처·identity_human_labeling): live ≥200 / KO ≥50 / pair 당 reviewer ≥2.
REQUIRED_PRODUCTION_GOLD = GOLD_MERGE_MIN_LIVE_GOLD       # 200(live-derived decisive gold floor).
REQUIRED_KOREAN_GOLD = GOLD_MERGE_MIN_KOREAN_GOLD         # 50(한국어 calibration floor·평균 뒤에 숨기지 않음).
REVIEWER_DUPLICATION_REQUIRED = DEFAULT_REVIEWERS_PER_PAIR  # 2(single reviewer=insufficient·gold 아님).
# ADR#74 파생 정책(operating floor — production truth 아님):
#   positive/negative per-class floor = ceil(total/3). balance 정책(ratio≥0.5·max:min≤2:1)을 총량 200 에서
#   만족시키는 최소 class 표본 = ceil(200/3)=67(= 정수 나눗셈 `(200+2)//3`). 양/음성 모두 floor 이상이어야 함.
REQUIRED_POSITIVE_GOLD = (REQUIRED_PRODUCTION_GOLD + 2) // 3   # 67
REQUIRED_NEGATIVE_GOLD = (REQUIRED_PRODUCTION_GOLD + 2) // 3   # 67
#   hard-negative gold floor = 20. MERGE_GATE 의 hard_negative_false_positive_max=0 을 *의미있게* 측정하려면
#   trap-zone hard negative 표본이 필요(표본 0 위의 FP=0 은 공허). 20 은 ADR#74 가 정한 evaluator floor.
REQUIRED_HARD_NEGATIVE = 20

# R1 plan 이 표면화하는 operator 산출물의 readiness(각자 자체 모듈/테스트로 검증 — plan 은 표면화만).
#   - contact evidence 양식: reviewer_pilot_execution.CONTACT_EVIDENCE_ALLOWED_KEYS(PII-safe allowlist).
#   - returned label 양식: reviewer_batch_launch.build_label_template / pilot_handoff._label_template_schema.
#   - placement guide: reviewer_batch_launch.build_intake_plan(intake_directory/expected_files/validation_command).
#   - R1 gap 가시성: ADR#74 옵션 C(GET /api/internal/ops/r1-gold-acquisition + frontend R1 패널).
#   - source storage strategy: ADR#74 옵션 D(RAG_KG_AGENT_READINESS source-role storage strategy).
CONTACT_EVIDENCE_TEMPLATE_READY = True
RETURNED_LABEL_TEMPLATE_READY = True
RETURNED_LABEL_PLACEMENT_GUIDE_READY = True
INTERNAL_OPS_R1_GAP_VISIBLE = True
SOURCE_STORAGE_STRATEGY_UPDATED = True


def _r1_status(*, returned_label_count: int, production_gold_count: int, calibration_ready: bool) -> str:
    """R1 acquisition status 를 게이트 파생값에서 산출(no_actual_input 둔갑 0).

    returned 0 → blocked_no_labels(유일 해제조건 미충족). calibration_ready → satisfied(전 sub-floor 충족).
    총량 floor 충족이나 미캘리브레이션 → partially_satisfied. 그 외(라벨 회수 중·총량 미달) → collecting."""
    if returned_label_count <= 0:
        return R1_BLOCKED_NO_LABELS
    if calibration_ready:
        return R1_SATISFIED
    if production_gold_count >= REQUIRED_PRODUCTION_GOLD:
        return R1_PARTIALLY_SATISFIED
    return R1_COLLECTING


def _current_gold_breakdown(gate: dict) -> dict:
    """granular current gold count(positive/negative/korean/hard-negative)을 게이트에서 정직 도출.

    production_gold_count==0 이면 모든 bucket=0(gold bucket 은 gold 의 부분집합·증명가능). >0 이면 게이트의
    calibration_delta 에서 읽되, 게이트는 baseline 없이 호출되므로 delta==current 다 —
    before_production_gold_count!=0 이면 그 불변이 깨진 것이므로 fail-loud(조용한 오집계 차단).
    hard-negative gold 는 별도 surface 가 아직 없어 0(라벨 도착 후 intake 가 thread 할 때까지 정직 0)."""
    prod = gate["production_gold_count"]
    if prod <= 0:
        return {"positive": 0, "negative": 0, "korean": 0, "hard_negative": 0}
    delta = gate["calibration_delta"]
    if delta.get("before_production_gold_count", 0) != 0:
        raise ValueError(
            "calibration_delta baseline must be zero for R1 current-count derivation "
            "(R1 plan calls the gate without a calibration baseline).")
    return {
        "positive": delta["positive_delta"],
        "negative": delta["negative_delta"],
        "korean": delta["korean_delta"],
        "hard_negative": 0,   # hard-negative gold 별도 surface 부재 — 라벨 도착 시 thread(현재 정직 0).
    }


def run_r1_gold_acquisition_plan(
    *, directory: Optional[Any] = None, batch_id: str = "reviewer_pilot_exec_001",
    as_of: Optional[str] = None,
) -> dict:
    """R1 production gold acquisition operating plan(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    1) actual input 재확인: 단일 출처 게이트로 no_actual_input/external_input_required + production_gold_count +
       calibration/merge_gate + granular breakdown 정직 산출,
    2) target floor(canonical 200/50/2 + ADR#74 파생 67/67/20)와 current 의 gap 산술,
    3) R1 status(4-state)·operator next manual action·산출물 readiness 표면화.
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read 를 하지 않는다."""
    gate = run_actual_input_gate(directory=directory, batch_id=batch_id, as_of=as_of)

    prod = gate["production_gold_count"]
    returned = gate["returned_label_count"]
    cur = _current_gold_breakdown(gate)
    # reviewer current = contact evidence 로 접촉 확인된 **global** reviewer 수(engaged). 라벨 제출 reviewer 의 상위
    # proxy — 미접촉/무입력이면 0(둔갑 0). **per-pair coverage 증명이 아니다**(global engaged count): reviewer_gap 은
    # "최소 2명 engaged" 의 coarse acquisition 신호일 뿐, pair 당 2-reviewer 중복은 하류 intake→agreement 가 강제한다.
    # 어떤 gate(r1_status/merge_gate)도 reviewer_gap 을 입력으로 쓰지 않는다(거짓 통과 0·adversarial #10).
    cur_reviewers = gate["real_reviewers_contacted"]

    label_collection_gap = max(0, REQUIRED_PRODUCTION_GOLD - prod)
    korean_gap = max(0, REQUIRED_KOREAN_GOLD - cur["korean"])
    positive_gap = max(0, REQUIRED_POSITIVE_GOLD - cur["positive"])
    negative_gap = max(0, REQUIRED_NEGATIVE_GOLD - cur["negative"])
    hard_negative_gap = max(0, REQUIRED_HARD_NEGATIVE - cur["hard_negative"])
    reviewer_gap = max(0, REVIEWER_DUPLICATION_REQUIRED - cur_reviewers)

    r1_status = _r1_status(
        returned_label_count=returned, production_gold_count=prod,
        calibration_ready=gate["calibration_ready"])

    # operator-facing next manual actions(실제 전송 0·파일 생성 0 — operator 수동). 게이트 next_action(배포/적재
    # 경로)을 묶고 recruitment/target/adjudication 을 앞에 둔다.
    next_manual_actions = [
        f"recruit ≥{REVIEWER_DUPLICATION_REQUIRED} reviewers per pair (pseudonymous ids; raw roster/mapping local-only, never committed)",
        "distribute the existing handoff bundle to reviewers manually (no system email/slack/webhook sending)",
        f"collect returned label JSONL into the gitignored intake directory ({gate['input_directory']}) and run the validation command",
        f"target floor: live ≥{REQUIRED_PRODUCTION_GOLD} / KO ≥{REQUIRED_KOREAN_GOLD} decisive gold; "
        f"balanced positive ≥{REQUIRED_POSITIVE_GOLD} and negative ≥{REQUIRED_NEGATIVE_GOLD}; hard-negative ≥{REQUIRED_HARD_NEGATIVE}",
        "two-reviewer agreement required; resolve conflicts by human-only adjudication (no auto-majority gold)",
    ]
    next_actions = next_manual_actions + list(gate["next_actions"])

    block_reasons: list[str] = []
    if r1_status == R1_BLOCKED_NO_LABELS:
        block_reasons.append("r1_blocked_no_actual_returned_labels")
    elif r1_status == R1_COLLECTING:
        block_reasons.append("r1_collecting_below_gold_floor")
    elif r1_status == R1_PARTIALLY_SATISFIED:
        block_reasons.append("r1_sub_floor_unmet")
    block_reasons.extend(gate["block_reasons"])
    block_reasons = list(dict.fromkeys(block_reasons))

    flags = {
        "internal_only": True,
        "no_public_truth": True,
        "no_merge": True,
        "no_public_iu": True,
        "pii_safe": True,
        "no_llm": True,
        "no_db_write": True,
        "gold_provenance_verified": False,   # production gold 무결성 선언 기반(provenance 미검증) — readiness 근거 인용 금지.
    }

    # API/UI 화이트리스트 contract(sanitized·forbidden 필드 없음·public truth 아님).
    r1_contract = {
        "contract": "InternalOpsR1AcquisitionStatus",
        "r1_status": r1_status,
        "actual_input_status": gate["actual_input_status"],
        "external_input_required": gate["external_input_required"],
        "current_production_gold_count": prod,
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_korean_gold_count": cur["korean"],
        "required_korean_gold_count": REQUIRED_KOREAN_GOLD,
        "current_positive_gold_count": cur["positive"],
        "current_negative_gold_count": cur["negative"],
        "required_positive_gold_count": REQUIRED_POSITIVE_GOLD,
        "required_negative_gold_count": REQUIRED_NEGATIVE_GOLD,
        "current_hard_negative_count": cur["hard_negative"],
        "required_hard_negative_count": REQUIRED_HARD_NEGATIVE,
        "current_reviewer_count": cur_reviewers,   # global engaged(contact evidence)·per-pair coverage 아님.
        "reviewer_count_required": REVIEWER_DUPLICATION_REQUIRED,
        "reviewer_duplication_required": REVIEWER_DUPLICATION_REQUIRED,
        "reviewer_agreement_required": True,
        "conflict_adjudication_required": True,
        "label_collection_gap": label_collection_gap,
        "korean_gap": korean_gap,
        "positive_gap": positive_gap,
        "negative_gap": negative_gap,
        "hard_negative_gap": hard_negative_gap,
        "reviewer_gap": reviewer_gap,
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        "next_manual_actions": list(next_manual_actions),
        "flags": dict(flags),
    }

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "input_directory": gate["input_directory"],
        # §A actual input 재확인(단일 출처 게이트 passthrough).
        "actual_input_rechecked": True,
        "actual_contact_evidence_found": gate["actual_contact_evidence_found"],
        "actual_returned_labels_found": gate["actual_returned_labels_found"],
        "actual_input_status": gate["actual_input_status"],
        "external_input_required": gate["external_input_required"],
        # §B R1 status + gold floor(current/required·exact passthrough + canonical/파생 floor).
        "r1_status": r1_status,
        "current_production_gold_count": prod,
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_korean_gold_count": cur["korean"],
        "required_korean_gold_count": REQUIRED_KOREAN_GOLD,
        "current_positive_gold_count": cur["positive"],
        "current_negative_gold_count": cur["negative"],
        "required_positive_gold_count": REQUIRED_POSITIVE_GOLD,
        "required_negative_gold_count": REQUIRED_NEGATIVE_GOLD,
        "current_hard_negative_count": cur["hard_negative"],
        "required_hard_negative_count": REQUIRED_HARD_NEGATIVE,
        "current_reviewer_count": cur_reviewers,
        "reviewer_count_required": REVIEWER_DUPLICATION_REQUIRED,
        "reviewer_duplication_required": REVIEWER_DUPLICATION_REQUIRED,
        "reviewer_agreement_required": True,
        "conflict_adjudication_required": True,
        # §C gap 산술(required − current).
        "label_collection_gap": label_collection_gap,
        "korean_gap": korean_gap,
        "positive_gap": positive_gap,
        "negative_gap": negative_gap,
        "hard_negative_gap": hard_negative_gap,
        "reviewer_gap": reviewer_gap,
        # §D operator-facing 산출물 readiness(표면화 — 각자 자체 테스트로 검증).
        "next_manual_actions": list(next_manual_actions),
        "contact_evidence_template_ready": CONTACT_EVIDENCE_TEMPLATE_READY,
        "returned_label_template_ready": RETURNED_LABEL_TEMPLATE_READY,
        "returned_label_placement_guide_ready": RETURNED_LABEL_PLACEMENT_GUIDE_READY,
        "internal_ops_r1_gap_visible": INTERNAL_OPS_R1_GAP_VISIBLE,
        "source_storage_strategy_updated": SOURCE_STORAGE_STRATEGY_UPDATED,
        # gold/calibration passthrough(exact).
        "production_gold_count": prod,
        "synthetic_gold_count": gate["synthetic_gold_count"],
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        # public/PII/merge 경계(정직·constant + 게이트 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": gate["score_exposed"],
        "rationale_exposed": gate["rationale_exposed"],
        "predicted_status_exposed": gate["predicted_status_exposed"],
        "raw_pii_exposed": gate["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        # merge/LLM/embedding/DB/IU 경계(상속).
        "no_public_intelligence_unit": gate["no_public_intelligence_unit"],
        "merge_allowed": gate["merge_allowed"],
        "db_write": gate["db_write"],
        "llm_invoked": gate["llm_invoked"],
        "embedding_invoked": gate["embedding_invoked"],
        # API/UI 화이트리스트 contract.
        "r1_contract": r1_contract,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_gold_acquisition_plan_output")
    return result


# ── CLI(settings 무관·network 0·DB 0·전송 0·secret read 0) ──────────────────────────────────────────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="R1 production gold acquisition operating plan (ADR#74·병합 0·LLM 0·embedding 0·DB 0·전송 0).")
    parser.add_argument("--batch-id", default="reviewer_pilot_exec_001", help="actual input 재확인 batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_r1_gold_acquisition_plan(directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: rechecked={out['actual_input_rechecked']} status={out['actual_input_status']} "
          f"external_input_required={out['external_input_required']}")
    print(f"- r1_status: {out['r1_status']}")
    print(f"- gold: production={out['current_production_gold_count']}/{out['required_production_gold_count']} "
          f"korean={out['current_korean_gold_count']}/{out['required_korean_gold_count']} "
          f"positive={out['current_positive_gold_count']}/{out['required_positive_gold_count']} "
          f"negative={out['current_negative_gold_count']}/{out['required_negative_gold_count']} "
          f"hard_neg={out['current_hard_negative_count']}/{out['required_hard_negative_count']}")
    print(f"- gaps: label={out['label_collection_gap']} korean={out['korean_gap']} positive={out['positive_gap']} "
          f"negative={out['negative_gap']} hard_neg={out['hard_negative_gap']} reviewer={out['reviewer_gap']}")
    print(f"- reviewer: required={out['reviewer_count_required']} duplication={out['reviewer_duplication_required']} "
          f"agreement_required={out['reviewer_agreement_required']} adjudication_required={out['conflict_adjudication_required']}")
    print(f"- readiness: contact_tpl={out['contact_evidence_template_ready']} label_tpl={out['returned_label_template_ready']} "
          f"placement={out['returned_label_placement_guide_ready']} r1_gap_visible={out['internal_ops_r1_gap_visible']} "
          f"storage_strategy={out['source_storage_strategy_updated']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} public_truth_exposed={out['public_truth_exposed']} "
          f"db_write={out['db_write']} llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    if out["next_manual_actions"]:
        print(f"- next_manual: {out['next_manual_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
