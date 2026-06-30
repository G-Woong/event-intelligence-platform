"""ADR#94 §13 — first live freeze→R1 dry-run harness (합성/가짜 freeze 후보로 freeze→hardening→R1 체크리스트 경로를
*깨지지 않게* 미리 한 번 돌려보는 dry-run; synthetic 은 NEVER production gold · 전송 0 · network 0).

문제(ADR#92~#93): freeze package hardening(§11)과 freeze→R1 executable checklist(§12)는 준비됐으나, *실제* live
production candidate 가 아직 0 이라 그 전체 경로가 한 번도 end-to-end 로 실행된 적이 없다. 진짜 live 후보가 나타나는
바로 그 순간 경로가 깨져 있으면 늦다. 이 모듈은 **합성/가짜(synthetic/fake)** freeze 후보를 만들어 hardening→R1
체크리스트 경로를 미리 한 번 통과시켜(dry-run) 경로가 살아있음을 증명한다. 합성/가짜는 reviewer worklist 흉내일 뿐
**절대 production gold 가 아니다** — gold 는 진짜 returned human label + >=2-reviewer 합의 전까지 0 으로 고정된다.

절대 불변(§13·상속·constant): synthetic_or_fake=True(항상 가짜로 표식) · 합성은 production gold 아님(is_production_gold=False·
production_gold_count=0) · freeze-artifact-safe 검사 필수(unsafe 합성은 거부) · actual sending 0 · reviewer roster 미커밋 ·
real returned label 미집계(real_label_counted=False) · merge 0 · public post/comment 0 · network 0 · 디스크 쓰기 0 ·
secret 읽기 0. 경로/명령/배치 id 는 기존 단일 출처(hardening·freeze→R1 bridge) 재사용(재저작 0)."""
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
from backend.app.tools.r1_label_return_operational_bridge import DEFAULT_BATCH_ID
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "first_live_freeze_r1_dry_run_harness"

# freeze_r1_dry_run_status.
DRY_RUN_READY = "synthetic_freeze_r1_dry_run_ready"
DRY_RUN_REJECTED = "synthetic_artifact_rejected"


def _default_synthetic_pair() -> dict:
    """기본 SAFE 합성/가짜 freeze 후보(iter_freeze_eligible_record_pairs 형태 · production gold 아님).

    test 의 `_safe_pair()` 템플릿을 미러 — 각 record 는 allowlist 키만 담는다(record_type/source_id/canonical_url/
    published_at_or_observed_at/title_or_label) · forbidden/extra 키 0. 한쪽은 official, 한쪽은 news 이고 둘 다
    canonical_url+published_at 을 갖는다. 내용은 명백히 SYNTHETIC 으로 표식(진짜 live 후보 아님)."""
    return {
        "pair_id": "synthetic_dry_run_0001",
        "official_record": {
            "record_type": "official_document",
            "source_id": "synthetic_official_source",
            "canonical_url": "https://example.org/synthetic/official/freeze-r1-dry-run",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC official record for freeze->R1 dry-run (not production gold)",
        },
        "news_record": {
            "record_type": "news_article",
            "source_id": "synthetic_news_source",
            "canonical_url": "https://example.com/synthetic/news/freeze-r1-dry-run",
            "published_at_or_observed_at": "2026-06-25",
            "title_or_label": "SYNTHETIC news article for freeze->R1 dry-run (not production gold)",
        },
        "shared_tokens": ["synthetic", "dry", "run"],
        "date_proximity_days": 0,
    }


def _next_action(*, status: str, blocked_reason: str) -> str:
    """freeze_r1_dry_run_status → operator 한 줄 next_action(synthetic dry-run 의미를 정직하게 환원)."""
    if status == DRY_RUN_READY:
        return (
            "synthetic/fake freeze->hardening->R1 checklist path was exercised end-to-end and stayed unbroken — when a "
            "REAL in-window official x news live candidate is frozen, run this same path on it; the synthetic candidate "
            "is never production gold (gold stays 0, no sending, no reviewer roster, no merge)")
    return (
        "synthetic freeze artifact was rejected by hardening (the path guard works as intended) — fix the synthetic "
        f"fixture before relying on the dry-run: {blocked_reason}; no checklist was built, production gold stays 0")


def build_first_live_freeze_r1_dry_run_harness(
    *, synthetic_pair: Optional[dict] = None, batch_id: Optional[str] = None,
) -> dict:
    """합성/가짜 freeze 후보로 freeze->hardening->R1 체크리스트 경로를 dry-run(PURE·전송 0·network 0·gold 0).

    `synthetic_pair` 미제공 시 `_default_synthetic_pair()`(SAFE 합성 후보) 사용. hardening 으로 reviewer-facing
    안전성을 검사하고(unsafe 합성 → DRY_RUN_REJECTED·체크리스트 미생성), safe 면 `build_freeze_to_r1_executable_checklist`
    를 통과시켜 명령 준비 상태(validation/intake/agreement)·dropbox·배치 정합을 확인한다. 출력은 flag/status/count 만
    담고 합성 record 본문을 echo 하지 않는다 — 합성은 절대 production gold 가 아니며(production_gold_count 는 bridge
    exact passthrough 0), 어떤 경로도 발송/merge/gold 생성/디스크 쓰기/secret 읽기를 하지 않는다."""
    pair = synthetic_pair if isinstance(synthetic_pair, dict) else _default_synthetic_pair()
    freeze_candidate_present = isinstance(pair, dict)
    resolved_batch_id = batch_id or DEFAULT_BATCH_ID

    # 1) freeze artifact hardening(reviewer-facing 안전성) — gold 불변(before==after==0). network 0·디스크 쓰기 0.
    hard = build_first_freeze_package_hardening(
        artifact=pair, production_gold_count_before=0, production_gold_count_after=0)
    freeze_package_hardening_status = str(hard["freeze_package_hardening_status"])
    freeze_artifact_safe = bool(hard["freeze_artifact_safe"])
    blocked_reason = str(hard.get("blocked_reason") or "")
    all_blockers = list(hard.get("all_blockers") or [])

    if freeze_artifact_safe:
        # 2) safe 합성 → freeze->R1 executable checklist 경로를 통과시킨다(단일 출처·재저작 0).
        fr1 = build_freeze_to_r1_executable_checklist(
            freeze_artifact=pair, batch_id=resolved_batch_id)
        freeze_to_r1_status = str(fr1["freeze_to_r1_status"])
        batch_id_consistent = not bool(fr1["batch_id_mismatch"])
        label_dropbox_ready = bool(fr1["dropbox_path"])
        validation_command_ready = bool(fr1["label_validation_command"])
        intake_command_ready = bool(fr1["label_intake_command"])
        agreement_command_ready = bool(fr1["agreement_check_command"])
        production_gold_count = int(fr1["production_gold_count"])   # bridge exact passthrough(합성이어도 0).
        status = DRY_RUN_READY
    else:
        # unsafe 합성 → 거부(체크리스트 미생성). 경로 guard 가 합성 결함을 막아준다는 증명 자체가 dry-run 의 목적.
        freeze_to_r1_status = ""
        batch_id_consistent = False
        label_dropbox_ready = False
        validation_command_ready = False
        intake_command_ready = False
        agreement_command_ready = False
        production_gold_count = 0
        status = DRY_RUN_REJECTED

    next_action = _next_action(status=status, blocked_reason=blocked_reason)

    out = {
        "operation_name": OPERATION_NAME,
        "freeze_r1_dry_run_status": status,
        # ── 합성/가짜 표식(항상) · 합성은 절대 production gold 아님. ──
        "synthetic_or_fake": True,
        "freeze_candidate_present": freeze_candidate_present,
        "freeze_artifact_safe": freeze_artifact_safe,
        "freeze_package_hardening_status": freeze_package_hardening_status,
        # ── freeze->R1 체크리스트 경로 결과(safe 일 때만 채워짐). ──
        "freeze_to_r1_status": freeze_to_r1_status,
        "batch_id": resolved_batch_id,
        "batch_id_consistent": batch_id_consistent,
        "label_dropbox_ready": label_dropbox_ready,
        "validation_command_ready": validation_command_ready,
        "intake_command_ready": intake_command_ready,
        "agreement_command_ready": agreement_command_ready,
        "production_gold_count": production_gold_count,   # 합성이어도 0(bridge passthrough).
        "blocked_reason": blocked_reason,
        "all_blockers": all_blockers,
        "next_action": next_action,
        # ── 정직 불변(hardcode·constant·합성은 진짜가 아니다) ──
        "is_production_gold": False,
        "actual_sending_performed": False,
        "reviewer_roster_committed": False,
        "real_label_counted": False,
        "merge_allowed": False,
        "network_invoked": False,
    }
    _assert_pii_safe(out, _path="first_live_freeze_r1_dry_run_harness_output")
    return out


def sanitized_first_live_freeze_r1_dry_run_harness(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status + flag + count 만 · 명령 문자열/raw record 제외)."""
    return {
        "freeze_r1_dry_run_status": out["freeze_r1_dry_run_status"],
        "synthetic_or_fake": out["synthetic_or_fake"],
        "freeze_artifact_safe": out["freeze_artifact_safe"],
        "freeze_to_r1_status": out["freeze_to_r1_status"],
        "batch_id_consistent": out["batch_id_consistent"],
        "is_production_gold": out["is_production_gold"],
        "actual_sending_performed": out["actual_sending_performed"],
        "real_label_counted": out["real_label_counted"],
        "merge_allowed": out["merge_allowed"],
        "production_gold_count": out["production_gold_count"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#94 first live freeze->R1 dry-run harness (합성/가짜 freeze 후보로 freeze->hardening->R1 "
                     "체크리스트 경로를 미리 통과시켜 경로가 깨지지 않음을 증명; synthetic 은 NEVER production gold·전송 0·"
                     "reviewer roster 미커밋·merge 0·network 0·gold 0). CLI 는 기본 합성 후보를 사용한다."))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="contact/dropbox/intake batch id.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령 문자열 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_first_live_freeze_r1_dry_run_harness(batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(sanitized_first_live_freeze_r1_dry_run_harness(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['freeze_r1_dry_run_status']} "
          f"synthetic_or_fake={out['synthetic_or_fake']} is_production_gold={out['is_production_gold']}")
    print(f"- freeze: hardening={out['freeze_package_hardening_status']} safe={out['freeze_artifact_safe']} "
          f"candidate_present={out['freeze_candidate_present']}")
    print(f"- freeze_to_r1: status={out['freeze_to_r1_status'] or '(not built)'} "
          f"batch_id={out['batch_id']} batch_id_consistent={out['batch_id_consistent']}")
    print(f"- commands_ready: dropbox={out['label_dropbox_ready']} validation={out['validation_command_ready']} "
          f"intake={out['intake_command_ready']} agreement={out['agreement_command_ready']}")
    print(f"- gold: production_gold_count={out['production_gold_count']} real_label_counted={out['real_label_counted']}")
    print(f"- gates: actual_sending={out['actual_sending_performed']} reviewer_roster_committed={out['reviewer_roster_committed']} "
          f"merge={out['merge_allowed']} network={out['network_invoked']}")
    if out["blocked_reason"]:
        print(f"- blocked_reason: {out['blocked_reason']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
