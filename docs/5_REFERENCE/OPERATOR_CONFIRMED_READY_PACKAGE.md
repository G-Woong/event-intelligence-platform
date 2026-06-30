# OPERATOR_CONFIRMED_READY_PACKAGE (ADR#94)

> Status: **PRE-PAYLOAD/OPERATOR-FACING · NOT a real payload · RUNTIME No-Go**. operator 가 외부에서 직접 검증한 뒤
> REAL payload 로 옮길 준비 묶음(후보 요약·official/news query 초안·검증 체크리스트·real path·명령)을 한 곳에 담는다.
> 코드: `backend/app/tools/operator_confirmed_ready_package.py` (코드가 confirm/approve/write 0·live 트리거 0·network 0).

## 0. 목적

promotion workflow(승격 절차)와 live command pack(실행 명령)은 있으나, operator 가 이 후보로 **무엇을 외부에서 직접
검증** 하면 real payload 로 옮길 준비가 되는가를 담은 **operator-facing PRE-payload 묶음** 이 없었다. 이 모듈은 promotion
workflow + live command pack + regulatory seed bank 를 thin 합성(재구현 0)해 그 묶음을 낸다 — 후보 요약·query 초안·date
window 는 `regulatory_event_seed_bank`(PURE·기본 `epa_final_rule_emissions`)에서 읽고 발생/같은 사건 단정 0.

## 1. 진입점

```
build_operator_confirmed_ready_package(*, selected_candidate_id=None, operator_payload_status=None) -> dict
보조: sanitized_operator_confirmed_ready_package(out) · main(--candidate-id / --json)
```

## 2. 상태 vocab (`operator_confirmed_ready_package_status`)

```
OCRP_READY        = "operator_confirmed_ready_package_ready"   # 후보 있음 → operator 가 검증 후 promote.
OCRP_REAL_PRESENT = "real_payload_present_already_promoted"    # real payload 이미 존재 → 검증/승인으로.
OCRP_NO_CANDIDATE = "no_candidate_to_prepare"                  # 준비할 후보 없음.
```

promotion status → ready status 는 `_STATUS_FROM_PROMOTION`(RPP_DRAFT_READY/RPP_REAL_PRESENT/RPP_NO_CANDIDATE)
단일 출처 분기(미지 → OCRP_READY fail-closed).

## 3. 핵심 출력 필드

```
operator_confirmed_ready_package_status · candidate_id · candidate_summary · agency_or_entity · action_phrase
official_query_draft · news_query_draft · date_window
operator_must_verify_occurrence · operator_must_verify_official_source · operator_must_verify_news_coverage
operator_must_set_operator_confirmed · operator_must_set_live_approved · manual_confirmation_fields
real_payload_path · validation_command · live_command · validate_payload_command · live_run_command
expected_provider_calls · provider_list · next_action
```

- `real_payload_path` = gitignored `inputs/operator_events/operator_regulatory_event_payload.json`(문자열일 뿐 파일 생성 0) · 명령은 전부 문자열(실행 0).
- `candidate_summary` 는 "occurrence NOT verified by code" 를 항상 명시한다.

## 4. 불변식 (절대 금지·THIS IS NOT A REAL PAYLOAD)

```
operator_confirmed=False · live_approved=False · same_event_asserted=False
event_occurrence_verified_by_code=False · code_writes_real_payload=False · code_claims_event_occurred=False
network_invoked=False · production_gold_count=0
```

- 시그니처에 `acquisition_fn` 자리가 없고 모듈이 `run_operator_confirmed_live(`·`httpx`·`requests` 를 호출하지 않는다
  (live 트리거 불가) · `_assert_pii_safe` 재귀 가드.
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `real_payload_promotion_workflow` (승격 절차·코드가 confirm/approve/write 0·status/명령/manual fields)
- `operator_live_command_pack` (validate/live 명령·provider 미리보기) · `operator_regulatory_event_payload`
  (`REAL_PAYLOAD_PATH`)
- `regulatory_event_seed_bank` (후보 요약·official/news query 초안·date window·기본 epa_final_rule_emissions)
- 테스트: `backend/tests/test_operator_confirmed_ready_package.py` — 14개(전부 통과).

## 6. 이것이 아니다

- REAL payload 가 **아니다** · live 를 트리거할 수 없다(runner 호출 0·acquisition_fn 0·network 0).
- 코드가 디스크에 payload 를 쓰거나 사건 발생/같은 사건을 단정하지 않는다.
- merge 0 · 전송 0 · production gold 0 — operator 가 외부 검증 후 직접 채워야 live 가 된다.

Status: ADR#94 · runtime 0
