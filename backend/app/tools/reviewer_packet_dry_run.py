"""ADR#95 §14 (option G) — reviewer packet dry-run (freeze 가 성공하면 reviewer 가 받게 될 packet 의 *모양*을 SAFE dry-run 으로 조립·전송 0·PII 0·gold 0).

문제(ADR#84~#94): freeze→handoff bridge(§contact-PRE package)·hardening(§reviewer-facing 안전성)·freeze→R1
executable checklist 는 준비됐으나, "freeze 가 진짜로 성공했을 때 reviewer 가 받는 **packet 그 자체의 모양**"을
운영자가 미리 한 화면에서 보지 못한다. 진짜 freeze 가 없으면 production packet 을 만들 수 없고(BLOCKED), 그렇다고
모양 확인을 위해 가짜 gold 를 만들면 안 된다. 이 모듈은 그 간극을 **dry-run** 으로 메운다:

  - 진짜 freeze(`production_candidate_batch_ready` ∧ batch_id ∧ frozen_pair_count>0)가 있으면 그것으로 **production
    packet** 을 조립한다(`build_reviewer_handoff_bridge` 단일 출처). 단, 후보가 reviewer worklist record pair 를
    실어오면 `build_first_freeze_package_hardening` 으로 reviewer-facing 안전성을 먼저 검사하고, unsafe 면 packet 을
    내보내지 않는다(`blocked_freeze_artifact_unsafe`).
  - 진짜 freeze 가 없고 `synthetic=True`(기본)면, `build_first_live_freeze_r1_dry_run_harness` 의 **safe 합성 후보**를
    써서 **명백히 SYNTHETIC 으로 표식된** dry-run packet 만 조립한다(`is_production=False`·절대 production gold 아님).
  - 진짜 freeze 도 없고 `synthetic=False`면 정직하게 BLOCKED(`blocked_no_production_candidate_freeze`).

절대 불변(상속·상용 안전 계약·hardcode):
  - **actual_sending_performed=False**: 어떤 채널로도 자동 발송 0(operator 수동 배포).
  - **reviewer PII / score / rationale / predicted_status / same_event truth / raw body 0**: packet·output 어디에도
    forbidden-key 0 — 마지막에 `_assert_pii_safe` 재귀 가드를 통과한다(reviewer 는 `*_hidden` 선언만 본다).
  - **synthetic ≠ production ≠ gold**: 합성 packet 은 `synthetic_or_fake=True`·`is_production=False`. **production_gold_count
    는 항상 0**(packet 모양을 만든다고 gold 가 생기지 않는다).
  - merge 0 · network 0 · DB 0 · 디스크 쓰기 0 · secret 0 · LLM/embedding 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.first_freeze_package_hardening import (
    build_first_freeze_package_hardening,
)
from backend.app.tools.first_live_freeze_r1_dry_run_harness import (
    build_first_live_freeze_r1_dry_run_harness,
)
from backend.app.tools.r1_label_return_operational_bridge import (
    DEFAULT_BATCH_ID,
    intake_command,
)
from backend.app.tools.reviewer_batch_launch import build_intake_plan
from backend.app.tools.reviewer_handoff_bridge import build_reviewer_handoff_bridge
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "reviewer_packet_dry_run"
CONTRACT_VERSION = "reviewer_packet_dry_run_v1"

# reviewer_packet_dry_run_status.
PACKET_SYNTHETIC_DRY_RUN = "synthetic_reviewer_packet_dry_run_ready"
PACKET_PRODUCTION_READY = "production_reviewer_packet_ready"
PACKET_BLOCKED_NO_FREEZE = "blocked_no_production_candidate_freeze"
PACKET_BLOCKED_UNSAFE = "blocked_freeze_artifact_unsafe"

# blocked_reason codes — forbidden-key 문자열을 reason 에 echo 하지 않는다(값 누출 0).
_BLOCKED_REASON_NO_FREEZE = "no_production_candidate_freeze_and_synthetic_disabled"
_BLOCKED_REASON_UNSAFE = "freeze_artifact_failed_reviewer_hardening"

# reviewer 가 쓰는 accepted label 어휘(미러·instruction 산문용·단정 아님).
_ACCEPTED_REVIEWER_LABELS = ("same_event", "not_same_event", "unsure", "needs_more_context")
# synthetic preview 의 dropbox/expected-file 경로 단일 출처(build_intake_plan)에 줄 pseudonym(미러 dropbox readiness).
_PREVIEW_PSEUDONYMS = ["reviewer_a", "reviewer_b"]

_OFFICIAL_NEWS_ROLE_EXPLANATION = (
    "Each pair has one OFFICIAL record (a primary-source document: regulator/court/agency filing) and one NEWS "
    "record (a news article reporting on it). Decide only whether the two describe the SAME underlying real-world "
    "event. The official record is the evidence anchor; the news record is the report/reaction.")

_DELIVERY_NOTE = (
    "operator manually distributes this packet to >=2 pseudonymous reviewers per pair; the system performs no "
    "sending. Reviewers return JSONL to dropbox_path; run validation_command then intake_command. Production gold "
    "stays 0 until >=2-reviewer agreement on returned human labels.")

_NEXT_ACTION_NO_FREEZE = (
    "no production-candidate freeze and synthetic preview disabled -- provide a real frozen candidate "
    "(production_candidate_batch_ready + production_batch_id + production_frozen_pair_count>0) or run with "
    "synthetic=True to preview the packet shape; production gold stays 0 and nothing is sent")
_NEXT_ACTION_UNSAFE = (
    "the candidate's freeze worklist record pair failed reviewer-facing hardening -- remove non-allowlisted/"
    "forbidden fields from the official/news records before reviewer contact; no packet is emitted from an "
    "unsafe artifact and production gold stays 0")
_NEXT_ACTION_SYNTHETIC = (
    "preview only -- this SYNTHETIC packet shows the reviewer-facing shape; when a REAL in-window official/news "
    "candidate is frozen, the same shape is emitted as a production packet. Synthetic is never production gold "
    "(gold stays 0, no system sending, no reviewer roster committed)")
_NEXT_ACTION_PRODUCTION = (
    "operator: manually distribute this packet to >=2 pseudonymous reviewers per pair and collect returned JSONL "
    "into the dropbox, then run validation_command and intake_command; production gold stays 0 until those human "
    "labels pass >=2-reviewer agreement (no system sending)")


def _is_real_freeze(pc: Optional[dict]) -> bool:
    """진짜 freeze gate(reviewer_handoff_bridge 의 fail-closed gate 미러): batch_ready ∧ batch_id ∧ frozen_pair_count>0."""
    return (
        isinstance(pc, dict)
        and bool(pc.get("production_candidate_batch_ready"))
        and bool(str(pc.get("production_batch_id") or ""))
        and int(pc.get("production_frozen_pair_count") or 0) > 0)


def _candidate_record_pair(pc: dict) -> Optional[dict]:
    """후보가 실어온 reviewer worklist record pair(official_record×news_record)를 찾는다(없으면 None → hardening skip)."""
    for key in ("record_pair", "freeze_artifact", "reviewer_worklist_pair"):
        rp = pc.get(key)
        if isinstance(rp, dict):
            return rp
    if isinstance(pc.get("official_record"), dict) and isinstance(pc.get("news_record"), dict):
        return pc
    return None


def _label_instruction(vocabulary: Optional[list]) -> str:
    """reviewer 가 받는 same-event 라벨 지시문(model signal 미노출). vocabulary 주입 시 그 어휘를, 아니면 기본 어휘를 쓴다."""
    vocab = (
        [str(v) for v in vocabulary]
        if isinstance(vocabulary, (list, tuple)) and vocabulary
        else list(_ACCEPTED_REVIEWER_LABELS))
    return (
        "For each official/news pair, return exactly one label from the accepted vocabulary "
        f"({' / '.join(vocab)}) with your confidence and an ISO8601 reviewed_at. Judge same-event only; do not "
        "infer market impact or recommend any action. No model signals are shown -- decide independently from the "
        "two records.")


def _assemble_packet(
    *, batch_id: str, candidate_count: int, label_instruction: str, expected_return_file_pattern: str,
    dropbox_path: str, validation_command: str, intake_cmd: str, synthetic: bool,
) -> dict:
    """reviewer 가 받게 될 packet 의 모양(safe 필드만 — forbidden field 는 담지 않고 `*_hidden` 선언만 노출)."""
    return {
        "batch_id": batch_id,
        "candidate_count": candidate_count,
        "synthetic_or_fake": synthetic,
        "official_news_role_explanation": _OFFICIAL_NEWS_ROLE_EXPLANATION,
        "label_instruction": label_instruction,
        "accepted_labels": list(_ACCEPTED_REVIEWER_LABELS),
        "reviewers_per_pair_minimum": 2,
        "expected_return_file_pattern": expected_return_file_pattern,
        "dropbox_path": dropbox_path,
        "validation_command": validation_command,
        "intake_command": intake_cmd,
        "delivery_note": _DELIVERY_NOTE,
        # reviewer-facing 안전 표식 — forbidden field 는 실제로 부재하며, 숨겨졌다는 선언만 보인다.
        "score_hidden": True,
        "rationale_hidden": True,
        "predicted_status_hidden": True,
        "same_event_truth_hidden": True,
        "raw_body_hidden": True,
        "reviewer_pii_hidden": True,
    }


def _result(
    *, status: str, synthetic_or_fake: bool, is_production: bool, batch_id: str, candidate_count: int,
    official_news_role_explanation: str, label_instruction: str, expected_return_file_pattern: str,
    dropbox_path: str, validation_command: str, intake_cmd: str, packet: Optional[dict],
    blocked_reason: str, next_action: str,
) -> dict:
    """단일 출력 조립부 — 모든 분기가 여기로 수렴한다. 반환 직전 `_assert_pii_safe` 재귀 가드를 통과한다."""
    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "reviewer_packet_dry_run_status": status,
        # ── ADR#95 §14 packet shape 표면 ──
        "synthetic_or_fake": synthetic_or_fake,
        "is_production": is_production,
        "batch_id": batch_id,
        "candidate_count": candidate_count,
        "official_news_role_explanation": official_news_role_explanation,
        "label_instruction": label_instruction,
        "expected_return_file_pattern": expected_return_file_pattern,
        "dropbox_path": dropbox_path,
        "validation_command": validation_command,
        "intake_command": intake_cmd,
        "forbidden_fields_hidden": True,
        "packet": packet,
        "blocked_reason": blocked_reason,
        "next_action": next_action,
        # ── 불변 경계(정직·constant·hardcode) ──
        "actual_sending_performed": False,
        "reviewer_roster_committed": False,
        "score_hidden": True,
        "rationale_hidden": True,
        "predicted_status_hidden": True,
        "same_event_truth_hidden": True,
        "raw_body_hidden": True,
        "reviewer_pii_hidden": True,
        "merge_allowed": False,
        "production_gold_count": 0,
        "network_invoked": False,
    }
    _assert_pii_safe(out, _path="reviewer_packet_dry_run_output")
    return out


def _blocked(*, status: str, batch_id: str, blocked_reason: str, next_action: str, synthetic_or_fake: bool) -> dict:
    """packet 없음(BLOCKED) 출력 — 모든 string 필드 빈 값·packet None(unsafe artifact 본문/값 echo 0)."""
    return _result(
        status=status, synthetic_or_fake=synthetic_or_fake, is_production=False, batch_id=batch_id,
        candidate_count=0, official_news_role_explanation="", label_instruction="",
        expected_return_file_pattern="", dropbox_path="", validation_command="", intake_cmd="",
        packet=None, blocked_reason=blocked_reason, next_action=next_action)


def _production_packet(pc: dict, *, batch_id_arg: Optional[str]) -> dict:
    """진짜 freeze → production packet. 후보가 record pair 를 실어오면 hardening 으로 reviewer-facing 안전성 먼저 검사."""
    # 1) hardening(있을 때만) — unsafe 면 packet 미생성·forbidden 값 echo 0.
    record_pair = _candidate_record_pair(pc)
    if record_pair is not None:
        hard = build_first_freeze_package_hardening(
            artifact=record_pair, production_gold_count_before=0, production_gold_count_after=0)
        if not bool(hard.get("freeze_artifact_safe")):
            return _blocked(
                status=PACKET_BLOCKED_UNSAFE,
                batch_id=str(pc.get("production_batch_id") or batch_id_arg or DEFAULT_BATCH_ID),
                blocked_reason=_BLOCKED_REASON_UNSAFE, next_action=_NEXT_ACTION_UNSAFE, synthetic_or_fake=False)

    # 2) safe(또는 pair 없음) → 동결된 handoff bridge(단일 출처)에서 packet 모양을 cherry-pick. 후보에 poisoned
    #    operator_launch_checklist 가 끼면 build_reviewer_handoff_bridge 의 _assert_pii_safe 가 fail-loud(PII backstop).
    hb = build_reviewer_handoff_bridge(pc)
    hp = hb.get("handoff_package") or {}
    cand_batch_id = str(hp.get("batch_id") or pc.get("production_batch_id") or "")
    dropbox_path = str(hp.get("intake_directory") or "")
    validation_command = str(hp.get("validation_command") or "")
    intake_cmd = intake_command(batch_id=cand_batch_id, intake_dir=dropbox_path) if cand_batch_id else ""
    pattern = f"{cand_batch_id}__*__labels.jsonl" if cand_batch_id else ""
    candidate_count = int(hp.get("frozen_pair_count") or pc.get("production_frozen_pair_count") or 0)
    label_instruction = _label_instruction(hp.get("label_vocabulary"))
    packet = _assemble_packet(
        batch_id=cand_batch_id, candidate_count=candidate_count, label_instruction=label_instruction,
        expected_return_file_pattern=pattern, dropbox_path=dropbox_path,
        validation_command=validation_command, intake_cmd=intake_cmd, synthetic=False)
    return _result(
        status=PACKET_PRODUCTION_READY, synthetic_or_fake=False, is_production=True, batch_id=cand_batch_id,
        candidate_count=candidate_count, official_news_role_explanation=_OFFICIAL_NEWS_ROLE_EXPLANATION,
        label_instruction=label_instruction, expected_return_file_pattern=pattern, dropbox_path=dropbox_path,
        validation_command=validation_command, intake_cmd=intake_cmd, packet=packet,
        blocked_reason="", next_action=_NEXT_ACTION_PRODUCTION)


def _synthetic_packet(*, batch_id_arg: Optional[str]) -> dict:
    """진짜 freeze 없음 + synthetic=True → 명백히 SYNTHETIC 으로 표식된 dry-run packet(절대 production gold 아님)."""
    resolved = str(batch_id_arg or DEFAULT_BATCH_ID)
    # 합성 freeze→R1 dry-run harness 의 safe 합성 후보를 한 번 통과시켜 reviewer-facing 안전성을 확인한다(spec 요구).
    harness = build_first_live_freeze_r1_dry_run_harness(batch_id=resolved)
    if not bool(harness.get("freeze_artifact_safe")):
        # 기본 합성 후보는 항상 reviewer-safe — harness 가 거부하면 fail-closed(packet 미생성).
        return _blocked(
            status=PACKET_BLOCKED_UNSAFE, batch_id=resolved, blocked_reason=_BLOCKED_REASON_UNSAFE,
            next_action=_NEXT_ACTION_UNSAFE, synthetic_or_fake=True)

    # 경로/명령 string 은 순수 단일 출처(build_intake_plan·디스크 스캔 0)에서 — drift 0.
    plan = build_intake_plan(resolved, pseudonyms=_PREVIEW_PSEUDONYMS)
    dropbox_path = str(plan["intake_directory"])
    validation_command = str(plan["validation_command"])
    intake_cmd = intake_command(batch_id=resolved, intake_dir=dropbox_path)
    pattern = f"{resolved}__*__labels.jsonl"
    label_instruction = _label_instruction(None)
    packet = _assemble_packet(
        batch_id=resolved, candidate_count=1, label_instruction=label_instruction,
        expected_return_file_pattern=pattern, dropbox_path=dropbox_path,
        validation_command=validation_command, intake_cmd=intake_cmd, synthetic=True)
    return _result(
        status=PACKET_SYNTHETIC_DRY_RUN, synthetic_or_fake=True, is_production=False, batch_id=resolved,
        candidate_count=1, official_news_role_explanation=_OFFICIAL_NEWS_ROLE_EXPLANATION,
        label_instruction=label_instruction, expected_return_file_pattern=pattern, dropbox_path=dropbox_path,
        validation_command=validation_command, intake_cmd=intake_cmd, packet=packet,
        blocked_reason="", next_action=_NEXT_ACTION_SYNTHETIC)


def build_reviewer_packet_dry_run(
    *, production_candidate: Optional[dict] = None, synthetic: bool = True, batch_id: Optional[str] = None,
) -> dict:
    """freeze 가 성공하면 reviewer 가 받을 packet 의 *모양*을 SAFE dry-run 으로 조립한다(전송 0·PII 0·gold 0).

    진짜 freeze(`production_candidate_batch_ready` ∧ `production_batch_id` ∧ `production_frozen_pair_count`>0)면
    production packet(`build_reviewer_handoff_bridge` 단일 출처; record pair 가 있으면 hardening 으로 reviewer-facing
    안전성 먼저 검사, unsafe → BLOCKED). 아니면 `synthetic=True`(기본)일 때만 명백히 SYNTHETIC 으로 표식된 dry-run
    packet 을, `synthetic=False`면 정직하게 BLOCKED 를 낸다. 어떤 경로도 발송/merge/gold 생성/디스크 쓰기/secret 읽기를
    하지 않으며, production_gold_count 는 항상 0 이다."""
    pc = production_candidate if isinstance(production_candidate, dict) else None
    if pc is not None and _is_real_freeze(pc):
        return _production_packet(pc, batch_id_arg=batch_id)
    if synthetic:
        return _synthetic_packet(batch_id_arg=batch_id)
    return _blocked(
        status=PACKET_BLOCKED_NO_FREEZE, batch_id=str(batch_id or DEFAULT_BATCH_ID),
        blocked_reason=_BLOCKED_REASON_NO_FREEZE, next_action=_NEXT_ACTION_NO_FREEZE, synthetic_or_fake=False)


def sanitized_reviewer_packet_dry_run(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(status + flag + count 만 · 명령 문자열/packet 본문 제외)."""
    return {
        "reviewer_packet_dry_run_status": out["reviewer_packet_dry_run_status"],
        "synthetic_or_fake": out["synthetic_or_fake"],
        "is_production": out["is_production"],
        "batch_id": out["batch_id"],
        "candidate_count": out["candidate_count"],
        "forbidden_fields_hidden": out["forbidden_fields_hidden"],
        "actual_sending_performed": out["actual_sending_performed"],
        "reviewer_roster_committed": out["reviewer_roster_committed"],
        "merge_allowed": out["merge_allowed"],
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
        description=("ADR#95 reviewer packet dry-run (freeze 성공 시 reviewer 가 받을 packet 모양을 SAFE dry-run 으로 "
                     "조립; 전송 0·reviewer PII/score/rationale/predicted/same_event/raw body 0·synthetic≠production≠gold·"
                     "production_gold_count 0·merge 0·network 0). CLI 는 freeze 후보를 받지 않으므로 기본은 synthetic "
                     "preview 다(--no-synthetic 면 BLOCKED)."))
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="preview/dropbox batch id.")
    parser.add_argument("--no-synthetic", action="store_true",
                        help="synthetic preview 비활성화(진짜 frozen 후보 없이는 BLOCKED).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(명령 문자열/packet 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_reviewer_packet_dry_run(synthetic=not ns.no_synthetic, batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(sanitized_reviewer_packet_dry_run(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} ({out['contract_version']}) "
          f"status={out['reviewer_packet_dry_run_status']}")
    print(f"- synthetic_or_fake={out['synthetic_or_fake']} is_production={out['is_production']} "
          f"candidate_count={out['candidate_count']} batch_id={out['batch_id']}")
    print(f"- forbidden_fields_hidden={out['forbidden_fields_hidden']} score_hidden={out['score_hidden']} "
          f"rationale_hidden={out['rationale_hidden']} predicted_status_hidden={out['predicted_status_hidden']} "
          f"same_event_truth_hidden={out['same_event_truth_hidden']} raw_body_hidden={out['raw_body_hidden']} "
          f"reviewer_pii_hidden={out['reviewer_pii_hidden']}")
    print(f"- gates: actual_sending={out['actual_sending_performed']} reviewer_roster_committed={out['reviewer_roster_committed']} "
          f"merge={out['merge_allowed']} network={out['network_invoked']} production_gold_count={out['production_gold_count']}")
    if out["packet"] is not None:
        print(f"- dropbox_path: {out['dropbox_path']} (pattern={out['expected_return_file_pattern']})")
        print(f"- validation_command: {out['validation_command']}")
        print(f"- intake_command: {out['intake_command']}")
    if out["blocked_reason"]:
        print(f"- blocked_reason: {out['blocked_reason']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
