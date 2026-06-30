# REAL_PAYLOAD_FILE_TEMPLATE_HARDENING (ADR#95)

> Status: **TEMPLATE-HARDENING/OPERATOR-FACING · 코드가 real 파일 생성 0 · RUNTIME No-Go**. operator 가
> `inputs/operator_events/operator_regulatory_event_payload.json`(gitignored)에 직접 채워 넣을 JSON 의 **계약**을
> 한 장으로 강화한다 — required/forbidden/default-false/placeholder + 검증 명령. 코드:
> `backend/app/tools/real_payload_file_template_hardening.py` (disk write 0·network 0·secret 0).

## 0. 목적

authoring helper 는 템플릿을 만들고 payload 모듈은 forbidden 키를 거부하지만, operator-facing 한 장짜리 "hardening
계약"(어떤 required 필드를 채워야 하는지, 어떤 forbidden 키[secret/PII/score]가 거부되는지, 어떤 boolean 이
default-false 인지, 어떤 명령으로 검증하는지)이 한 곳에 모여 있지 않았다. 이 모듈은 기존 단일 출처를 합성(재구현 0)해
그 계약을 묶고, template_schema 가 **real(approved) payload 가 아님을 실제 §8 검증으로 증명**한다. **코드는 real
payload 파일을 절대 쓰지 않으며**(template_schema 는 in-memory only), operator_confirmed/live_approved 를 true 로
설정하지 않는다.

## 1. 진입점

```
build_real_payload_file_template_hardening(*, seed_id=None) -> dict
보조: scan_payload_for_forbidden_keys(payload) -> list[str]  # 모든 depth 재귀·키명만(값 미접근)
     sanitized_real_payload_file_template_hardening(out) · main(--seed-id / --json)
```

## 2. 상태 vocab (`payload_template_hardening_status`)

```
TEMPLATE_HARDENED = "payload_template_hardened"   # 단일 상태 — 계약은 항상 산출 가능(기본 epa seed)
```

`scan_payload_for_forbidden_keys` 는 입력 dict 의 키 집합 ∩ `_PAYLOAD_FORBIDDEN_KEYS` 만 정렬 반환한다(값 노출 0·
테스트가 forbidden 필드 거부 증명에 사용).

## 3. 핵심 출력 필드

```
payload_template_hardening_status · template_schema
forbidden_fields · forbidden_field_count(22) · required_fields · required_field_count(12) · default_false_fields
real_payload_path · example_payload_path · copy_instruction · validation_command · template_not_real_payload_proof
```

- `required_field_count=12`(`OPERATOR_EVENT_REQUIRED_FIELDS`) · `forbidden_field_count=22`(`_PAYLOAD_FORBIDDEN_KEYS`) ·
  `default_false_fields=[operator_confirmed, live_approved]`(schema 에 실제 존재하는 것만).
- `template_not_real_payload_proof` 가 is_real_payload=False·can_trigger_live=False 를 실제 검증으로 증명 ·
  `real_payload_path` 는 gitignored 문자열일 뿐 파일 생성 0.

## 4. 불변식 (절대 금지·코드가 real 파일 안 씀)

```
real_file_written=False · code_sets_operator_confirmed_true=False · code_sets_live_approved_true=False
real_payload_path_gitignored=True · secret_values_exposed=False · network_invoked=False · production_gold_count=0
```

- template 의 operator_confirmed/live_approved 는 강제 False — operator 가 발생 확인 후 **수동으로만** true · 명령은 전부
  문자열(실행 0) · `_assert_pii_safe` 가 반환 직전 모든 depth 의 forbidden 키 0 을 보장.
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈 (import·재구현 0)

- `operator_payload_authoring_helper` (`generate_operator_fillable_payload_template`·`validate_template_not_real_payload`).
- `operator_payload_sourcing_workflow.validation_command` · `operator_regulatory_event_intake.OPERATOR_EVENT_REQUIRED_FIELDS`.
- `operator_regulatory_event_payload` (`_PAYLOAD_FORBIDDEN_KEYS`·`REAL_PAYLOAD_PATH`·`EXAMPLE_PAYLOAD_PATH`) ·
  `regulatory_event_seed_bank` · `reviewer_pilot_handoff._assert_pii_safe`.
- 테스트: `backend/tests/test_real_payload_file_template_hardening.py` — 15개(전부 통과).

## 6. 이것이 아니다

- real(approved) payload 가 **아니다** · 코드가 real 파일을 디스크에 쓰지 않는다(template_schema 는 in-memory only).
- 코드가 operator_confirmed/live_approved 를 true 로 설정하지 않는다 · secret 값을 노출하지 않는다.
- merge 0 · 전송 0 · network 0 · production gold 0 — operator 가 직접 채우고 검증해야 real payload 가 된다.

Status: ADR#95 · runtime 0
