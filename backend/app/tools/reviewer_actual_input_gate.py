"""ADR#72 — actual reviewer input gate + internal ops dashboard bridge (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#71 이 만든 것: `reviewer_pilot_execution` — operator 가 *입력으로 건넨* contact evidence/returned label 을
PII-safe 하게 받아 8-state execution_status·SLA/checklist·ops UI execution contract 를 산출하는 **순수**(인자 기반)
ledger. 그러나 그 입력이 **실제로 디스크에 존재하는지**(operator 가 gitignored 경로에 실 contact evidence/returned
label 파일을 떨궜는지)를 확인하고, 있으면 end-to-end 로 태우고 없으면 `external_input_required` 로 정직하게 멈추는
**입력 게이트**가 없었다. "ledger 가 있으니 pilot 이 실행됐다"로 둔갑할 자리가 남는다(R-ReviewerPilotExecution·
R-ActualInputStall).

이 모듈은 **재구현이 아니라 입력 게이트 + 산출 wrapper** 다. 무거운 일은 전부 단일 출처가 한다:
  - contact evidence 검증·8-state execution_status·SLA/checklist·ops UI execution contract·gold/calibration
    exact passthrough: `reviewer_pilot_execution.run_reviewer_pilot_execution`(단일 호출·decorate). 그 자신이
    handoff→followup→intake 를 1회 태우므로 본 게이트도 그 체인을 **재호출하지 않는다**(발산 0).
  - returned label 파일 스캔/검증: `intake_directory` 를 그대로 넘기면 기존 intake 체인이 처리(재구현 0).
  - PII 재귀 가드: `reviewer_pilot_handoff._assert_pii_safe`(재사용).

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **actual input 탐지(§A·Lane A)**: gitignored `outputs/reviewer_batch/<batch>/intake/` 에서 operator 가 떨군 실
    contact evidence(JSON)·returned label(JSONL) 파일을 **스캔만** 하고(생성 0·날조 0), 있으면 ledger 로 dispatch,
    없으면 `no_actual_input`/`external_input_required` 로 정직 보고. demo/fixture 를 production 입력으로 둔갑 금지.
  - **actual_input_status(5-state)**: no_actual_input/contact_evidence_only/returned_labels_present/
    invalid_returned_labels/labels_imported. execution_status(8-state)와 직교(입력 파일 축 vs 운영 실행 축).
  - **internal ops bridge readiness(§B·Lane B/C)**: backend read-only API·frontend seed 가 읽을 sanitized
    `InternalOpsPilotExecutionStatus` 가 준비됐는지·public truth 와 분리됐는지 플래그로 표면화.

절대 불변(상속·상용 안전 계약):
  - **입력 날조 0**: contact evidence/returned label 파일은 *스캔*만 — 코드가 생성하지 않는다(operator 가 떨군 것만).
    demo/synthetic/fixture 를 production label 로 둔갑 0(synthetic 경로는 CLI 에서 label_source=synthetic 명시).
  - **production_gold_count 0 정직·exact passthrough**: gold/calibration/merge_gate 는 전부 ledger(→handoff→intake)
    결과를 그대로 전달. 게이트만으로 증가 0. 실 production human label 파일이 없으면 0.
  - **no merge / no public IU / no DB / no LLM / no embedding / no 전송**: 전 경로 상속.
  - **reviewer raw PII 0 / secret 0 / score·rationale·predicted_status 숨김**: ledger 파생 + 전체 재귀 가드.
  - **internal ops ≠ public truth**: ops contract 는 workflow state 만(same_event 확정·verified gold 렌더 불가·flags 강제).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from backend.app.tools.production_label_intake import _display_path
from backend.app.tools.reviewer_label_operations import (
    LABEL_SOURCE_PRODUCTION,
    LABEL_SOURCES,
)
from backend.app.tools.reviewer_pilot_execution import run_reviewer_pilot_execution
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "actual_input_gate_and_internal_ops_bridge"

# operator 가 실 입력을 떨구는 gitignored 루트(.gitignore 가 outputs/reviewer_batch/ 추적 제외). 코드가 만들지 않는다.
DEFAULT_REVIEWER_BATCH_ROOT = "outputs/reviewer_batch"
# 스캔 대상 파일 패턴(생성 아님·탐지만). contact evidence=JSON 배열, returned label=reviewer 별 JSONL.
CONTACT_EVIDENCE_GLOB = "contact_evidence*.json"
RETURNED_LABEL_GLOB = "*.jsonl"
# 출력 basename 마스킹(operator 가 파일명에 raw PII[이메일 등]를 넣어도 노출 0·gitignored·API 미노출이나 심층 방어).
_SAFE_NAME_RE = re.compile(r"[A-Za-z0-9_.\-]+")


def _safe_basename(name: str) -> str:
    return name if _SAFE_NAME_RE.fullmatch(name) else "<redacted_filename>"

# ── §A actual_input_status(5-state·입력 파일 축) ────────────────────────────────────────────────────────
# no_actual_input: 실 입력 파일 0. contact_evidence_only: contact evidence 만(returned label 0).
# returned_labels_present: label 파일 회수·검증 통과 row>0(gold 미달). invalid_returned_labels: label 파일은
# 있으나 검증 통과 row 0. labels_imported: returned label 이 production gold 로 적재됨(production_gold_count>0).
INPUT_NO_ACTUAL = "no_actual_input"
INPUT_CONTACT_ONLY = "contact_evidence_only"
INPUT_RETURNED_PRESENT = "returned_labels_present"
INPUT_INVALID_RETURNED = "invalid_returned_labels"
INPUT_LABELS_IMPORTED = "labels_imported"
ACTUAL_INPUT_STATES = frozenset({
    INPUT_NO_ACTUAL, INPUT_CONTACT_ONLY, INPUT_RETURNED_PRESENT,
    INPUT_INVALID_RETURNED, INPUT_LABELS_IMPORTED,
})

# ADR#72 가 ship 하는 internal ops bridge surface 선언(각자 자체 모듈/테스트로 검증). 게이트는 이를 표면화만 한다.
#   - backend read-only API: backend/app/api/internal_ops.py(GET /api/internal/ops/pilot-execution·admin-token+flag).
#   - frontend seed: frontend/src/app/internal/ops-pilot/page.tsx(URL /internal/ops-pilot·server-env gate·nav 미노출·read-only).
BACKEND_INTERNAL_OPS_API_READY = True
FRONTEND_INTERNAL_OPS_SEED_READY = True


# ── §A: actual input 탐지(스캔만·생성 0·날조 0) ─────────────────────────────────────────────────────────
def scan_actual_reviewer_input(directory: Any) -> dict:
    """gitignored 입력 디렉터리에서 operator 가 떨군 실 contact evidence/returned label 파일을 **스캔만** 한다.
    디렉터리가 없으면(정상 초기 상태) 빈 결과 — 파일을 만들지 않는다(날조 0). basename 만 반환(raw 경로 PII 0)."""
    p = Path(directory)
    if not p.exists() or not p.is_dir():
        return {
            "directory": str(p), "directory_exists": False,
            "contact_evidence_files": [], "returned_label_files": [],
        }
    contact_files = sorted(f.name for f in p.glob(CONTACT_EVIDENCE_GLOB) if f.is_file())
    label_files = sorted(f.name for f in p.glob(RETURNED_LABEL_GLOB) if f.is_file())
    return {
        "directory": str(p), "directory_exists": True,
        "contact_evidence_files": contact_files, "returned_label_files": label_files,
    }


def _load_contact_evidence(directory: Any, contact_files: list[str]) -> Optional[list[dict]]:
    """contact evidence JSON 파일(들)을 읽어 evidence record 리스트로 병합. 없으면 None(접촉 0). 각 파일은 JSON
    배열이어야 하며(아니면 fail-loud) — record 자체의 PII/allowlist 검증은 ledger 의 validate_contact_evidence 가
    수행(둔갑 0). 코드가 evidence 를 생성하지 않는다(operator 가 떨군 파일만 읽는다)."""
    if not contact_files:
        return None
    p = Path(directory)
    merged: list[dict] = []
    for name in contact_files:
        raw = (p / name).read_text(encoding="utf-8")
        parsed = json.loads(raw)   # 깨진 JSON → fail-loud(조용한 무시 금지).
        if not isinstance(parsed, list):
            raise ValueError(f"contact evidence file {name!r} must be a JSON array of evidence records.")
        merged.extend(parsed)
    return merged


def _actual_input_status(
    *, contact_found: bool, labels_found: bool, returned_label_count: int, production_gold_count: int,
) -> str:
    """입력 파일 축 5-state. 파일이 있어도 검증 통과 row 가 0 이면 invalid_returned_labels(둔갑 금지).
    production gold 로 적재돼야 labels_imported(그 전까지는 returned_labels_present)."""
    if labels_found:
        if returned_label_count <= 0:
            return INPUT_INVALID_RETURNED
        return INPUT_LABELS_IMPORTED if production_gold_count > 0 else INPUT_RETURNED_PRESENT
    if contact_found:
        return INPUT_CONTACT_ONLY
    return INPUT_NO_ACTUAL


# ── §4: actual input gate + internal ops bridge entrypoint ─────────────────────────────────────────────
def run_actual_input_gate(
    *, directory: Optional[Any] = None, queue: Optional[dict] = None, discovery: Optional[dict] = None,
    batch_id: str = "reviewer_pilot_exec_001", packet_id: str = "reviewer_pilot_exec_pkt",
    label_source: str = LABEL_SOURCE_PRODUCTION, reviewers: Optional[list[str]] = None,
    top_k_sourced: bool = True, include_synthetic_hard_negatives: bool = False,
    due_hint: Optional[str] = None, calibration_baseline: Optional[dict] = None,
    as_of: Optional[str] = None,
) -> dict:
    """actual reviewer input gate + internal ops dashboard bridge(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    1) gitignored 입력 디렉터리를 스캔(생성 0)해 실 contact evidence/returned label 파일 유무를 확인하고,
    2) 있으면 `run_reviewer_pilot_execution`(단일 출처)로 end-to-end dispatch, 없으면 external_input_required 정직 산출,
    3) ledger 결과를 internal ops bridge 산출(sanitized ops contract·readiness·no-go flags)로 표면화한다.
    어떤 경로도 입력을 날조하거나 merge/LLM/embedding/DB/전송을 건드리지 않는다."""
    if label_source not in LABEL_SOURCES:
        raise ValueError(f"invalid label_source {label_source!r} (allowed: {sorted(LABEL_SOURCES)})")
    # canonical 입력 디렉터리=`outputs/reviewer_batch/<batch>/intake`(reviewer_batch_launch/handoff bundle 와 동일
    # 규약). 게이트가 스캔하는 경로를 ledger 에 **그대로** 넘겨 scan==intake==bundle 을 단일 경로로 수렴시킨다 —
    # `None`→`/intake` fallback 발산 차단(HIGH: 부모만 스캔하면 ledger 가 다른 `/intake` 를 적재해 no_actual_input +
    # returned_label_count>0 자기모순). 빈/부재 dir 은 ledger 가 빈 결과 반환(awaiting·노이즈 0).
    directory = directory if directory is not None else str(Path(DEFAULT_REVIEWER_BATCH_ROOT) / batch_id / "intake")
    scan = scan_actual_reviewer_input(directory)
    contact_evidence = _load_contact_evidence(directory, scan["contact_evidence_files"])
    labels_found = bool(scan["returned_label_files"])
    intake_directory = directory   # 항상 스캔 경로 전달(발산 0).

    # 단일 출처 ledger 로 dispatch(입력 날조 0 — 스캔된 실 파일/evidence 만 전달).
    execution = run_reviewer_pilot_execution(
        queue=queue, discovery=discovery, batch_id=batch_id, packet_id=packet_id,
        intake_directory=intake_directory, label_source=label_source, adjudications=None,
        reviewers=reviewers, top_k_sourced=top_k_sourced,
        include_synthetic_hard_negatives=include_synthetic_hard_negatives, due_hint=due_hint,
        calibration_baseline=calibration_baseline, contact_evidence=contact_evidence, as_of=as_of)

    contact_found = bool(contact_evidence)
    returned_label_count = execution["returned_label_count"]
    production_gold_count = execution["production_gold_count"]
    actual_input_status = _actual_input_status(
        contact_found=contact_found, labels_found=labels_found,
        returned_label_count=returned_label_count, production_gold_count=production_gold_count)
    # 외부 입력이 더 필요한가 = MERGE_GATE 미준비(gold 1개라도 calibration floor 미충족이면 여전히 필요·정직).
    # `gold==0` 만 보면 "gold 1개=수집 종료" 로 오인 → merge_gate_ready 기준으로 정의(production_gold_count 0 이면
    # merge_gate_ready 도 False 라 무입력 케이스는 그대로 True).
    external_input_required = not execution["merge_gate_ready"]

    ops_ui_contract = execution["ops_ui_contract"]
    gate_block_reason = (
        "external_reviewer_input_required" if external_input_required else "awaiting_merge_gate_review")
    gate_next_action = (
        f"operator 가 실 reviewer 에게 handoff bundle 을 배포(수동)하고, contact evidence(JSON)·returned label "
        f"(JSONL)을 gitignored {DEFAULT_REVIEWER_BATCH_ROOT}/{batch_id}/intake/ 에 떨구면 게이트가 자동으로 end-to-end "
        f"intake/monitor 를 태운다(현재 actual_input_status={actual_input_status})."
        if external_input_required else "MERGE_GATE review 준비(adversarial 승인 필요·자동 병합 0)")

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        "packet_id": packet_id,
        # 출력 표면은 _display_path 로 절대경로 사용자명 미노출(상대경로는 그대로·repo 밖 절대경로는 basename).
        "input_directory": _display_path(scan["directory"]),
        "input_directory_exists": scan["directory_exists"],
        # §A actual input 탐지(스캔만·basename 마스킹·생성 0).
        "actual_contact_evidence_found": contact_found,
        "actual_returned_labels_found": labels_found,
        "contact_evidence_files": [_safe_basename(n) for n in scan["contact_evidence_files"]],
        "returned_label_files": [_safe_basename(n) for n in scan["returned_label_files"]],
        "actual_input_status": actual_input_status,
        "external_input_required": external_input_required,
        # ledger passthrough(운영 실행 축·exact).
        "execution_status": execution["execution_status"],
        "pilot_status": execution["pilot_status"],
        "pilot_executed": execution["pilot_executed"],
        "contact_evidence_present": execution["contact_evidence_present"],
        "real_reviewers_contacted": execution["real_reviewers_contacted"],
        "expected_label_count": execution["expected_label_count"],
        "returned_label_count": returned_label_count,
        "missing_label_count": execution["missing_label_count"],
        "invalid_label_count": execution["invalid_label_count"],
        "conflict_pair_count": execution["conflict_pair_count"],
        "calibration_gap": execution["calibration_gap"],
        "production_gold_count": production_gold_count,
        "synthetic_gold_count": execution["synthetic_gold_count"],
        "calibration_ready": execution["calibration_ready"],
        "merge_gate_ready": execution["merge_gate_ready"],
        # §B internal ops bridge readiness(sanitized contract·public truth 분리).
        "internal_ops_contract_ready": ops_ui_contract["contract"] == "InternalOpsPilotExecutionStatus",
        "backend_internal_ops_api_ready": BACKEND_INTERNAL_OPS_API_READY,
        "frontend_internal_ops_seed_ready": FRONTEND_INTERNAL_OPS_SEED_READY,
        "internal_ops_contract": ops_ui_contract,
        "ops_ui_flags": ops_ui_contract["flags"],
        # public/PII/merge 경계(정직·constant + ledger 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "raw_pii_exposed": execution["raw_pii_exposed"],
        "score_exposed": not execution["score_hidden_from_labeler"],
        "rationale_exposed": not execution["rationale_hidden_from_labeler"],
        "predicted_status_exposed": not execution["predicted_status_hidden"],
        "reviewer_ids_pseudonymous": execution["reviewer_ids_pseudonymous"],
        "actual_sending_performed": execution["actual_sending_performed"],
        "no_public_intelligence_unit": execution["no_public_intelligence_unit"],
        "merge_allowed": execution["merge_allowed"],
        "no_merge_without_gold": execution["no_merge_without_gold"],
        "db_write": execution["db_write"],
        "llm_invoked": execution["llm_invoked"],
        "embedding_invoked": execution["embedding_invoked"],
        # block_reasons / next_actions(gate-level + ledger passthrough·dedup).
        "block_reasons": list(dict.fromkeys([gate_block_reason] + list(execution["block_reasons"]))),
        "next_actions": [gate_next_action] + list(execution["next_actions"]),
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="actual_input_gate_output")
    return result


# ── CLI(기본 실 입력 디렉터리 스캔·network 0·DB 0·전송 0; synthetic 데모 opt-in·production 둔갑 0) ────────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="actual reviewer input gate + internal ops bridge (ADR#72·병합 0·LLM 0·DB 0·전송 0).")
    parser.add_argument("--input-dir", metavar="DIR",
                        help=f"실 입력 디렉터리(미지정 시 {DEFAULT_REVIEWER_BATCH_ROOT}/<batch-id>). 코드가 생성하지 않음.")
    parser.add_argument("--batch-id", default="reviewer_pilot_exec_cli", help="batch id.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO). 미지정 시 overdue 0.")
    parser.add_argument("--use-fixture-queue", action="store_true",
                        help="captured overlap fixture 로 구조 데모(실 후보 아님·no_public_truth). 미지정 시 not_started.")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    queue = None
    if ns.use_fixture_queue:
        from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
        from backend.app.tools.source_overlap_discovery import (
            build_captured_overlap_fixture,
            discover_overlap,
        )
        disc = discover_overlap(build_captured_overlap_fixture())
        queue = build_near_match_reviewer_queue(disc, packet_id="actual_input_gate_cli")

    out = run_actual_input_gate(
        directory=ns.input_dir, queue=queue, batch_id=ns.batch_id, packet_id="actual_input_gate_cli",
        label_source=LABEL_SOURCE_PRODUCTION, as_of=ns.as_of, top_k_sourced=False)

    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']} dir={out['input_directory']}")
    print(f"- actual_input: status={out['actual_input_status']} contact_found={out['actual_contact_evidence_found']} "
          f"labels_found={out['actual_returned_labels_found']} external_input_required={out['external_input_required']}")
    print(f"- execution: status={out['execution_status']} pilot_status={out['pilot_status']} "
          f"pilot_executed={out['pilot_executed']} contacted={out['real_reviewers_contacted']}")
    print(f"- returns: returned={out['returned_label_count']}/{out['expected_label_count']} "
          f"missing={out['missing_label_count']} invalid={out['invalid_label_count']} conflict={out['conflict_pair_count']}")
    print(f"- gold: production={out['production_gold_count']} synthetic={out['synthetic_gold_count']} "
          f"calibration_ready={out['calibration_ready']} merge_gate_ready={out['merge_gate_ready']}")
    print(f"- bridge: contract_ready={out['internal_ops_contract_ready']} api_ready={out['backend_internal_ops_api_ready']} "
          f"frontend_seed_ready={out['frontend_internal_ops_seed_ready']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} public_truth_exposed={out['public_truth_exposed']} "
          f"same_event_truth_exposed={out['same_event_truth_exposed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- ops_ui: contract={out['internal_ops_contract']['contract']} flags={out['ops_ui_flags']}")
    if out["next_actions"]:
        print(f"- next: {out['next_actions'][0]}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
