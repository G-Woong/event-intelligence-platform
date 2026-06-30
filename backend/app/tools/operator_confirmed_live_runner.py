"""ADR#90 — operator-confirmed live runner (real payload → load → validate → live → classify; execution-ready·재구현 0).

문제(§10): operator 가 real payload 를 drop 했을 때 *한 번의 호출* 로 load(forbidden-key 재귀 scan)→§8 validate→
(valid∧approved 이면)official×news live→no-yield taxonomy 분류→returned-label dropbox readiness 까지 이어지는
**실행 경로** 가 흩어져 있었다(entrypoint·gate·engine·taxonomy·dropbox 가 따로). 이 모듈은 그 경로를 묶는 thin runner 다.

재구현 0(orchestrator only):
  - load+gate+live: `operator_regulatory_event_payload.resolve_operator_payload_entrypoint`(load→intake gate→engine).
    intake gate 가 confirmation_valid ∧ live_approved 일 때만 engine 을 호출(아니면 정직 block). raw payload 본문 미노출.
  - classify: `live_no_yield_taxonomy.build_live_no_yield_taxonomy`(payload-stage + engine status → 세분 taxonomy).
  - dropbox: `returned_label_dropbox_readiness.build_returned_label_dropbox_readiness`(batch-specific·실 returned label 0).
  - reviewer_contact_checklist_ready = reviewer_handoff_ready(freeze) ∧ label_dropbox_ready(launch checklist 와 동형).

이번 턴 현실: real payload absent → operator_payload_status=not_provided·operator_event_status=not_provided·live 미실행·
freeze 0·taxonomy=missing_payload·reviewer_contact_checklist_ready=False. fake acquisition_fn 주입 시 경로를 결정론 검증.

절대 불변: operator 확인 없이 live 0 · example/secret/PII payload fail-closed · same_event 단정 0 · actual sending 0 ·
merge 0 · production gold 0(returned labels 전) · raw payload/secret/score/PII 미노출(`_assert_pii_safe` 재귀 가드).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Callable, Optional

from backend.app.tools.live_no_yield_taxonomy import build_live_no_yield_taxonomy
from backend.app.tools.operator_regulatory_event_payload import resolve_operator_payload_entrypoint
from backend.app.tools.returned_label_dropbox_readiness import (
    build_returned_label_dropbox_readiness,
)
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_confirmed_live_runner"
DEFAULT_BATCH_ID = "operator_regulatory_live"


def run_operator_confirmed_live(
    path: Optional[str] = None, *, batch_id: str = DEFAULT_BATCH_ID,
    acquisition_fn: Optional[Callable[..., dict]] = None, today: Optional[str] = None,
    dropbox_scan_fn: Optional[Callable[..., dict]] = None, **acquisition_kwargs: Any,
) -> dict:
    """real payload(gitignored) → load→§8 gate→(valid∧approved이면)live→no-yield 분류→dropbox readiness 를 한 번에.

    real payload 없으면 not_provided 로 정직 산출(network 0). example/secret/PII payload 는 fail-closed(live 0).
    valid ∧ live_approved 일 때만 gate 가 engine 을 호출한다(이 모듈은 재구현 0). acquisition_fn/transports/scan_fn 은
    결정론 테스트용. raw payload 본문/secret/score/PII 는 출력에 재임베드하지 않는다(status/count/taxonomy 만)."""
    entry = resolve_operator_payload_entrypoint(
        path, acquisition_fn=acquisition_fn, today=today, **acquisition_kwargs)
    intake = entry.get("operator_intake_result") or {}
    taxonomy = build_live_no_yield_taxonomy(intake, payload_entrypoint_out=entry)
    dropbox = build_returned_label_dropbox_readiness(batch_id=batch_id, scan_fn=dropbox_scan_fn)

    handoff_ready = bool(intake.get("reviewer_handoff_ready"))
    dropbox_ready = bool(dropbox.get("label_dropbox_ready"))
    # launch checklist 와 동형: freeze(handoff) ∧ dropbox 일 때만 ready(readiness ≠ actual sending).
    checklist_ready = bool(handoff_ready and dropbox_ready)
    current = taxonomy["current"]

    out = {
        "operation_name": OPERATION_NAME,
        # ── payload 경계(real↔example·gitignored·코드 생성 0) ──
        "operator_payload_status": entry["operator_payload_status"],
        "operator_payload_path_status": entry["operator_payload_path_status"],
        "real_payload_gitignored": entry["real_payload_gitignored"],
        "payload_is_example_dummy": entry["payload_is_example_dummy"],
        "payload_forbidden_keys_count": int(entry.get("payload_forbidden_keys_count") or 0),
        "code_generated_payload": entry["code_generated_payload"],
        # ── intake gate(operator 확인 게이트·truth 아님) ──
        "operator_event_status": intake.get("operator_event_status") or "not_provided",
        "operator_confirmed": bool(intake.get("operator_confirmed")),
        "confirmation_valid": bool(intake.get("confirmation_valid")),
        "confirmation_blocked_reason": intake.get("confirmation_blocked_reason") or "",
        "seed_provenance": intake.get("seed_provenance") or "code_proposed_regulatory_shape",
        "live_query_executed": bool(intake.get("live_query_executed")),
        # ── official/news/bridge counts(intake passthrough·aggregate·title/url 0) ──
        "official_records_count": int(intake.get("official_records_count") or 0),
        "news_records_count": int(intake.get("news_records_count") or 0),
        "bridge_candidate_count": int(intake.get("bridge_candidate_count") or 0),
        "freeze_eligible_count": int(intake.get("freeze_eligible_count") or 0),
        "production_candidate_status": intake.get("production_candidate_status") or "blocked",
        "production_candidate_batch_ready": bool(intake.get("production_candidate_batch_ready")),
        "production_frozen_pair_count": int(intake.get("production_frozen_pair_count") or 0),
        "reviewer_handoff_ready": handoff_ready,
        # ── no-yield taxonomy(세분 분류·진단) ──
        "live_no_yield_taxonomy_status": taxonomy["live_no_yield_taxonomy_status"],
        "live_run_yielded": bool(taxonomy["is_yield"]),
        "live_no_yield_stage": current["stage"],
        "recommended_payload_adjustment": current["recommended_payload_adjustment"],
        "recommended_source_adjustment": current["recommended_source_adjustment"],
        # ── dropbox / contact checklist(batch-specific·readiness ≠ sending) ──
        "batch_id": batch_id,
        "label_dropbox_ready": dropbox_ready,
        "actual_returned_label_count": int(dropbox.get("actual_returned_label_count") or 0),
        "reviewer_contact_checklist_ready": checklist_ready,
        # ── R1 / gold(passthrough·gold 0 유지) ──
        "production_gold_count": int(intake.get("production_gold_count") or 0),
        # ── 불변 경계(정직·constant) ──
        "actual_sending_performed": False,
        "operator_confirmation_as_same_event_truth": False,
        "same_event_asserted": False,
        "merge_allowed": bool(intake.get("merge_allowed")),
        "public_iu_allowed": False,
        "r2_r7_no_go": True,
        "blocked_reason": intake.get("blocked_reason") or "",
        "next_action": current["next_action"],
    }
    _assert_pii_safe(out, _path="operator_confirmed_live_runner_output")
    return out


def sanitized_operator_confirmed_live(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(taxonomy 본문 외 status/count/flag 만)."""
    return {
        "operator_payload_status": out["operator_payload_status"],
        "operator_payload_path_status": out["operator_payload_path_status"],
        "operator_event_status": out["operator_event_status"],
        "live_query_executed": out["live_query_executed"],
        "official_records_count": out["official_records_count"],
        "news_records_count": out["news_records_count"],
        "bridge_candidate_count": out["bridge_candidate_count"],
        "freeze_eligible_count": out["freeze_eligible_count"],
        "production_candidate_status": out["production_candidate_status"],
        "live_no_yield_taxonomy_status": out["live_no_yield_taxonomy_status"],
        "reviewer_contact_checklist_ready": out["reviewer_contact_checklist_ready"],
        "label_dropbox_ready": out["label_dropbox_ready"],
        "actual_returned_label_count": out["actual_returned_label_count"],
        "blocked_reason": out["blocked_reason"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 operator-confirmed live runner (real payload → load→§8 gate→live→no-yield 분류; operator "
                     "확인 없이 live 0·example/secret/PII fail-closed·actual sending 0·merge 0·secret read 0)."))
    parser.add_argument("--event-json", metavar="PATH", default=None,
                        help="real operator payload JSON(미지정 시 기본 gitignored real path·없으면 not_provided).")
    parser.add_argument("--batch-id", default=DEFAULT_BATCH_ID, help="returned-label dropbox batch id.")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(taxonomy 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = run_operator_confirmed_live(ns.event_json, batch_id=ns.batch_id)
    if ns.json:
        print(json.dumps(sanitized_operator_confirmed_live(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']}")
    print(f"- payload: status={out['operator_payload_status']} path_status={out['operator_payload_path_status']} "
          f"is_example_dummy={out['payload_is_example_dummy']}")
    print(f"- operator_event: status={out['operator_event_status']} confirmed={out['operator_confirmed']} "
          f"provenance={out['seed_provenance']} live_executed={out['live_query_executed']}")
    print(f"- records: official={out['official_records_count']} news={out['news_records_count']} "
          f"bridge={out['bridge_candidate_count']} freeze_eligible={out['freeze_eligible_count']}")
    print(f"- taxonomy: status={out['live_no_yield_taxonomy_status']} yielded={out['live_run_yielded']} "
          f"stage={out['live_no_yield_stage']}")
    print(f"- contact/dropbox: checklist_ready={out['reviewer_contact_checklist_ready']} "
          f"dropbox_ready={out['label_dropbox_ready']} returned_labels={out['actual_returned_label_count']} "
          f"actual_sending={out['actual_sending_performed']}")
    print(f"- r1: production_gold={out['production_gold_count']} merge={out['merge_allowed']} "
          f"r2_r7_no_go={out['r2_r7_no_go']}")
    print(f"- blocked_reason: {out['blocked_reason'] or '(none)'}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
