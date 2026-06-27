"""ADR#75 — R1 first reviewer pilot batch freeze + operator launch handoff (병합 0·LLM 0·embedding 0·DB 0·전송 0).

ADR#74 가 만든 것: R1 gold acquisition **operating plan**(actual input 재확인 + gold floor gap + operator next
manual action). 그러나 그것은 *계획*일 뿐 — 실제 reviewer 에게 넘길 수 있는 **동결된 첫 R1 pilot batch**(frozen pair
worklist·deterministic signature·expected label files·intake/validation 경로를 하나의 immutable batch 로 묶은 것)와,
운영자가 그대로 수동 실행하는 **operator launch package**, internal ops UI 의 **launch readiness**가 없었다. "R1
plan 이 있으니 라벨 수집이 시작됐다"로 착각할 자리가 남는다(R-GoldAcquisitionPlanOnly).

이 모듈은 **재구현이 아니라 freeze + handoff orchestrator** 다. 무거운 일은 전부 단일 출처가 한다:
  - actual input 재확인(no_actual_input/external_input_required·production_gold_count exact passthrough): 단일 호출
    `reviewer_actual_input_gate.run_actual_input_gate`(재호출 0).
  - 후보 worklist(결정적·오프라인·LLM 0·network 0): `source_overlap_discovery.build_captured_overlap_fixture` →
    `discover_overlap` → `near_match_reviewer_queue.build_near_match_reviewer_queue`.
  - freeze artifacts(instruction·template·manifest·intake plan·handoff bundle): `reviewer_batch_launch` /
    `reviewer_pilot_handoff` 의 **순수 builder**(체인 실행 0·발산 0 — followup/intake 재호출 없음).
  - R1 status/floor: `r1_gold_acquisition_plan._r1_status` + `REQUIRED_PRODUCTION_GOLD`(canonical 재사용).
  - PII 재귀 가드: `reviewer_pilot_handoff._assert_pii_safe`.

이 모듈이 **새로** 더하는 것(기존에 없던 운영 결손):
  - **frozen reviewer-facing pair worklist(§5)**: pair_id·source_role·title·canonical_url·observed_at·language 만
    (score/rationale/predicted_status/same_event/raw body/PII 구조적 부재 — template allowlist 파생). dedupe·정렬.
  - **deterministic batch_signature(§5)**: 정렬된 pair 정체성 + batch config 의 sha256. wall-clock/PII/score/rationale
    제외 → 같은 입력=같은 signature(order-invariant·provenance 박제).
  - **launch_status(§4·5-state)**: blocked_no_candidates/ready_for_manual_launch/awaiting_manual_launch/
    awaiting_returned_labels/labels_present — frozen + 게이트 actual-input 축에서 파생(둔갑 0).
  - **operator launch checklist(§6)**: 수동 배포/회수/검증 단계 + manual-only contact 지시 + PII/secret 금지 reminder.
    실제 email/slack/webhook 전송 0·label/contact evidence/roster 생성 0.

절대 불변(상속·상용 안전 계약):
  - **합성 fixture 를 production 후보로 둔갑 0**: 유일 오프라인 후보 source 는 합성 captured fixture 다(실 source
    아님). `candidate_provenance="synthetic_fixture"`·`pilot_batch_is_production_candidate=False` 를 **명시**하고,
    freeze 는 freeze→handoff→validation **machinery 를 증명**하는 구조적 pilot 일 뿐 — 실 production gold 는 live
    source overlap(이번 턴 No-Go)으로 실 후보를 얻고 실 reviewer 가 라벨링해야 한다. 라벨이 회수돼도 dataset_source=
    synthetic 이라 intake chain 이 production gold 로 승격하지 않는다(machinery 강제).
  - **batch freeze ≠ truth·≠ 라벨 생성**: frozen batch 는 reviewer worklist 동결이지 same_event 동결이 아니다.
    production_gold_count 를 늘리지 않고, 라벨 회수를 함의하지 않는다.
  - **입력 날조 0·production_gold_count exact passthrough**: gold/calibration/merge_gate 는 전부 게이트 결과 그대로.
  - **no merge / no public IU / no DB / no LLM / no embedding / no 전송 / no secret read**: 전 경로 상속.
  - **internal ops ≠ public truth**: launch readiness 는 workflow 상태만. same_event·score·rationale·predicted_status·
    raw PII·secret 은 contract 에 필드 자체가 없다(구조적 미노출) + 전체 재귀 가드.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Optional

from backend.app.services.identity_human_labeling import (
    DEFAULT_REVIEWERS_PER_PAIR,
    SOURCE_SYNTHETIC,
)
from backend.app.tools.near_match_reviewer_queue import build_near_match_reviewer_queue
from backend.app.tools.r1_gold_acquisition_plan import (
    REQUIRED_PRODUCTION_GOLD,
    _r1_status,
)
from backend.app.tools.reviewer_actual_input_gate import (
    INPUT_INVALID_RETURNED,
    INPUT_LABELS_IMPORTED,
    INPUT_RETURNED_PRESENT,
    run_actual_input_gate,
)
from backend.app.tools.reviewer_batch_launch import (
    build_assignment_manifest,
    build_intake_plan,
    build_label_template,
    build_reviewer_instruction,
)
from backend.app.tools.reviewer_pilot_handoff import (
    _assert_pii_safe,
    build_pilot_handoff_bundle,
)
from backend.app.tools.source_overlap_discovery import (
    build_captured_overlap_fixture,
    discover_overlap,
)

OPERATION_NAME = "r1_reviewer_pilot_batch"

# ── §4 launch_status(5-state·launch readiness 축) ──────────────────────────────────────────────────────────
# blocked_no_candidates: frozen pair 0(worklist 없음). ready_for_manual_launch: frozen·intake dir 미설정(operator
# 미시작). awaiting_manual_launch: frozen·intake dir 설정(회수 경로 준비)이나 contact/label 0. awaiting_returned_labels:
# contact evidence 있음(또는 invalid 회수) — 유효 라벨 회수 대기. labels_present: 유효 returned label 회수됨.
LAUNCH_BLOCKED_NO_CANDIDATES = "blocked_no_candidates"
LAUNCH_READY_FOR_MANUAL = "ready_for_manual_launch"
LAUNCH_AWAITING_MANUAL = "awaiting_manual_launch"
LAUNCH_AWAITING_RETURNED = "awaiting_returned_labels"
LAUNCH_LABELS_PRESENT = "labels_present"
LAUNCH_STATES = frozenset({
    LAUNCH_BLOCKED_NO_CANDIDATES, LAUNCH_READY_FOR_MANUAL, LAUNCH_AWAITING_MANUAL,
    LAUNCH_AWAITING_RETURNED, LAUNCH_LABELS_PRESENT,
})

# 후보 provenance — 이번 턴 오프라인 결정적 source 는 **합성** captured fixture 뿐(실 source 아님). live source
# overlap 으로 실 후보를 얻는 경로는 이번 턴 No-Go(credentials·live fetch). production 둔갑 차단의 핵심 플래그.
PROVENANCE_SYNTHETIC_FIXTURE = "synthetic_fixture"

# launch_status → operator 한 줄 next action(internal ops UI 가 읽는 단일 요약).
_LAUNCH_NEXT_ACTION = {
    LAUNCH_BLOCKED_NO_CANDIDATES: (
        "run source overlap acquisition (live smoke with credentials/opt-in) to obtain production candidate "
        "pairs — the current offline source is a synthetic fixture (do not fabricate pairs)"),
    LAUNCH_READY_FOR_MANUAL: (
        "operator: manually distribute the frozen worklist + instruction + label template to >=2 pseudonymous "
        "reviewers per pair, then collect returned label JSONL into the intake directory (no system sending)"),
    LAUNCH_AWAITING_MANUAL: (
        "operator: complete the manual send (intake directory is set up) and collect returned label JSONL, "
        "then run the validation command (the system records no contact evidence and generates no labels)"),
    LAUNCH_AWAITING_RETURNED: (
        "operator: chase missing/invalid returned labels with a manual reminder (no value leak), then re-run "
        "the validation command"),
    LAUNCH_LABELS_PRESENT: (
        "returned labels present — the intake chain validates and (only if production + live_derived) promotes "
        "to gold; review MERGE_GATE readiness (no auto-merge)"),
}


# ── §5: frozen reviewer-facing pair worklist(allowlist 파생·score/rationale/predicted 구조적 부재) ──────────
def _frozen_pair_list(template: list[dict]) -> list[dict]:
    """label template rows(REVIEWER_ALLOWED_KEYS allowlist·fail-loud) → frozen reviewer-facing **pair** list.

    pair_id 로 dedupe(reviewer-specific 칸 제거)하고 pair_id 정렬(order-invariant). source_role=source_type.
    observed_at=published proxy. 별도 source_name/topic/time_window 는 chain 에 부재 — **날조 안 함**(정직 생략).
    score/rationale/predicted_status/same_event/raw body/PII 는 template allowlist 가 이미 구조적으로 차단."""
    by_pair: dict[str, dict] = {}
    for r in template:
        pid = r["pair_id"]
        if pid in by_pair:
            continue
        pair: dict[str, Any] = {
            "pair_id": pid,
            "source_role_a": r["source_type_left"],
            "source_role_b": r["source_type_right"],
            "title_a": r["title_left"],
            "title_b": r["title_right"],
            "observed_at_a": r["observed_at_left"],
            "observed_at_b": r["observed_at_right"],
            "language": r["language"],
        }
        if r.get("canonical_url_left"):
            pair["canonical_url_a"] = r["canonical_url_left"]
        if r.get("canonical_url_right"):
            pair["canonical_url_b"] = r["canonical_url_right"]
        by_pair[pid] = pair
    return [by_pair[pid] for pid in sorted(by_pair)]


def _batch_signature(
    frozen_pairs: list[dict], *, batch_id: str, target_pair_count: int,
    reviewers_per_pair: int, provenance: str,
) -> str:
    """정렬된 pair 정체성 + batch config 의 deterministic sha256. wall-clock/PII/score/rationale/title 제외 →
    같은 입력=같은 signature(order-invariant·fixture 결정적). title 은 식별이 아니라 표시 텍스트라 signature 에서
    제외(pair_id·canonical_url·source_role·observed_at·language 가 pair 정체성)."""
    canon = {
        "batch_id": batch_id,
        "provenance": provenance,
        "target_pair_count": target_pair_count,
        "reviewers_per_pair": reviewers_per_pair,
        "pairs": [
            [
                p["pair_id"], p.get("canonical_url_a", ""), p.get("canonical_url_b", ""),
                p["source_role_a"], p["source_role_b"], p["observed_at_a"], p["observed_at_b"], p["language"],
            ]
            for p in frozen_pairs   # 이미 pair_id 정렬됨.
        ],
    }
    blob = json.dumps(canon, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _launch_status(
    *, frozen_pair_count: int, actual_input_status: str, returned_label_count: int,
    dir_exists: bool, contact_found: bool,
) -> str:
    """frozen + 게이트 actual-input 축 → launch_status(둔갑 0). frozen 0 → blocked_no_candidates. 유효 returned
    label → labels_present. invalid/ contact_only → awaiting_returned_labels. no_actual_input 은 intake dir 존재
    여부로 ready_for_manual_launch(미설정·미시작) vs awaiting_manual_launch(설정·회수 경로 준비)로 분할."""
    if frozen_pair_count <= 0:
        return LAUNCH_BLOCKED_NO_CANDIDATES
    if actual_input_status in (INPUT_RETURNED_PRESENT, INPUT_LABELS_IMPORTED) and returned_label_count > 0:
        return LAUNCH_LABELS_PRESENT
    if actual_input_status == INPUT_INVALID_RETURNED:
        return LAUNCH_AWAITING_RETURNED
    if contact_found:
        return LAUNCH_AWAITING_RETURNED
    if dir_exists:
        return LAUNCH_AWAITING_MANUAL
    return LAUNCH_READY_FOR_MANUAL


# ── §6: operator launch checklist(수동 실행·전송 0·생성 0) ──────────────────────────────────────────────────
def build_operator_launch_checklist(
    *, batch_id: str, batch_signature: str, intake_plan: dict, bundle: dict,
    frozen_pair_count: int, provenance: str,
) -> dict:
    """operator 가 그대로 수동 실행하는 launch checklist(§6). **실제 전송 0·label/contact evidence/roster 생성 0**.

    포함(§6): pilot_batch_id·signature·instruction/template/manifest 참조·expected files·placement·validation·
    no-go·manual-only contact·PII/secret 금지. 금지(§6): raw roster·email·phone·contact evidence·returned labels·
    score/rationale/predicted_status·same_event·raw body — `_assert_pii_safe` 재귀 가드로 강제."""
    checklist = {
        "pilot_batch_id": batch_id,
        "batch_signature": batch_signature,
        "candidate_provenance": provenance,
        "frozen_pair_count": frozen_pair_count,
        "steps": [
            "1) review the frozen reviewer worklist (pair_id·source_role·title·canonical_url·observed_at·"
            "language only — no scores/rationale/predicted_status/same_event truth)",
            "2) recruit >=2 pseudonymous reviewers per pair (raw roster/local mapping stay operator-local, "
            "never committed)",
            "3) distribute the reviewer instruction + label template + per-reviewer assignment summary MANUALLY "
            "(no system email/slack/webhook sending)",
            f"4) collect returned label JSONL into the gitignored intake directory: {intake_plan['intake_directory']}",
            f"5) run the validation command: {intake_plan['validation_command']}",
            "6) do not edit the label schema; do not include PII/secret/score/rationale/predicted_status; do not "
            "assert same_event truth",
        ],
        "expected_label_files": list(intake_plan["expected_label_files"]),
        "placement_guide": (
            f"place each reviewer's *.jsonl into {intake_plan['intake_directory']} "
            f"(filename = {batch_id}__<reviewer_pseudonym>__labels.jsonl)"),
        "validation_command": intake_plan["validation_command"],
        "manual_only_contact_instruction": (
            "operator manually sends the packet and collects files — the system performs no sending and "
            "generates no contact evidence or labels"),
        "pii_secret_forbidden_reminder": (
            "never include raw reviewer name/email/phone, API keys, secrets, scores, rationales, "
            "predicted_status, same_event truth, or raw source body"),
        "dry_run_only": provenance == PROVENANCE_SYNTHETIC_FIXTURE,
        "no_go_warnings": (
            (["SYNTHETIC FIXTURE pilot — use only to validate the labeling process (dry-run); do NOT collect "
              "production gold from it (returned labels are tagged dataset_source=synthetic and cannot become "
              "production gold); acquire real candidate pairs from live source overlap before production labeling"]
             if provenance == PROVENANCE_SYNTHETIC_FIXTURE else [])
            + [
                "frozen batch is a reviewer worklist, not event truth",
                "production gold remains 0 until human production labels are imported",
                "R2~R7 remain No-Go",
            ]),
        "allowed_labels": list(bundle["allowed_labels"]),
    }
    _assert_pii_safe(checklist, _path="operator_launch_checklist")
    return checklist


# ── §4: 통합 R1 reviewer pilot batch freeze entrypoint ─────────────────────────────────────────────────────
def run_r1_reviewer_pilot_batch(
    *, directory: Optional[Any] = None, batch_id: str = "reviewer_pilot_exec_001",
    as_of: Optional[str] = None,
) -> dict:
    """R1 first reviewer pilot batch freeze + operator launch handoff(병합 0·LLM 0·embedding 0·DB 0·전송 0).

    1) actual input 재확인: 단일 출처 게이트 1회 호출로 no_actual_input/external_input_required + production_gold_count
       + actual-input 축 정직 산출(재호출 0·입력 날조 0).
    2) frozen pilot batch: 결정적·오프라인 **합성** fixture 후보를 순수 builder 로 동결(frozen pair worklist·
       deterministic signature·expected files·intake/validation·operator package). provenance=synthetic_fixture 명시
       — production 후보 둔갑 0(실 후보는 live overlap 필요·이번 턴 No-Go).
    3) launch readiness: launch_status(5-state)·R1 gap·R2~R7 No-Go·sanitized contract(internal ops UI 용).
    어떤 경로도 입력 날조·merge·LLM·embedding·DB·전송·secret read·same_event 확정·label 생성을 하지 않는다."""
    # 1) actual input 재확인(단일 출처 게이트 1회). production 경로(queue 미배선=empty) — 실 returned label 만 본다.
    gate = run_actual_input_gate(directory=directory, batch_id=batch_id, as_of=as_of)

    # 2) 결정적·오프라인 후보 worklist(**합성** captured fixture — 유일 오프라인 source·LLM 0·network 0).
    #    실 production 후보는 live source overlap 필요(이번 턴 No-Go) → provenance 정직 표기·production 둔갑 0.
    provenance = PROVENANCE_SYNTHETIC_FIXTURE
    packet_id = f"{batch_id}_pilot_batch"
    disc = discover_overlap(build_captured_overlap_fixture())
    queue = build_near_match_reviewer_queue(disc, packet_id=packet_id)

    # 3) freeze artifacts(순수 builder·체인 실행 0·발산 0 — followup/intake 재호출 없음·동일 queue/batch_id).
    instruction = build_reviewer_instruction()
    # **template 을 합성 provenance 로 태깅**(adversarial HIGH-1): 이 batch 에서 회수된 라벨은 dataset_source=
    # synthetic 이라 intake chain(production gold = production AND live_derived)이 production gold 로 승격하지
    # 않는다(machinery 강제 — "합성→production gold 둔갑 0"이 선언이 아니라 코드로 보장). live provenance 도입 시
    # 이 매핑을 live 로 바꾼다(현재 합성 fixture 뿐).
    template = build_label_template(queue, dataset_source=SOURCE_SYNTHETIC)
    manifest = build_assignment_manifest(queue, batch_id=batch_id)
    # intake_dir = 게이트가 실제 스캔한 경로(display)로 정렬 → intake_directory/validation_command/placement 가
    # 게이트 스캔 경로와 단일 경로로 수렴(Q8 일관성·directory override 시에도 발산 0).
    intake_plan = build_intake_plan(
        batch_id, pseudonyms=manifest["pseudonymous_reviewers"], intake_dir=gate["input_directory"])
    bundle = build_pilot_handoff_bundle(
        batch_id=batch_id, packet_id=packet_id, instruction=instruction, manifest=manifest,
        intake_plan=intake_plan, template=template, intake_dir_display=gate["input_directory"])

    frozen_pairs = _frozen_pair_list(template)
    frozen_pair_count = len(frozen_pairs)
    batch_frozen = frozen_pair_count > 0
    # target = operating floor proxy(실제 필요 pair ≥ 200; non-decisive/conflict 고려 시 더 큼). frozen << target → pilot_n.
    target_pair_count = REQUIRED_PRODUCTION_GOLD
    batch_signature = (
        _batch_signature(
            frozen_pairs, batch_id=batch_id, target_pair_count=target_pair_count,
            reviewers_per_pair=DEFAULT_REVIEWERS_PER_PAIR, provenance=provenance)
        if batch_frozen else "")

    # 4) launch_status(frozen + 게이트 actual-input 축). 합성이어도 worklist 자체는 ready — production 후보 여부는
    #    candidate_provenance/pilot_batch_is_production_candidate 가 별도로 명시(launch_status 가 production 을 함의 0).
    launch_status = _launch_status(
        frozen_pair_count=frozen_pair_count, actual_input_status=gate["actual_input_status"],
        returned_label_count=gate["returned_label_count"], dir_exists=gate["input_directory_exists"],
        contact_found=gate["actual_contact_evidence_found"])
    ready_for_manual_launch = launch_status in (LAUNCH_READY_FOR_MANUAL, LAUNCH_AWAITING_MANUAL)

    # 5) operator launch checklist(§6·전송 0·생성 0).
    checklist = build_operator_launch_checklist(
        batch_id=batch_id, batch_signature=batch_signature, intake_plan=intake_plan,
        bundle=bundle, frozen_pair_count=frozen_pair_count, provenance=provenance)

    # 6) R1 gap(게이트 production_gold_count exact passthrough + canonical floor 재사용·_r1_status).
    prod = gate["production_gold_count"]
    returned_label_count = gate["returned_label_count"]
    r1_status = _r1_status(
        returned_label_count=returned_label_count, production_gold_count=prod,
        calibration_ready=gate["calibration_ready"])
    current_r1_gap = max(0, REQUIRED_PRODUCTION_GOLD - prod)

    # operator next actions(launch 한 줄 + 합성 provenance caveat + 게이트 next_action 묶음).
    primary_next_action = _LAUNCH_NEXT_ACTION[launch_status]
    # 합성 batch hard-stop(adversarial MEDIUM-1): production gold 수집 금지를 **맨 앞**에 둬 실 reviewer 노력을
    # fixture 라벨링에 낭비하거나 gold 를 오염시키지 않게 한다(HIGH-1 의 template synthetic 태깅과 함께 이중 방어).
    provenance_caveat = (
        "SYNTHETIC FIXTURE pilot — use only to validate the labeling process (dry-run); do NOT collect production "
        "gold from it (returned labels are tagged dataset_source=synthetic and cannot become production gold); "
        "acquire real candidate pairs from live source overlap AND real reviewer labels before production labeling")
    next_actions: list[str] = []
    if provenance == PROVENANCE_SYNTHETIC_FIXTURE:
        next_actions.append(provenance_caveat)   # hard-stop 맨 앞.
    next_actions.append(primary_next_action)
    next_actions.extend(gate["next_actions"])
    next_actions = list(dict.fromkeys(next_actions))

    block_reasons: list[str] = []
    if not batch_frozen:
        block_reasons.append("no_candidate_pairs")
    if provenance == PROVENANCE_SYNTHETIC_FIXTURE:
        block_reasons.append("synthetic_fixture_only_no_production_candidates")
    if r1_status == "blocked_no_labels":
        block_reasons.append("r1_blocked_no_actual_returned_labels")
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
        "gold_provenance_verified": False,   # production gold 무결성 선언 기반(미검증) — readiness 근거 인용 금지.
    }

    # internal ops API/UI 화이트리스트 contract(sanitized·forbidden 필드 없음·public truth 아님).
    r1_pilot_batch_contract = {
        "contract": "InternalOpsR1PilotBatchStatus",
        "pilot_batch_id": batch_id,
        "batch_frozen": batch_frozen,
        "batch_signature": batch_signature,
        "candidate_provenance": provenance,
        "pilot_batch_is_production_candidate": False,   # 합성 fixture — production 후보 둔갑 0.
        "frozen_pair_count": frozen_pair_count,
        "target_pair_count": target_pair_count,
        "expected_label_file_count": len(intake_plan["expected_label_files"]),
        "launch_status": launch_status,
        "ready_for_manual_launch": ready_for_manual_launch,
        "returned_labels_found": gate["actual_returned_labels_found"],
        "returned_label_count": returned_label_count,
        "intake_directory": gate["input_directory"],
        "validation_command": intake_plan["validation_command"],
        "r1_status": r1_status,
        "production_gold_count": prod,
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_r1_gap": current_r1_gap,
        "r2_r7_no_go": True,
        "next_manual_action": primary_next_action,
        "flags": dict(flags),
    }

    result = {
        "operation_name": OPERATION_NAME,
        "batch_id": batch_id,
        # §A actual input 재확인(단일 출처 게이트 passthrough).
        "actual_input_rechecked": True,
        "actual_contact_evidence_found": gate["actual_contact_evidence_found"],
        "actual_returned_labels_found": gate["actual_returned_labels_found"],
        "actual_input_status": gate["actual_input_status"],
        "external_input_required": gate["external_input_required"],
        "r1_status": r1_status,
        # §B frozen pilot batch(동결·deterministic signature·provenance 정직).
        "pilot_batch_id": batch_id,
        "batch_frozen": batch_frozen,
        "batch_signature": batch_signature,
        "candidate_provenance": provenance,
        "pilot_batch_is_production_candidate": False,
        "frozen_label_dataset_source": SOURCE_SYNTHETIC,   # template 태그=synthetic → 회수 라벨 production gold 미승격(machinery 강제·HIGH-1).
        "frozen_pair_count": frozen_pair_count,
        "target_pair_count": target_pair_count,
        "frozen_pairs": frozen_pairs,
        "expected_reviewer_count": manifest["reviewer_count_assigned"],
        "reviewer_count_required": DEFAULT_REVIEWERS_PER_PAIR,
        "expected_label_file_count": len(intake_plan["expected_label_files"]),
        "expected_label_files": list(intake_plan["expected_label_files"]),
        "intake_directory": gate["input_directory"],
        "validation_command": intake_plan["validation_command"],
        # §C operator launch package(전송 0·생성 0).
        "reviewer_instruction_ready": bool(instruction) and "label_vocabulary" in instruction,
        "label_template_ready": bool(template),
        "placement_guide_ready": True,
        "operator_launch_checklist_ready": bool(checklist["steps"]),
        "operator_launch_checklist": checklist,
        "handoff_bundle": bundle,
        "ready_for_manual_launch": ready_for_manual_launch,
        "launch_status": launch_status,
        # §B returned-label / R1 gap(게이트 exact passthrough + canonical floor).
        "returned_labels_found": gate["actual_returned_labels_found"],
        "returned_label_count": returned_label_count,
        "production_gold_count": prod,
        "synthetic_gold_count": gate["synthetic_gold_count"],
        "required_production_gold_count": REQUIRED_PRODUCTION_GOLD,
        "current_r1_gap": current_r1_gap,
        "calibration_ready": gate["calibration_ready"],
        "merge_gate_ready": gate["merge_gate_ready"],
        "r2_r7_no_go": True,
        # public/PII/merge 경계(정직·constant + 게이트 파생).
        "public_truth_exposed": False,
        "same_event_truth_exposed": False,
        "score_exposed": gate["score_exposed"],
        "rationale_exposed": gate["rationale_exposed"],
        "predicted_status_exposed": gate["predicted_status_exposed"],
        "raw_pii_exposed": gate["raw_pii_exposed"],
        "raw_source_body_exposed": False,
        "no_public_intelligence_unit": gate["no_public_intelligence_unit"],
        "merge_allowed": gate["merge_allowed"],
        "db_write": gate["db_write"],
        "llm_invoked": gate["llm_invoked"],
        "embedding_invoked": gate["embedding_invoked"],
        "actual_sending_performed": False,
        # internal ops API/UI 화이트리스트 contract.
        "r1_pilot_batch_contract": r1_pilot_batch_contract,
        "block_reasons": block_reasons,
        "next_actions": next_actions,
    }
    # 전체 출력 재귀 forbidden-key 가드(score/rationale/predicted_status/raw PII/secret 어떤 depth 도 0·미래 드리프트 fail-loud).
    _assert_pii_safe(result, _path="r1_reviewer_pilot_batch_output")
    return result


# ── CLI(실 입력 디렉터리 스캔·network 0·DB 0·전송 0·secret read 0; 합성 fixture freeze·production 둔갑 0) ────
def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description="R1 first reviewer pilot batch freeze + operator launch handoff "
                    "(ADR#75·병합 0·LLM 0·embedding 0·DB 0·전송 0).")
    parser.add_argument("--batch-id", default="reviewer_pilot_exec_001", help="actual input 재확인·freeze batch id.")
    parser.add_argument("--input-dir", metavar="DIR", help="실 입력 디렉터리(미지정 시 canonical). 코드가 생성하지 않음.")
    parser.add_argument("--as-of", metavar="ISO_DATE", help="overdue 산정 기준일(ISO).")
    parser.add_argument("--json", action="store_true", help="전체 output JSON 출력.")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_r1_reviewer_pilot_batch(directory=ns.input_dir, batch_id=ns.batch_id, as_of=ns.as_of)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
        return 0
    print(f"- operation: {out['operation_name']} batch_id={out['batch_id']}")
    print(f"- actual_input: rechecked={out['actual_input_rechecked']} status={out['actual_input_status']} "
          f"external_input_required={out['external_input_required']} r1_status={out['r1_status']}")
    print(f"- frozen_batch: frozen={out['batch_frozen']} provenance={out['candidate_provenance']} "
          f"production_candidate={out['pilot_batch_is_production_candidate']} "
          f"pairs={out['frozen_pair_count']}/{out['target_pair_count']} signature={out['batch_signature'][:23]}...")
    print(f"- launch: status={out['launch_status']} ready_for_manual={out['ready_for_manual_launch']} "
          f"returned_labels_found={out['returned_labels_found']} returned={out['returned_label_count']}")
    print(f"- package: instruction={out['reviewer_instruction_ready']} template={out['label_template_ready']} "
          f"placement={out['placement_guide_ready']} checklist={out['operator_launch_checklist_ready']} "
          f"expected_files={out['expected_label_file_count']}")
    print(f"- intake_dir: {out['intake_directory']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- r1_gap: production={out['production_gold_count']}/{out['required_production_gold_count']} "
          f"gap={out['current_r1_gap']} r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- gates: merge_allowed={out['merge_allowed']} public_truth_exposed={out['public_truth_exposed']} "
          f"actual_sending={out['actual_sending_performed']} db_write={out['db_write']} "
          f"llm_invoked={out['llm_invoked']} embedding_invoked={out['embedding_invoked']}")
    print(f"- next_action: {out['next_actions'][0] if out['next_actions'] else ''}")
    print(f"- block_reasons: {out['block_reasons']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
