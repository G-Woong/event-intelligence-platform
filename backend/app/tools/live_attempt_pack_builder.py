"""ADR#92 §9 — live attempt pack builder (operator 가 바로 채울 수 있는 live attempt 후보 묶음·코드가 event fabricate 0).

문제(ADR#91 실측·R-OperatorConfirmedEventScarcity 부분진전): sourcing workflow 는 *하나의* selected seed → 템플릿 +
운영 절차를 주지만, operator 가 "지금 어떤 regulatory event 후보들 중에서 골라 채워야 하는가" 를 한눈에 보여주지
않았다. real payload 가 아직 없을 때 operator 가 바로 검토·선택·채울 수 있는 **후보 묶음(live attempt pack)** 이 필요하다.

이 모듈은 curated regulatory seed bank → operator-fillable **candidate event shape** 리스트를 만든다(seed bank +
authoring helper 위 thin 합성·재구현 0). 핵심 정직성:
  - 코드가 event 발생을 단정하지 않는다(operator_must_verify_occurrence=True·event_occurrence_verified_by_code=False).
  - pack 후보는 live 를 트리거할 수 없다 — 각 후보의 underlying 템플릿은 operator_confirmed=False·live_approved=False
    (authoring helper 가 강제) 이며, pack 은 confirmed/approved 를 자동으로 쓰지 않는다.
  - real payload 경로에 자동 쓰기 0 · network 0 · disk read 0(frontier-safe·operator_confirmed_live_runner 미import).
  - same_event 단정 0 · merge 0 · secret/PII 0(`_assert_pii_safe` 재귀 가드).
  pack 은 real payload 가 아니다 — operator 가 후보를 골라 발생 확인 + confirmed/approved 설정 + drop 해야 live 가 된다.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_payload_authoring_helper import (
    generate_operator_fillable_payload_template,
)
from backend.app.tools.operator_payload_sourcing_workflow import (
    live_command,
    validation_command,
)
from backend.app.tools.operator_regulatory_event_payload import (
    PAYLOAD_PRESENT_VALID,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "live_attempt_pack_builder"

# deterministic pack id(batch 관례와 동형·Date/random 0).
ATTEMPT_PACK_ID = "operator_regulatory_live_attempt_pack"

# live_attempt_pack_status(operator-facing).
PACK_READY = "live_attempt_pack_ready_operator_fill_required"   # real 없음 → 후보 골라 채워 drop.
PACK_REAL_PRESENT = "real_payload_present_pack_optional"        # real 있음 → pack 불필요(검증/승인으로).
PACK_NO_CANDIDATES = "no_candidate_event_shapes_available"      # 후보 seed 없음.


def _source_strategy(seed: dict) -> str:
    """후보의 official×news 수집 전략 한 줄(provider constraints 가시화·role 분리 명시·operator-facing)."""
    official = str(seed.get("official_provider") or "federal_register")
    news = list(seed.get("news_providers") or ["guardian", "nyt"])
    return (
        f"official={official} (Federal Register window-honoring·publication_date[gte/lte]) × "
        f"news={'/'.join(news)} (enforce_window=True·out-of-window dropped) — "
        "official=authoritative evidence·news=public reporting·NOT same role·bridge=reviewer-routing only"
    )


def build_candidate_event_shape(seed: dict) -> dict:
    """curated regulatory seed → operator-fillable candidate event shape(§9·14필드).

    agency_or_entity/action/window/query/angle 는 authoring helper 템플릿에서 가져온다(operator_confirmed/live_approved
    강제 False 패턴 상속·재구현 0). operator_must_* 는 항상 True — 후보는 발생 미확인·confirmed/approved 미설정이며,
    operator 가 발생을 확인하고 confirmed/approved 를 설정해 채워야 live 가 된다. 코드가 event 를 단정하지 않는다."""
    template = generate_operator_fillable_payload_template(seed)
    return {
        "candidate_id": seed.get("seed_id"),
        "regulatory_domain": str(seed.get("regulatory_domain") or ""),
        "agency_or_entity": template["agency_or_entity"],
        "action_phrase": template["action_phrase"],
        "date_window_start": template["date_window_start"],
        "date_window_end": template["date_window_end"],
        "official_query_draft": template["official_query"],
        "news_query_draft": template["news_query"],
        "expected_news_angle": template["expected_news_angle"],
        "source_strategy": _source_strategy(seed),
        "risk_notes": str(seed.get("risk") or ""),
        # operator 가 반드시 할 일(코드가 대신 단정하지 않는다).
        "operator_must_verify_occurrence": True,
        "operator_must_set_confirmed": True,
        "operator_must_set_live_approved": True,
    }


def _pack_safety_notes() -> list[str]:
    """pack-facing 안전수칙(불변·계약·pack ≠ real payload)."""
    return [
        "A live attempt pack is a DRAFT set of candidate event shapes, not confirmed events.",
        "Code does not claim any candidate event occurred — you must verify the actual occurrence yourself.",
        "Each candidate keeps operator_confirmed=false and live_approved=false; a candidate cannot trigger a live run.",
        f"To proceed: pick a candidate, confirm it occurred, fill the payload, save it to {REAL_PAYLOAD_PATH} "
        "(gitignored), then approve and run the manual live command.",
        "Do not commit the real payload; do not put secrets/API keys/reviewer PII in it.",
        "official=authoritative evidence · news=public reporting — never merged into the same role; the bridge is "
        "reviewer-routing only.",
    ]


def _pack_next_action(status: str, candidate_count: int) -> str:
    """현재 pack 상태에서 operator 가 할 첫 행동 한 줄."""
    if status == PACK_READY:
        return (
            f"no real payload is present yet — pick one of the {candidate_count} candidate event shapes, confirm the "
            f"event actually occurred, fill the payload template, save it to {REAL_PAYLOAD_PATH} (gitignored), then "
            "validate (live_approved=false), set operator_confirmed=true ∧ live_approved=true, and run the manual live "
            "command"
        )
    if status == PACK_REAL_PRESENT:
        return (
            "a real payload is already present — validate and approve it (see the operator payload sourcing workflow) "
            "rather than starting from a new candidate"
        )
    return (
        "no candidate event shape is available — specify a named regulatory event "
        "(agency/entity + action + ISO date window) before authoring a payload"
    )


def build_live_attempt_pack(
    *, operator_payload_status: Optional[str] = None, selected_seed_id: Optional[str] = None,
) -> dict:
    """curated regulatory seeds → operator-fillable live attempt pack(후보 묶음 + 운영 명령 + 안전수칙·network 0·disk 0).

    operator_payload_status 는 주입(frontier-safe) — real payload 가 valid present 면 pack 은 optional(검증/승인으로 진행),
    아니면(미주입/미제공/무효) pack ready(operator 가 후보 골라 채움). 이 모듈은 real payload 를 읽지 않는다(disk read 0·
    present/absent 판정은 sourcing workflow 가 담당). 코드가 confirmed/approved 를 자동으로 쓰지 않으며 real path 에
    자동 기록하지 않는다(disk write 0). selected_seed_id 는 표면화용 — 모든 curated 후보를 묶되 선택을 기록한다."""
    bank = build_regulatory_event_seed_bank(selected_seed_id=selected_seed_id)
    seeds = bank["seed_bank"]
    shapes = [build_candidate_event_shape(s) for s in seeds]
    # 후보가 live 를 트리거할 수 없음을 underlying 템플릿으로 증명(operator_confirmed/live_approved 강제 False).
    templates = [generate_operator_fillable_payload_template(s) for s in seeds]
    all_confirmed_false = all(t["operator_confirmed"] is False for t in templates)
    all_approved_false = all(t["live_approved"] is False for t in templates)

    real_present = operator_payload_status == PAYLOAD_PRESENT_VALID
    if not shapes:
        status = PACK_NO_CANDIDATES
    elif real_present:
        status = PACK_REAL_PRESENT
    else:
        status = PACK_READY

    out = {
        "operation_name": OPERATION_NAME,
        "live_attempt_pack_status": status,
        "attempt_pack_id": ATTEMPT_PACK_ID,
        "candidate_count": len(shapes),
        "candidate_event_shapes": shapes,
        "operator_fill_required": status != PACK_REAL_PRESENT,
        "all_candidates_operator_confirmed_false": all_confirmed_false,
        "all_candidates_live_approved_false": all_approved_false,
        "selected_seed_id": bank.get("selected_seed_id"),
        "available_candidate_ids": [s["candidate_id"] for s in shapes],
        # paths + 운영 명령(수동·문서화만·실행하지 않는다).
        "real_payload_path": REAL_PAYLOAD_PATH,
        "real_payload_path_gitignored": True,
        "validation_command": validation_command(),
        "manual_live_command": live_command(),
        "live_command_is_manual_step": True,
        "safety_notes": _pack_safety_notes(),
        "next_action": _pack_next_action(status, len(shapes)),
        # ── 불변 경계(정직·constant) ──
        "code_writes_real_payload_path": False,
        "code_invokes_network": False,
        "code_reads_disk": False,
        "code_claims_event_occurred": False,
        "pack_candidates_can_trigger_live": False,
        "same_event_asserted": False,
        "event_occurrence_verified_by_code": False,
        "actual_sending_performed": False,
        "merge_allowed": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="live_attempt_pack_output")
    return out


def sanitized_live_attempt_pack(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(candidate 본문·명령·체크리스트 제외·status/flag/next_action 만)."""
    return {
        "live_attempt_pack_status": out["live_attempt_pack_status"],
        "candidate_count": out["candidate_count"],
        "operator_fill_required": out["operator_fill_required"],
        "all_candidates_operator_confirmed_false": out["all_candidates_operator_confirmed_false"],
        "all_candidates_live_approved_false": out["all_candidates_live_approved_false"],
        "pack_candidates_can_trigger_live": out["pack_candidates_can_trigger_live"],
        "live_attempt_pack_next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#92 live attempt pack builder (curated regulatory seeds → operator-fillable candidate event "
                     "shapes; 코드가 event fabricate 0·real path 자동 쓰기 0·후보 live 트리거 0·network 0·disk read 0)."))
    parser.add_argument("--seed-id", default=None, help="선택을 기록할 후보 seed id(미지정 시 bank 의 selected).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(candidate 본문 제외).")
    parser.add_argument("--print-candidates", action="store_true",
                        help="candidate event shape 리스트 JSON 출력(stdout·디스크 미저장).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_live_attempt_pack(selected_seed_id=ns.seed_id)
    if ns.print_candidates:
        print(json.dumps(out.get("candidate_event_shapes"), ensure_ascii=False, indent=2))
        return 0
    if ns.json:
        print(json.dumps(sanitized_live_attempt_pack(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['live_attempt_pack_status']} "
          f"candidate_count={out['candidate_count']}")
    print(f"- operator_fill_required={out['operator_fill_required']} "
          f"all_confirmed_false={out['all_candidates_operator_confirmed_false']} "
          f"all_approved_false={out['all_candidates_live_approved_false']} "
          f"can_trigger_live={out['pack_candidates_can_trigger_live']}")
    print(f"- real_payload_path: {out['real_payload_path']} (gitignored={out['real_payload_path_gitignored']})")
    print("- candidates:")
    for c in out["candidate_event_shapes"]:
        print(f"    {c['candidate_id']:<28} {c['agency_or_entity']} | {c['action_phrase']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- manual_live_command: {out['manual_live_command']}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
