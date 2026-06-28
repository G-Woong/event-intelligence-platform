"""ADR#84 — reviewer handoff bridge: production-candidate freeze → contact-PRE handoff package (no sending).

ADR#76 freeze(`run_r1_production_candidate_acquisition`)가 live-derived publishable×publishable batch 를
동결했을 때만, reviewer **contact 직전** 의 handoff package(label schema·expected label files·validation
command·placement guide·operator checklist)를 조립한다. **실제 email/slack/webhook 전송은 하지 않는다**
(`actual_sending_performed=False` 불변·operator 가 수동 배포). freeze 가 없으면 `reviewer_handoff_ready=False` +
candidate blocker 를 정직하게 표면화한다(다음 행동=contact 전 blocker 해소).

이 모듈은 freeze 를 **재계산하지 않는다** — 이미 동결된 산출물(`expected_label_files`·`validation_command`·
`operator_launch_checklist`·`production_batch_signature`)을 contact-PRE 형태로 **재패키징**할 뿐이다(단일 출처 보존).

절대 불변(상속·상용 안전 계약):
  - **no sending**: 어떤 채널로도 자동 발송 0(`actual_sending_performed=False`). reviewer 모집/접촉은 operator 수동.
  - **freeze ≠ truth ≠ gold**: handoff package 는 pre-contact worklist 이지 same_event 확정·production gold 가 아니다
    (`freeze_is_reviewer_worklist_only=True`·production_gold_count 불변).
  - **PII/secret/score/rationale/predicted_status/same_event/raw body 0**: 출력은 `_assert_pii_safe` 통과 —
    단 이 가드는 **정확명 forbidden-key 를 재귀 차단**(값/substring 미검사·whitelisted 스키마 전제의 defense-in-depth
    backstop·구조적 불가능성 아님). reviewer roster raw name/email/phone·local mapping 미포함(pseudonym 만).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.reviewer_batch_launch import build_reviewer_instruction
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "reviewer_handoff_bridge"

# freeze 없음 → contact 전 blocker 해소 필요(다음 행동·정직).
HANDOFF_BLOCKED_NO_FREEZE = "no_production_candidate_freeze"
_NEXT_ACTION_NO_FREEZE = (
    "resolve the candidate blocker before reviewer contact — no live-derived publishable production-candidate "
    "batch was frozen, so there is nothing to hand off yet (acquire in-window cross-source publishable pairs first)")
_NEXT_ACTION_READY = (
    "operator: manually distribute the frozen production-candidate worklist to >=2 pseudonymous reviewers per "
    "pair and collect returned label JSONL into the intake directory (no system sending); production gold stays "
    "0 until those human labels are imported and validated")
_PLACEMENT_GUIDE = (
    "place each reviewer's returned JSONL at the expected_label_files path under the intake_directory, then run "
    "the validation_command to check schema/pair coverage before importing (operator-managed; files stay "
    "gitignored under outputs/reviewer_batch/ and are never committed)")


def _label_vocabulary() -> list[str]:
    """reviewer 가 쓰는 label 어휘(단일 출처 = build_reviewer_instruction). 실패 시 빈 목록(fail-soft)."""
    try:
        instr = build_reviewer_instruction()
        vocab = instr.get("label_vocabulary") if isinstance(instr, dict) else None
        return list(vocab) if isinstance(vocab, (list, tuple)) else []
    except Exception:
        return []


def build_reviewer_handoff_bridge(
    pcand: dict, *, live_run_status: Optional[str] = None,
) -> dict:
    """production-candidate freeze 결과(pcand) → reviewer handoff bridge(contact-PRE·전송 0·PII/secret/score 0).

    pcand = `run_r1_production_candidate_acquisition` output(또는 그 형태의 dict). freeze 가 됐으면
    (production_candidate_batch_ready=True) contact-PRE package 를 조립; 아니면 handoff_ready=False +
    blocked_reason(live_run_status 우선 — 더 구체적 §5 live 상태). 어떤 경우도 전송·merge·gold 증가 0."""
    ready = bool(pcand.get("production_candidate_batch_ready"))
    batch_id = str(pcand.get("production_batch_id") or "")
    frozen_pair_count = int(pcand.get("production_frozen_pair_count") or 0)
    provenance = str(pcand.get("candidate_provenance") or "none")
    # ready 는 batch_id·frozen pair 가 실제로 있어야 성립(freeze 선언만으로 ready 둔갑 방지·fail-closed).
    ready = ready and bool(batch_id) and frozen_pair_count > 0

    handoff_package: Optional[dict] = None
    if ready:
        handoff_package = {
            "batch_id": batch_id,
            "batch_signature": str(pcand.get("production_batch_signature") or ""),
            "frozen_pair_count": frozen_pair_count,
            "candidate_provenance": provenance,
            "label_vocabulary": _label_vocabulary(),
            "expected_label_files": list(pcand.get("expected_label_files") or []),
            "validation_command": str(pcand.get("validation_command") or ""),
            "intake_directory": str(pcand.get("intake_directory") or ""),
            "placement_guide": _PLACEMENT_GUIDE,
            "operator_launch_checklist": pcand.get("operator_launch_checklist"),
            "reviewers_per_pair_minimum": 2,
        }
        blocked_reason = None
        next_action = _NEXT_ACTION_READY
    else:
        blocked_reason = live_run_status or str(
            pcand.get("production_candidate_status") or HANDOFF_BLOCKED_NO_FREEZE)
        next_action = _NEXT_ACTION_NO_FREEZE

    result = {
        "operation_name": OPERATION_NAME,
        "reviewer_handoff_ready": ready,
        "reviewer_instruction_ready": ready and bool(pcand.get("reviewer_instruction_ready")),
        "expected_label_files_ready": ready and bool(pcand.get("expected_label_files")),
        "validation_command_ready": ready and bool(pcand.get("validation_command")),
        "placement_guide_ready": ready,
        "actual_sending_performed": False,
        "handoff_package": handoff_package,
        "production_batch_id": batch_id if ready else "",
        "frozen_pair_count": frozen_pair_count,
        "candidate_provenance": provenance,
        "freeze_is_reviewer_worklist_only": True,
        "production_gold_count": int(pcand.get("production_gold_count") or 0),
        "current_r1_gap": int(pcand.get("current_r1_gap") or 0),
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        # 경계(정직·constant) — 어떤 경우도 truth/score/rationale/predicted/PII/body/merge 0.
        "same_event_truth_exposed": False,
        "score_exposed": False,
        "rationale_exposed": False,
        "predicted_status_exposed": False,
        "raw_pii_exposed": False,
        "raw_source_body_exposed": False,
        "merge_allowed": False,
    }
    # 전체 출력 재귀 가드 — 정확명 forbidden-key(score/rationale/predicted_status/raw PII/secret)를 어떤 depth 든
    # 차단(값/substring 미검사·whitelisted 스키마 전제의 backstop·드리프트 fail-loud).
    _assert_pii_safe(result, _path="reviewer_handoff_bridge_output")
    return result


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#84 reviewer handoff bridge (freeze → contact-PRE package; 전송 0·PII/secret/score 0). "
                     "freeze 결과 JSON 을 stdin 으로 받아 handoff readiness/package 를 산출."))
    parser.add_argument("--pcand-json", metavar="PATH", help="freeze(pcand) output JSON 파일 경로(미지정 시 stdin).")
    parser.add_argument("--live-run-status", default=None, help="(optional) §5 live run status(더 구체적 blocked_reason).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    raw = None
    if ns.pcand_json:
        with open(ns.pcand_json, encoding="utf-8") as f:
            raw = json.load(f)
    else:
        data = sys.stdin.read().strip()
        raw = json.loads(data) if data else {}
    out = build_reviewer_handoff_bridge(raw or {}, live_run_status=ns.live_run_status)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']}")
    print(f"- reviewer_handoff_ready={out['reviewer_handoff_ready']} "
          f"frozen_pair_count={out['frozen_pair_count']} provenance={out['candidate_provenance']}")
    print(f"- actual_sending_performed={out['actual_sending_performed']} "
          f"freeze_is_reviewer_worklist_only={out['freeze_is_reviewer_worklist_only']}")
    print(f"- production_gold_count={out['production_gold_count']} current_r1_gap={out['current_r1_gap']}")
    print(f"- blocked_reason={out['blocked_reason']}")
    print(f"- next_action={out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
