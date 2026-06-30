# REAL_PAYLOAD_PROMOTION_WORKFLOW (ADR#93)

> Status: **WORKFLOW/DRAFT-ONLY · operator promote required · RUNTIME No-Go**. live attempt pack 후보를 operator 가
> REAL payload 로 승격(promote)하는 절차를 명시한다 — 코드는 operator_confirmed/live_approved 를 자동 true 로 만들지
> 않고, 실 payload 파일을 쓰지 않으며, 사건 발생을 단정하지 않는다(draft-only). 코드:
> `backend/app/tools/real_payload_promotion_workflow.py` (event fabricate 0·network 0·disk write 0).

## 0. 목적

live attempt pack 은 operator 가 고를 수 있는 candidate event shape 묶음만 준다 — "그 후보 하나를 *어떤 순서·어떤
안전장치* 로 REAL operator payload 로 승격하는가" 의 절차가 흩어져 있었다. 승격은 코드가 아니라 operator 가 하는 일
(발생 확인 → confirmed/approved 직접 설정 → real path 저장)이며, 이 모듈은 그 절차를 *보여줄 뿐* 이다. live attempt
pack + authoring helper 위 thin 합성(재구현 0).

## 1. 진입점

```
build_real_payload_promotion_workflow(*, selected_attempt_candidate_id=None,
                                      operator_payload_status=None) -> dict
보조: sanitized_real_payload_promotion(out) · live_preflight_command(=validation_command alias·no-live)
     main(--json / --candidate-id)
```

기본 선택 후보 = `epa_final_rule_emissions`(occurrence-verifiability 가 가장 높은 유일 selectable·없으면 첫 후보).

## 2. 상태 vocab (`real_payload_promotion_status`)

```
RPP_DRAFT_READY  = "promotion_draft_ready_operator_must_confirm"   # real 없음 → 후보를 draft 로 승격
RPP_REAL_PRESENT = "real_payload_present_promotion_complete"       # real 있음 → 승격 완료(검증/승인으로)
RPP_NO_CANDIDATE = "no_attempt_candidate_to_promote"               # 승격할 후보 없음
```

## 3. 핵심 출력 필드

```
real_payload_promotion_status · selected_attempt_candidate_id · operator_verification_required
manual_confirmation_fields · real_payload_path · promotion_checklist
validation_command · live_preflight_command · manual_live_command · next_action
```

- `promotion_checklist` 순서 강제: **occurrence 확인 FIRST** → source/date/query 확인 → confirmed/approved 설정 →
  real path 저장 → manual live 실행.
- `validation_command`/`live_preflight_command` 는 no-live 구조 검증(별칭)·`manual_live_command` 는 수동 단계.

## 4. 불변식 (절대 금지)

```
code_sets_operator_confirmed_true=False · code_sets_live_approved_true=False
code_claims_event_occurred=False · code_writes_real_payload=False
draft_operator_confirmed=False · draft_live_approved=False
real_payload_path_gitignored=True · production_gold_count=0
```

- file write 0 · network 0 · real-payload disk read 0. draft 는 `validate_operator_confirmed_event` 로 gate 통과
  불가(live-eligible 아님)임을 실값으로 증명한다.

## 5. 합성하는 기존 모듈

- `live_attempt_pack_builder` (후보 집합·status 분기 단일 출처)
- `operator_payload_authoring_helper` (draft template — confirmed/approved 강제 False 상속)
- `operator_payload_sourcing_workflow` (validation/live command 단일 출처)
- `operator_regulatory_event_intake` (`validate` 로 draft 가 live-ineligible 임을 증명)

## 6. 이것이 아니다

- 실 confirmed payload 가 **아니다** — draft 는 operator 가 직접 채워야 한다.
- authoring template ≠ real payload · draft ≠ live 실행 자격.
- 코드가 사건을 단정하거나 confirmed/approved 를 쓰지 않는다.

Status: ADR#93 · runtime 0
