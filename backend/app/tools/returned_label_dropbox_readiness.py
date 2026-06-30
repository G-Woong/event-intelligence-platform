"""ADR#89 — returned label dropbox readiness (수신 경로/schema/validation command 준비·실 label 0·production gold 0).

freeze→reviewer worklist 가 만들어지면 reviewer 가 채운 label 을 **어디로 어떤 형식으로 돌려받고 어떻게 검증할지**
가 준비되어 있어야 한다 — 단, 실제 returned label 은 아직 없다. 이 모듈은 그 **수신 경계** 다:
  - dropbox 경로(`outputs/reviewer_batch/<batch_id>/intake`·gitignored·`reviewer_actual_input_gate` 스캔 경로와 동일),
  - returned-label schema/accepted vocabulary/validation command(단일 출처 `build_intake_plan`),
  - actual_returned_label_count(실 `*.jsonl` 파일만·없으면 0·synthetic fixture 0),
  - production_gold_count(실 returned human label + ≥2-reviewer agreement 전까지 **0**).

절대 불변(상속·상용 안전 계약):
  - **dropbox gitignored**: 실 reviewer label 은 reviewer_id/rationale PII 를 담을 수 있어 커밋 0(outputs/reviewer_batch/).
  - **synthetic ≠ gold · single reviewer ≠ gold · unsure/needs_review ≠ gold**: production_gold_count 0 유지.
  - **label 날조 0**: 코드가 returned label 을 만들지 않는다(경로/schema/검증만 준비).
  - merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · secret 0 · score 0(`_assert_pii_safe` 재귀 가드).
  test: scan_fn(fake)·label_readiness(주입) 시 결정론(network 0·디스크 쓰기 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.official_news_label_intake_readiness import (
    LABEL_INTAKE_READINESS_READY,
    run_official_news_label_intake_readiness,
)
from backend.app.tools.reviewer_actual_input_gate import (
    RETURNED_LABEL_GLOB,
    scan_actual_reviewer_input,
)
from backend.app.tools.reviewer_batch_launch import (
    LABELER_LABELS,
    build_intake_plan,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "returned_label_dropbox_readiness"

DROPBOX_READY = "returned_label_dropbox_ready"
DROPBOX_BLOCKED_SCHEMA = "returned_label_schema_not_ready"

SCHEMA_VERSION = "official_news_returned_label_v1"
# §12 accepted returned-label 어휘(단일 출처 LABELER_LABELS + §12 alias needs_more_context).
_NEEDS_MORE_CONTEXT = "needs_more_context"
_ACCEPTED_RETURNED_LABELS = sorted(set(LABELER_LABELS) | {_NEEDS_MORE_CONTEXT})

_DEFAULT_DROPBOX_BATCH_ID = "operator_regulatory_live"


def build_returned_label_dropbox_readiness(
    *, batch_id: str = _DEFAULT_DROPBOX_BATCH_ID,
    scan_fn: Optional[Callable[[Any], dict]] = None,
    label_readiness: Optional[dict] = None,
    label_readiness_fn: Optional[Callable[..., dict]] = None,
) -> dict:
    """returned label dropbox readiness — 수신 경로/schema/validation command 준비(실 label 0·production gold 0).

    dropbox 경로·expected file 名·validation command 는 단일 출처(`build_intake_plan`)에서 — reviewer 에게 전달할
    instruction 과 동일(드리프트 0). actual_returned_label_count 는 dropbox 의 실 `*.jsonl` 파일만 카운트(없으면 0).
    schema 수용 여부는 official×news label intake readiness dry-run(synthetic·production gold 0)에서 파생.
    label_readiness 주입 시 dry-run 재실행 생략(orchestrator 중복 호출 회피)."""
    scan_fn = scan_fn or scan_actual_reviewer_input

    # dropbox 경로/expected files/validation command(단일 출처·gitignored outputs/reviewer_batch/<batch>/intake).
    plan = build_intake_plan(batch_id, pseudonyms=["reviewer_a", "reviewer_b"])
    dropbox_path = str(plan["intake_directory"])

    # 실 returned label 파일 스캔(없으면 directory_exists=False·returned_label_files=[]).
    scan = scan_fn(dropbox_path)
    returned_files = list(scan.get("returned_label_files") or [])
    actual_returned_label_count = len(returned_files)   # 실 *.jsonl 파일 수(synthetic 0·없으면 0).

    # schema 수용 = official×news label intake readiness dry-run(synthetic·production gold 0·single/unsure ≠ gold).
    if label_readiness is not None:
        li = label_readiness
    else:
        li = (label_readiness_fn or run_official_news_label_intake_readiness)()
    schema_ready = li.get("label_intake_readiness_status") == LABEL_INTAKE_READINESS_READY
    production_gold_count = int(li.get("production_gold_count") or 0)   # 0(synthetic dry-run).

    status = DROPBOX_READY if schema_ready else DROPBOX_BLOCKED_SCHEMA
    out = {
        "operation_name": OPERATION_NAME,
        "returned_label_dropbox_status": status,
        "label_dropbox_ready": schema_ready,
        # 수신 경로/형식(단일 출처).
        "batch_id": str(batch_id),   # ADR#90 — batch 검사 가능(launch checklist batch 정합 lock).
        "dropbox_path": dropbox_path,
        "dropbox_gitignored": True,   # outputs/reviewer_batch/ 전체 gitignored(test-lock).
        "expected_returned_files_example": list(plan["expected_label_files"]),
        "returned_label_glob": RETURNED_LABEL_GLOB,
        "schema_version": SCHEMA_VERSION,
        "accepted_labels": list(_ACCEPTED_RETURNED_LABELS),
        "validation_command": str(plan["validation_command"]),
        "validation_command_ready": bool(plan.get("validation_command")),
        # 실 label 카운트(synthetic 분리·없으면 0).
        "actual_returned_label_count": actual_returned_label_count,
        "synthetic_fixture_counted_as_gold": False,
        "single_reviewer_label_is_gold": False,
        "unsure_label_is_gold": False,
        "agreement_required_for_gold": True,
        "production_gold_count": production_gold_count,   # 0 until real returned human labels.
        # ── 불변 경계(정직·constant) ──
        "label_fabricated": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": "" if schema_ready else "official_news_label_schema_not_ready",
        "next_action": (
            f"distribute the official×news reviewer worklist manually; reviewers return JSONL to {dropbox_path} "
            "(gitignored), then run the validation_command before import — production gold stays 0 until >=2-reviewer "
            "agreement on live-derived pairs"
            if schema_ready else
            "fix the official×news returned-label schema before opening the dropbox"),
    }
    _assert_pii_safe(out, _path="returned_label_dropbox_readiness_output")
    return out


def sanitized_dropbox_readiness(out: dict) -> dict:
    """snapshot/frontier 용 aggregate-only 투영(경로 본문 외 status/count 만)."""
    return {
        "returned_label_dropbox_status": out["returned_label_dropbox_status"],
        "label_dropbox_ready": out["label_dropbox_ready"],
        "actual_returned_label_count": out["actual_returned_label_count"],
        "production_gold_count": out["production_gold_count"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#89 returned label dropbox readiness (수신 경로/schema/validation command 준비·실 label 0·"
                     "production gold 0·synthetic/single/unsure ≠ gold·label 날조 0·merge 0·전송 0·secret 0)."))
    parser.add_argument("--batch-id", default=_DEFAULT_DROPBOX_BATCH_ID, help="dropbox batch id.")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_returned_label_dropbox_readiness(batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} status={out['returned_label_dropbox_status']}")
    print(f"- dropbox: path={out['dropbox_path']} gitignored={out['dropbox_gitignored']} "
          f"ready={out['label_dropbox_ready']}")
    print(f"- schema: version={out['schema_version']} accepted_labels={out['accepted_labels']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- returned_labels: actual={out['actual_returned_label_count']} "
          f"agreement_required={out['agreement_required_for_gold']}")
    print(f"- gold: production={out['production_gold_count']} synthetic_counted={out['synthetic_fixture_counted_as_gold']} "
          f"single_is_gold={out['single_reviewer_label_is_gold']} unsure_is_gold={out['unsure_label_is_gold']}")
    print(f"- gates: merge={out['merge_allowed']} sending={out['actual_sending_performed']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
