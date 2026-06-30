"""ADR#90 — operator payload authoring helper (curated seed → operator-fillable payload 템플릿·코드가 real event fabricate 0).

문제(ADR#89 실측·R-OperatorConfirmedEventScarcity): operator real payload 가 없으면 live 가 blocked 되는데, ADR#88/#89
gate 는 payload 를 **검증**만 하고(`operator_event_not_provided`), operator 가 **무엇을 어떤 모양으로 채워 둘지** 를
보여주지 않았다 — example 1개만으로는 부족하고, curated regulatory seed 는 operator-payload 와 **스키마가 다르다**
(seed: agency/entity/official_query…, payload: agency_or_entity/operator_confirmed/live_approved…).

이 모듈은 그 간극을 줄이는 **authoring helper** 다 — curated regulatory seed 를 **operator-fillable payload 템플릿**으로
변환한다. 핵심 정직성(상속·§9):
  - **코드가 event 를 fabricate 하지 않는다**: agency_or_entity/action/window/query 는 seed 에서 가져오되,
    `operator_confirmed=False`·`live_approved=False` 를 **강제**하고 confirmed_by/confirmed_at 는 placeholder 로 둔다 —
    operator 가 실제 발생을 확인하고 채울 때까지 템플릿은 **live 를 트리거할 수 없다**(gate 가 차단).
  - **real payload 경로에 자동 쓰기 0**: template_path(draft·gitignored outputs/)는 REAL_PAYLOAD_PATH 와 **다르다**.
    helper 는 디스크에 쓰지 않고(network 0·disk write 0) in-memory 템플릿 + 채워야 할 필드 체크리스트만 산출한다.
  - **example ≠ real**: 생성 템플릿은 example dummy 와 같은 "미확인" 성질(operator_confirmed=false)을 가지며 real event 단정 0.
  - same_event 단정 0 · network 0 · merge 0 · secret 0 · 전송 0.
  test: 생성 템플릿 operator_confirmed=false·live_approved=false·template path≠real path·gate 통과 불가(live 트리거 0).
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_regulatory_event_payload import (
    REAL_PAYLOAD_PATH,
    is_example_payload,
    validate_operator_regulatory_event_payload,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "operator_payload_authoring_helper"

# draft 템플릿 저장 권장 위치(gitignored outputs/·real payload 경로 아님). helper 는 기본 쓰지 않는다.
DRAFT_DIR = "outputs/operator_payload_drafts"

# operator 가 채워야만 valid+approved 되는 placeholder(강제 미충족).
_CONFIRMED_BY_PLACEHOLDER = "OPERATOR_NAME_OR_ROLE"
_CONFIRMED_AT_PLACEHOLDER = "YYYY-MM-DD"
_DATE_PLACEHOLDER = "YYYY-MM-DD"
_AGENCY_PLACEHOLDER = "NAMED_AGENCY_OR_ENTITY"

# authoring status(operator-facing).
AUTHORING_TEMPLATE_READY = "operator_payload_template_ready"
AUTHORING_NO_SEED = "no_authorable_regulatory_seed"


def _is_seed_placeholder(text: object) -> bool:
    """seed 값이 operator 가 채워야 하는 placeholder(<…> / 'operator fills')인가."""
    s = str(text or "")
    return "<" in s or "operator fills" in s.lower()


def draft_template_path(seed_id: Optional[str]) -> str:
    """draft 저장 권장 경로(gitignored outputs/·REAL_PAYLOAD_PATH 와 다름)."""
    sid = seed_id or "operator_seed"
    return f"{DRAFT_DIR}/{sid}__operator_payload.draft.json"


def generate_operator_fillable_payload_template(seed: dict) -> dict:
    """curated regulatory seed → operator-fillable operator-payload 템플릿(operator_confirmed=False·live_approved=False 강제).

    코드가 event 를 fabricate 하지 않는다 — agency_or_entity/action/window/query 는 seed 에서 가져오되(수집 의도),
    confirmed_by/confirmed_at 는 placeholder 로 두고 operator_confirmed/live_approved 는 False 로 강제한다. 따라서
    템플릿은 그대로는 gate 를 통과하지 못한다(live 트리거 0). seed entity 가 placeholder('operator fills …')면
    agency 를 쓰되 named subject 지정을 missing_fields 가 요구한다."""
    agency = str(seed.get("agency") or "").strip()
    entity = str(seed.get("entity") or "").strip()
    # agency_or_entity: named agency 우선, 없으면 named entity, 둘 다 placeholder/공백이면 placeholder 노출.
    if agency and not _is_seed_placeholder(agency):
        agency_or_entity = agency
    elif entity and not _is_seed_placeholder(entity):
        agency_or_entity = entity
    else:
        agency_or_entity = _AGENCY_PLACEHOLDER
    return {
        "seed_id": seed.get("seed_id"),
        "operator_confirmed": False,                       # 강제 — operator 가 발생 확인 후 true.
        "confirmed_by": _CONFIRMED_BY_PLACEHOLDER,         # operator 가 채움.
        "confirmed_at": _CONFIRMED_AT_PLACEHOLDER,         # operator 가 채움.
        "agency_or_entity": agency_or_entity,
        "action_phrase": str(seed.get("action_phrase") or "SPECIFIC_REGULATORY_ACTION"),
        "date_window_start": str(seed.get("date_window_start") or _DATE_PLACEHOLDER),
        "date_window_end": str(seed.get("date_window_end") or _DATE_PLACEHOLDER),
        "official_query": str(seed.get("official_query") or "FEDERAL_REGISTER_QUERY"),
        "news_query": str(seed.get("news_query") or "NEWS_QUERY"),
        "expected_news_angle": str(seed.get("expected_news_angle") or "WHY_NEWS_SHOULD_COVER_THIS"),
        "live_approved": False,                            # 강제 — operator 가 승인 시 true.
    }


def emit_missing_fields_checklist(template: dict, seed: Optional[dict] = None) -> list[str]:
    """template 이 valid+approved(live 가능) 되려면 operator 가 채워야 할 필드 목록(결정론·operator-facing)."""
    missing: list[str] = []
    if template.get("operator_confirmed") is not True:
        missing.append("operator_confirmed (set true ONLY after confirming the event actually occurred)")
    if template.get("confirmed_by") in (None, "", _CONFIRMED_BY_PLACEHOLDER):
        missing.append("confirmed_by (operator name or role)")
    if template.get("confirmed_at") in (None, "", _CONFIRMED_AT_PLACEHOLDER):
        missing.append("confirmed_at (ISO date when you confirmed the event)")
    if template.get("live_approved") is not True:
        missing.append("live_approved (set true to approve a bounded official×news live run)")
    ae = str(template.get("agency_or_entity") or "")
    if not ae or _is_seed_placeholder(ae) or ae == _AGENCY_PLACEHOLDER:
        missing.append("agency_or_entity (replace the placeholder with the named agency/entity)")
    elif seed is not None and (_is_seed_placeholder(seed.get("entity")) or _is_seed_placeholder(seed.get("agency"))):
        # seed entity 가 'operator fills named respondent/target/product' → named subject 지정 필요(같은 subject 겹침).
        missing.append("agency_or_entity (the seed leaves the specific respondent/target/product unspecified — name it)")
    # code-proposed window 는 발생 미검증 — operator 가 실제 발생 window 로 확인/대체해야 한다.
    missing.append("verify date_window_start/date_window_end are the ACTUAL occurrence window (code-proposed, unverified)")
    return missing


def validate_template_not_real_payload(template: dict) -> dict:
    """생성 템플릿이 real(approved) payload 로 오인되지 않음을 증명(operator_confirmed≠true ∨ live_approved≠true → live 불가).

    추가로 §8 검증을 실제로 돌려(`validate_operator_regulatory_event_payload`) 템플릿이 현재 **gate 를 통과하지 못함**을
    보인다(operator_confirmed=false → not accepted). 이는 '생성 템플릿이 live 를 트리거할 수 없다'의 직접 증거다."""
    operator_confirmed = template.get("operator_confirmed") is True
    live_approved = template.get("live_approved") is True
    validation = validate_operator_regulatory_event_payload(template)
    can_trigger_live = bool(operator_confirmed and live_approved and validation.get("accepted"))
    reasons_not_real: list[str] = []
    if not operator_confirmed:
        reasons_not_real.append("operator_confirmed is false")
    if not live_approved:
        reasons_not_real.append("live_approved is false")
    if not validation.get("accepted"):
        reasons_not_real.append("payload validation not accepted (operator must fill required fields)")
    return {
        "is_real_payload": False,
        "operator_confirmed": operator_confirmed,
        "live_approved": live_approved,
        "validation_accepted": bool(validation.get("accepted")),
        "can_trigger_live": can_trigger_live,
        "reasons_not_real": reasons_not_real,
    }


def emit_operator_next_action(template: dict, missing_fields: list[str], *, seed_id: Optional[str]) -> str:
    """operator 가 다음에 할 일 한 줄(템플릿 채워 real path 에 저장 → live 승인)."""
    return (
        f"fill the {len(missing_fields)} missing field(s) in the template (confirm the event actually occurred, set "
        f"operator_confirmed=true and live_approved=true, name the agency/entity, and verify the real occurrence "
        f"window), then save it to {REAL_PAYLOAD_PATH} (gitignored) — the curated seed {seed_id!r} is a collection "
        f"SHAPE, not a confirmed event; code does not fabricate the event")


def build_operator_payload_authoring(
    *, seed: Optional[dict] = None, seed_id: Optional[str] = None,
) -> dict:
    """curated regulatory seed → operator-fillable payload 템플릿 + 채울 필드 체크리스트 + next action(network 0·disk write 0).

    seed 미지정 시 regulatory seed bank 의 selected(live-eligible) seed 를 쓰고, seed_id 지정 시 그 seed 를 고른다. 코드가
    real event 를 만들지 않으며(operator_confirmed/live_approved 강제 False) real payload 경로에 자동 쓰지 않는다(template_path
    는 draft·REAL_PAYLOAD_PATH 와 다름). raw payload 본문은 forbidden-key 가드를 통과하는 안전 필드만 담는다."""
    bank = build_regulatory_event_seed_bank(selected_seed_id=seed_id)
    # authoring 대상은 **모든 curated shape** 다 — placeholder/미완성 seed(sec/fda/ofac, date 미기재)야말로 operator 가
    # 채워야 할 주 대상이므로 accepted 로 필터하지 않는다(미완성도 fillable 템플릿으로 변환·missing_fields 가 결손 표면화).
    available_seed_ids = [s["seed_id"] for s in bank["seed_bank"]]
    if seed is None:
        if seed_id is not None:
            seed = next((s for s in bank["seed_bank"] if s.get("seed_id") == seed_id), None)
        else:
            seed = bank.get("selected_seed_for_next_live_run") or (
                bank["seed_bank"][0] if bank["seed_bank"] else None)
    if not isinstance(seed, dict):
        out = {
            "operation_name": OPERATION_NAME,
            "authoring_status": AUTHORING_NO_SEED,
            "payload_template_ready": False,
            "template_path": draft_template_path(seed_id),
            "template_path_equals_real_payload_path": False,
            "real_payload_path": REAL_PAYLOAD_PATH,
            "operator_action_required": True,
            "missing_fields": ["select an authorable regulatory seed (none available/eligible)"],
            "example_is_real_payload": False,
            "operator_confirmed": False,
            "live_approved": False,
            "can_trigger_live": False,
            "code_fabricated_confirmed_event": False,
            "available_seed_ids": available_seed_ids,
            "next_action": ("no authorable regulatory seed is available — specify a named regulatory event "
                            "(agency/entity + action + ISO date window) before authoring a payload"),
            "payload_template": None,
        }
        _assert_pii_safe(out, _path="operator_payload_authoring_no_seed")
        return out

    template = generate_operator_fillable_payload_template(seed)
    missing_fields = emit_missing_fields_checklist(template, seed)
    not_real = validate_template_not_real_payload(template)
    tpath = draft_template_path(template.get("seed_id"))
    out = {
        "operation_name": OPERATION_NAME,
        "authoring_status": AUTHORING_TEMPLATE_READY,
        "payload_template_ready": True,
        "template_path": tpath,
        # 핵심 안전 — draft 경로는 real payload 경로와 다르다(자동 쓰기 0).
        "template_path_equals_real_payload_path": tpath == REAL_PAYLOAD_PATH,
        "real_payload_path": REAL_PAYLOAD_PATH,
        "operator_action_required": True,
        "missing_fields": missing_fields,
        "missing_field_count": len(missing_fields),
        # 생성 템플릿은 미확인(example 과 같은 성질)·real event 단정 0.
        "example_is_real_payload": False,
        "template_is_example_shaped": is_example_payload(template),
        "operator_confirmed": bool(template.get("operator_confirmed")),
        "live_approved": bool(template.get("live_approved")),
        "can_trigger_live": not_real["can_trigger_live"],
        "validation_accepted": not_real["validation_accepted"],
        "code_fabricated_confirmed_event": False,
        "available_seed_ids": available_seed_ids,
        "selected_seed_id": template.get("seed_id"),
        "next_action": emit_operator_next_action(template, missing_fields, seed_id=template.get("seed_id")),
        # operator 가 채워 저장할 안전 템플릿(secret/PII/score 없음·forbidden-key 가드 통과).
        "payload_template": template,
    }
    _assert_pii_safe(out, _path="operator_payload_authoring_output")
    return out


def sanitized_operator_payload_authoring(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(template 본문 제외·status/count/next_action 만)."""
    return {
        "authoring_status": out["authoring_status"],
        "payload_template_ready": out["payload_template_ready"],
        "template_path_equals_real_payload_path": out["template_path_equals_real_payload_path"],
        "operator_action_required": out["operator_action_required"],
        "missing_field_count": int(out.get("missing_field_count") or len(out.get("missing_fields") or [])),
        "can_trigger_live": out["can_trigger_live"],
        "next_action": out["next_action"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#90 operator payload authoring helper (curated seed → operator-fillable payload 템플릿; "
                     "operator_confirmed/live_approved 강제 False·real path 자동 쓰기 0·network 0·코드가 event fabricate 0)."))
    parser.add_argument("--seed-id", default=None, help="authoring 할 regulatory seed id(미지정 시 bank 의 selected).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(template 본문 제외).")
    parser.add_argument("--print-template", action="store_true",
                        help="operator 가 채울 payload 템플릿 JSON 을 출력(stdout·디스크 미저장).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_operator_payload_authoring(seed_id=ns.seed_id)
    if ns.print_template:
        print(json.dumps(out.get("payload_template"), ensure_ascii=False, indent=2))
        return 0
    if ns.json:
        print(json.dumps(sanitized_operator_payload_authoring(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} status={out['authoring_status']} "
          f"template_ready={out['payload_template_ready']}")
    print(f"- template_path: {out['template_path']} (== real path: {out['template_path_equals_real_payload_path']})")
    print(f"- real_payload_path: {out['real_payload_path']}")
    print(f"- operator_confirmed={out['operator_confirmed']} live_approved={out['live_approved']} "
          f"can_trigger_live={out['can_trigger_live']}")
    print(f"- missing_fields ({out.get('missing_field_count', 0)}):")
    for m in out.get("missing_fields") or []:
        print(f"    - {m}")
    print(f"- next_action: {out['next_action']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
