"""ADR#91 §12 — R1 label return operational bridge (returned labels 도착 시 다음 실행을 명확화·gold 0 유지·재구현 0).

문제(ADR#90 Q11): freeze 후 reviewer contact/dropbox/readiness 는 준비됐고 **validation_command** 는 존재하지만,
"실 returned human label 이 dropbox 에 도착하면 *어떤 명령*으로 import 해서 R1 production gold 로 승격하는가" — 그
**intake_command + 승격 상태** 가 어디에도 노출되지 않았다(grep intake_command = 0건). operator 는 라벨을 받아도 다음
한 걸음을 모른다.

이 모듈은 그 간극을 잇는 **thin composer** 다(재구현 0):
  - dropbox(경로/expected pattern/실 returned count/validation_command): `returned_label_dropbox_readiness` 재사용.
  - gold 상태(r1_status/production_gold_count/gap/block_reasons): `r1_gold_acquisition_plan` 재사용(actual input 재확인).
  - **새로 더하는 유일한 표면**: `intake_command`(라벨 import+승격 시도 명령) · `gold_promotion_status`(파생) ·
    `gold_promotion_blockers`(block_reasons 명명 투영) · gold-promotion 특화 next_action.

절대 불변(§12): actual_returned_label_count 는 실 파일만 · synthetic fixture 미집계 · single reviewer/unsure 는 gold 아님 ·
agreement gate 필수 · production_gold_count 는 returned human labels + 2-reviewer 합의 전까지 0 · merge 0 · 전송 0 ·
score/rationale/PII 미노출(`_assert_pii_safe` 재귀 가드). read-API 안전: live runner 를 import 하지 않는다(frontier-safe).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Callable, Optional

from backend.app.tools.r1_gold_acquisition_plan import (
    R1_PARTIALLY_SATISFIED,
    R1_SATISFIED,
    run_r1_gold_acquisition_plan,
)
from backend.app.tools.returned_label_dropbox_readiness import (
    build_returned_label_dropbox_readiness,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "r1_label_return_operational_bridge"
# returned_label_dropbox_readiness._DEFAULT_DROPBOX_BATCH_ID / operator_confirmed_live_runner.DEFAULT_BATCH_ID 와 동일
# 문자열(live runner 를 import 하지 않으려 로컬 미러 — read-API frontier safety).
DEFAULT_BATCH_ID = "operator_regulatory_live"
_VENV_PY = r".\.venv\Scripts\python.exe"

# r1_label_return_status(returned-label 파이프라인 상위 상태).
RETURN_AWAITING = "awaiting_returned_labels"
RETURN_COLLECTING = "labels_present_collecting"
RETURN_ELIGIBLE = "gold_floor_satisfied_gate_controlled"

# gold_promotion_status(승격 세부 상태·r1_status + count 파생).
GP_AWAITING_LABELS = "awaiting_returned_labels"
GP_LABELS_NO_GOLD = "labels_present_no_decisive_gold"
GP_ACCUMULATING = "gold_accumulating_below_floor"
GP_SUB_FLOOR_UNMET = "total_floor_met_sub_floor_unmet"
GP_FLOOR_SATISFIED = "gold_floor_satisfied_merge_gate_review"


def intake_command(*, batch_id: str, intake_dir: str) -> str:
    """returned label 을 import 하고 production gold 승격을 *시도* 하는 명령(actual input 재확인·gold 산출)."""
    return (f"{_VENV_PY} -m backend.app.tools.r1_gold_acquisition_plan "
            f"--batch-id {batch_id} --input-dir {intake_dir} --json")


def _promotion_status(*, actual_count: int, production_gold_count: int, r1_status: Optional[str]) -> str:
    """returned count + production gold + r1_status → gold_promotion_status(파생·gold 날조 0)."""
    if actual_count <= 0:
        return GP_AWAITING_LABELS
    if production_gold_count <= 0:
        return GP_LABELS_NO_GOLD
    if r1_status == R1_SATISFIED:
        return GP_FLOOR_SATISFIED
    if r1_status == R1_PARTIALLY_SATISFIED:
        return GP_SUB_FLOOR_UNMET
    return GP_ACCUMULATING


def _return_status(*, actual_count: int, production_gold_count: int, r1_status: Optional[str]) -> str:
    if actual_count <= 0:
        return RETURN_AWAITING
    if production_gold_count > 0 and r1_status == R1_SATISFIED:
        return RETURN_ELIGIBLE
    return RETURN_COLLECTING


def _next_action(*, gold_promotion_status: str, intake_dir: str, label_collection_gap: int) -> str:
    if gold_promotion_status == GP_AWAITING_LABELS:
        return (f"no returned labels yet — distribute the handoff bundle manually, place returned JSONL in "
                f"{intake_dir} (gitignored), then run the intake command")
    if gold_promotion_status == GP_LABELS_NO_GOLD:
        return ("labels present but no decisive 2-reviewer agreement gold — adjudicate conflicts by human-only "
                "review (no auto-majority); single-reviewer/unsure labels never count")
    if gold_promotion_status == GP_FLOOR_SATISFIED:
        return ("production gold floor satisfied — route to MERGE_GATE calibration review (still gate-controlled; "
                "no auto-merge)")
    if gold_promotion_status == GP_SUB_FLOOR_UNMET:
        return "total gold floor met but a sub-floor (korean/positive/negative/hard-negative) is unmet — collect targeted labels"
    return f"gold accumulating below the floor — collect more decisive labels (label gap {label_collection_gap})"


def build_r1_label_return_operational_bridge(
    *, batch_id: str = DEFAULT_BATCH_ID, dropbox_readiness: Optional[dict] = None,
    gold_plan: Optional[dict] = None, scan_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """returned label dropbox + R1 gold plan → label-return operational bridge(intake_command + 승격 상태).

    dropbox_readiness/gold_plan 미주입 시 빌드한다(gitignored outputs/ 스캔·network 0). frontier 에서는 이미 계산된
    dropbox/gold 를 주입해 중복 스캔 0. dropbox 의 실 returned count + gold plan 의 production_gold_count 를 그대로
    쓰며(날조 0), synthetic/single/unsure 는 dropbox 안전 플래그로 표면화한다. live runner 를 import 하지 않는다."""
    dropbox = dropbox_readiness or build_returned_label_dropbox_readiness(batch_id=batch_id, scan_fn=scan_fn)
    intake_dir = str(dropbox.get("dropbox_path") or f"outputs/reviewer_batch/{batch_id}")
    gold = gold_plan or run_r1_gold_acquisition_plan(batch_id=batch_id, directory=intake_dir)

    actual_count = int(dropbox.get("actual_returned_label_count") or 0)
    production_gold_count = int(gold.get("production_gold_count") or 0)
    r1_status = gold.get("r1_status")
    label_collection_gap = int(gold.get("label_collection_gap") or 0)

    gp_status = _promotion_status(
        actual_count=actual_count, production_gold_count=production_gold_count, r1_status=r1_status)
    return_status = _return_status(
        actual_count=actual_count, production_gold_count=production_gold_count, r1_status=r1_status)

    # gold_promotion_blockers — 명명 투영(특화 사유 + gold plan block_reasons).
    blockers: list[str] = []
    if actual_count <= 0:
        blockers.append("no_returned_labels")
    elif production_gold_count <= 0:
        blockers.append("no_decisive_two_reviewer_gold")
    if label_collection_gap > 0:
        blockers.append("below_production_gold_floor")
    blockers.extend(gold.get("block_reasons") or [])
    blockers = list(dict.fromkeys(blockers))   # 순서 보존 dedupe.

    nxt = _next_action(
        gold_promotion_status=gp_status, intake_dir=intake_dir, label_collection_gap=label_collection_gap)

    out = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "r1_label_return_status": return_status,
        # dropbox 재사용(경로/패턴/실 count/validation).
        "dropbox_path": dropbox.get("dropbox_path"),
        "dropbox_gitignored": bool(dropbox.get("dropbox_gitignored")),
        "expected_file_pattern": dropbox.get("returned_label_glob") or "*.jsonl",
        "expected_returned_files_example": list(dropbox.get("expected_returned_files_example") or []),
        "actual_returned_label_count": actual_count,
        "validation_command": dropbox.get("validation_command"),
        # 새 표면 — intake + 승격.
        "intake_command": intake_command(batch_id=batch_id, intake_dir=intake_dir),
        "gold_promotion_status": gp_status,
        "gold_promotion_blockers": blockers,
        # gold/agreement 경계(dropbox 안전 플래그 passthrough·날조 0).
        "production_gold_count": production_gold_count,
        "r1_status": r1_status,
        "label_collection_gap": label_collection_gap,
        "synthetic_fixture_counted_as_gold": bool(dropbox.get("synthetic_fixture_counted_as_gold")),
        "single_reviewer_label_is_gold": bool(dropbox.get("single_reviewer_label_is_gold")),
        "unsure_label_is_gold": bool(dropbox.get("unsure_label_is_gold")),
        "agreement_required_for_gold": bool(dropbox.get("agreement_required_for_gold")),
        # ── 불변 경계(정직·constant) ──
        "actual_sending_performed": False,
        "merge_allowed": False,
        "same_event_asserted": False,
        "r2_r7_no_go": True,
        "next_action": nxt,
    }
    _assert_pii_safe(out, _path="r1_label_return_operational_bridge_output")
    return out


def sanitized_r1_label_return(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(명령 문자열 제외·status/count 만)."""
    return {
        "r1_label_return_status": out["r1_label_return_status"],
        "gold_promotion_status": out["gold_promotion_status"],
        "actual_returned_label_count": out["actual_returned_label_count"],
        "production_gold_count": out["production_gold_count"],
        "r1_label_return_next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#91 R1 label return operational bridge (returned labels → intake_command + gold 승격 상태; "
                     "synthetic/single/unsure 는 gold 아님·agreement 필수·production gold 0 유지·merge 0·전송 0)."))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="returned-label dropbox batch id.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령 문자열 포함).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)
    out = build_r1_label_return_operational_bridge(batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} status={out['r1_label_return_status']}")
    print(f"- dropbox: path={out['dropbox_path']} pattern={out['expected_file_pattern']} "
          f"returned_labels={out['actual_returned_label_count']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- intake_command: {out['intake_command']}")
    print(f"- gold_promotion: status={out['gold_promotion_status']} production_gold={out['production_gold_count']} "
          f"blockers={out['gold_promotion_blockers']}")
    print(f"- gold guards: synthetic_gold={out['synthetic_fixture_counted_as_gold']} "
          f"single_gold={out['single_reviewer_label_is_gold']} unsure_gold={out['unsure_label_is_gold']} "
          f"agreement_required={out['agreement_required_for_gold']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
