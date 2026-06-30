"""ADR#95 §11 (option D) — real payload file template hardening (operator-fillable JSON 템플릿 강화·코드가 real 파일 생성 0).

문제(ADR#90/#91 진전 후 남은 결손): operator 가 `inputs/operator_events/operator_regulatory_event_payload.json`
(REAL_PAYLOAD_PATH·gitignored)에 직접 채워 넣을 JSON 의 **계약**(어떤 required 필드를 채워야 하는지, 어떤 forbidden
키[secret/PII/score]가 거부되는지, 어떤 boolean 이 default-false 인지, placeholder 가 무엇인지, 어떤 명령으로 검증하는지)
이 한 곳에 **강화된 형태로** 모여있지 않았다 — authoring helper 는 템플릿을 만들고, payload 모듈은 forbidden 키를
거부하지만, operator-facing 한 장짜리 "hardening 계약"은 없었다.

이 모듈은 그 계약을 묶는 **template hardening** 이다(기존 단일 출처 합성·재구현 0):
  - required_fields(`OPERATOR_EVENT_REQUIRED_FIELDS` 12개)·forbidden_fields(`_PAYLOAD_FORBIDDEN_KEYS` 22개)·
    default_false_fields(operator_confirmed/live_approved)·placeholder 가 박힌 template_schema 를 노출하고,
  - 그 template_schema 가 **real(approved) payload 가 아님을 실제 검증으로 증명**한다
    (`validate_template_not_real_payload` → is_real_payload=False·can_trigger_live=False).

절대 불변(상속·상용 안전 계약):
  - **코드가 real payload 파일을 쓰지 않는다**(REAL_PAYLOAD_PATH 자동 author 0·disk write 0·template_schema 는 in-memory only).
  - **코드가 operator_confirmed/live_approved 를 true 로 설정하지 않는다**(template 은 강제 False·operator 가 수동으로만).
  - secret 값 노출 0 · network 0 · LLM/embedding 0 · DB 0 · 전송 0 · production gold 증가 0.
  - 출력 어떤 depth 도 forbidden 키(PII/secret/score) 0(`_assert_pii_safe` 재귀 가드·LAST before return).
  test: template_schema 의 operator_confirmed/live_approved=False·forbidden 키 스캔 거부·real 파일 미생성·proof is_real_payload=False.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from backend.app.tools.operator_payload_authoring_helper import (
    generate_operator_fillable_payload_template,
    validate_template_not_real_payload,
)
from backend.app.tools.operator_payload_sourcing_workflow import validation_command
from backend.app.tools.operator_regulatory_event_intake import OPERATOR_EVENT_REQUIRED_FIELDS
from backend.app.tools.operator_regulatory_event_payload import (
    _PAYLOAD_FORBIDDEN_KEYS,
    EXAMPLE_PAYLOAD_PATH,
    REAL_PAYLOAD_PATH,
)
from backend.app.tools.regulatory_event_seed_bank import build_regulatory_event_seed_bank
from backend.app.tools.reviewer_pilot_handoff import _assert_pii_safe

OPERATION_NAME = "real_payload_file_template_hardening"
CONTRACT_VERSION = "real_payload_file_template_hardening_v1"

# payload_template_hardening_status(단일 상태 — hardening 계약은 항상 산출 가능·default epa seed).
TEMPLATE_HARDENED = "payload_template_hardened"

# default-false boolean 후보. **실제 template_schema 에 있는 것만** 노출(operator_confirmed/live_approved 가 12-field
# schema 에 있음·same_event_asserted/event_occurrence_verified_by_code 는 schema 밖이라 제외됨).
_DEFAULT_FALSE_CANDIDATE_FIELDS: tuple[str, ...] = (
    "operator_confirmed", "live_approved", "same_event_asserted", "event_occurrence_verified_by_code",
)


def scan_payload_for_forbidden_keys(payload: dict) -> list[str]:
    """payload 의 **모든 depth**(dict/list 재귀)에서 forbidden(secret/PII/score) 키를 탐지(키명만·값 미접근).

    `operator_regulatory_event_payload._scan_forbidden_keys` 를 미러링한다 — 테스트가 forbidden 필드가 거부됨을
    증명하는 데 쓴다(값은 매칭/노출에 쓰지 않으며 키 집합 ∩ _PAYLOAD_FORBIDDEN_KEYS 만 반환)."""
    found: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            found.update(set(obj) & _PAYLOAD_FORBIDDEN_KEYS)
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(payload)
    return sorted(found)


def _resolve_seed(seed_id: Optional[str]) -> Optional[dict]:
    """regulatory seed bank 에서 hardening 대상 seed 선택(기본 epa_final_rule_emissions·network 0·disk write 0)."""
    bank = build_regulatory_event_seed_bank(selected_seed_id=seed_id)
    if seed_id is not None:
        return next((s for s in bank["seed_bank"] if s.get("seed_id") == seed_id), None)
    return bank.get("selected_seed_for_next_live_run") or (
        bank["seed_bank"][0] if bank["seed_bank"] else None)


def _copy_instruction(required_field_count: int) -> str:
    """operator-facing 산문 — template 을 real path 로 복사·채우기·boolean 수동 설정·커밋 금지."""
    return (
        f"Copy the template_schema into a new JSON file at {REAL_PAYLOAD_PATH} (gitignored — never commit it), "
        f"fill the {required_field_count} required field(s), and set operator_confirmed=true and live_approved=true "
        f"MANUALLY only after you confirm the event actually occurred. This code never writes the real payload "
        f"file and never sets those booleans for you (code does not author the payload)."
    )


def build_real_payload_file_template_hardening(*, seed_id: Optional[str] = None) -> dict:
    """operator-fillable real payload JSON 의 hardening 계약 산출(required/forbidden/default-false/placeholder + 검증 명령).

    seed 미지정 시 regulatory seed bank 의 selected(기본 epa_final_rule_emissions)로 template_schema 를 생성하되
    operator_confirmed/live_approved 는 강제 False 다. real payload 파일을 쓰지 않으며(disk write 0·network 0)
    template_schema 는 in-memory only 다. template_schema 가 real(approved) payload 가 아님을 실제 검증으로 증명한다."""
    seed = _resolve_seed(seed_id) or {}
    template_schema = generate_operator_fillable_payload_template(seed)
    not_real = validate_template_not_real_payload(template_schema)

    forbidden_fields = sorted(_PAYLOAD_FORBIDDEN_KEYS)
    required_fields = list(OPERATOR_EVENT_REQUIRED_FIELDS)
    default_false_fields = [f for f in _DEFAULT_FALSE_CANDIDATE_FIELDS if f in template_schema]

    out = {
        "operation_name": OPERATION_NAME,
        "contract_version": CONTRACT_VERSION,
        "payload_template_hardening_status": TEMPLATE_HARDENED,
        # operator 가 채울 안전 template(secret/PII/score 없음·operator_confirmed/live_approved 강제 False·in-memory only).
        "template_schema": template_schema,
        # forbidden 키(secret/PII/score) — load 단계에서 fail-closed 거부되는 키(값 아님·키명 목록).
        "forbidden_fields": forbidden_fields,
        "forbidden_field_count": len(forbidden_fields),
        # required 필드(operator 가 채워야 valid).
        "required_fields": required_fields,
        "required_field_count": len(required_fields),
        # default-false boolean(코드가 true 로 설정하지 않음·schema 에 실제 존재하는 것만).
        "default_false_fields": default_false_fields,
        # paths(real↔example·real 은 gitignored·자동 쓰기 0).
        "real_payload_path": REAL_PAYLOAD_PATH,
        "example_payload_path": EXAMPLE_PAYLOAD_PATH,
        "copy_instruction": _copy_instruction(len(required_fields)),
        "validation_command": validation_command(REAL_PAYLOAD_PATH),
        # template 이 real(approved) payload 가 아님을 실제 §8 검증으로 증명(is_real_payload=False·can_trigger_live=False).
        "template_not_real_payload_proof": not_real,
        # ── 하드코딩 불변(정직·constant) ──
        "real_file_written": False,
        "code_sets_operator_confirmed_true": False,
        "code_sets_live_approved_true": False,
        "real_payload_path_gitignored": True,
        "secret_values_exposed": False,
        "network_invoked": False,
        "production_gold_count": 0,
    }
    _assert_pii_safe(out, _path="payload_template_hardening_output")
    return out


def sanitized_real_payload_file_template_hardening(out: dict) -> dict:
    """frontier/snapshot 용 aggregate-only 투영(template_schema 본문·명령 문자열 제외·status/count/flag 만)."""
    return {
        "payload_template_hardening_status": out["payload_template_hardening_status"],
        "contract_version": out["contract_version"],
        "required_field_count": out["required_field_count"],
        "forbidden_field_count": out["forbidden_field_count"],
        "default_false_field_count": len(out["default_false_fields"]),
        "real_file_written": out["real_file_written"],
        "real_payload_path_gitignored": out["real_payload_path_gitignored"],
        "template_can_trigger_live": bool(out["template_not_real_payload_proof"]["can_trigger_live"]),
        "secret_values_exposed": out["secret_values_exposed"],
        "network_invoked": out["network_invoked"],
        "production_gold_count": out["production_gold_count"],
    }


def main(argv: Optional[list[str]] = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(
        description=("ADR#95 §11 real payload file template hardening (operator-fillable JSON 템플릿 강화; "
                     "코드가 real payload 파일 생성 0·operator_confirmed/live_approved 자동 설정 0·network 0·secret 0)."))
    parser.add_argument("--seed-id", default=None,
                        help="hardening 대상 regulatory seed id(미지정 시 epa_final_rule_emissions).")
    parser.add_argument("--json", action="store_true", help="aggregate JSON 출력(template_schema 본문 제외).")
    ns = parser.parse_args(sys.argv[1:] if argv is None else argv)

    out = build_real_payload_file_template_hardening(seed_id=ns.seed_id)
    if ns.json:
        print(json.dumps(sanitized_real_payload_file_template_hardening(out), ensure_ascii=False, indent=2))
        return 0
    print(f"- operation: {out['operation_name']} version={out['contract_version']} "
          f"status={out['payload_template_hardening_status']}")
    print(f"- required_fields ({out['required_field_count']}): {', '.join(out['required_fields'])}")
    print(f"- forbidden_fields ({out['forbidden_field_count']}): {', '.join(out['forbidden_fields'])}")
    print(f"- default_false_fields: {', '.join(out['default_false_fields'])}")
    print(f"- real_payload_path: {out['real_payload_path']} (gitignored={out['real_payload_path_gitignored']})")
    print(f"- example_payload_path: {out['example_payload_path']}")
    print(f"- real_file_written={out['real_file_written']} network_invoked={out['network_invoked']} "
          f"production_gold_count={out['production_gold_count']}")
    print(f"- validation_command: {out['validation_command']}")
    print(f"- copy_instruction: {out['copy_instruction']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
