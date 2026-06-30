# OPERATOR_VERIFICATION_WORKSHEET (ADR#95)

> Status: **HUMAN-FILLS/OPERATOR-FACING · 완료해도 확정 아님 · payload 아님 · RUNTIME No-Go**. 사람이 외부에서 사건
> 발생을 검증하는 구조화 worksheet — **official source 검증과 news coverage 검증을 구조적으로 분리**한다. 코드:
> `backend/app/tools/operator_verification_worksheet.py` (코드가 operator_confirmed/live_approved 0·disk write 0·
> network 0).

## 0. 목적

`operator_confirmed_ready_package` 는 검증 항목을 한 줄 지시문으로 뭉쳐 두어, operator 가 official 기록과 news 보도를
같은 칸에 섞어 "확인함" 처리하면 same-day unrelated 보도가 official 검증으로 둔갑할 수 있다(ADR#84 date-window
fidelity gap 의 사람 측 재현). 이 모듈은 그 위험을 끊는 worksheet 다 — official-source check 와 news-coverage check 를
**다른 check** 로 분리하고, 각 check 를 {item·instruction·record_slot·confirmed} 빈칸 dict 로 준다. 핵심 정직성:
**worksheet 완료 ≠ 확정** — 셋을 다 채워도 코드는 operator_confirmed/live_approved 를 절대 True 로 두지 않는다.

## 1. 진입점

```
build_operator_verification_worksheet(*, candidate_id=None, official_check=None,
                                      news_coverage_check=None, date_window_check=None) -> dict
보조: sanitized_operator_verification_worksheet(out) · main(--candidate-id / --json)
```

## 2. 상태 vocab (`worksheet_status` / `completion_status`)

```
WORKSHEET_INCOMPLETE = "worksheet_incomplete_operator_must_verify"
WORKSHEET_COMPLETE   = "worksheet_complete_still_not_confirmation"   # 완료조차 확정이 아님(이름이 못 박음)
completion_status: "complete" / "incomplete"
```

각 *_check 는 `confirmed==True` **그리고** `record_slot` 이 비어있지 않을 때만 충족(빈칸 confirm 둔갑 차단). official +
news + date_window **셋 모두** 충족일 때만 complete(나머지 check 는 기록용).

## 3. 핵심 출력 필드

```
worksheet_status · candidate_id · completion_status
official_source_check · news_coverage_check · date_window_check · agency_entity_check
action_phrase_check · canonical_url_check · published_at_check · source_role_check
operator_confirmation_fields(12) · unresolved_questions
```

- 각 check = {item, instruction, record_slot:"", confirmed:False} — record_slot 은 operator 가 채울 빈칸이며 임의 키는
  echo 하지 않는다(PII 가드).
- `operator_confirmation_fields` = `OPERATOR_EVENT_REQUIRED_FIELDS`(12) 단일 출처 · `unresolved_questions` 는 항상 비어
  있지 않다(완료가 발생/같은 사건을 단정하지 않음을 못 박음).

## 4. 불변식 (절대 금지·완료해도 확정 아님)

```
worksheet_is_payload=False · worksheet_complete_auto_confirms=False
code_sets_operator_confirmed_true=False · code_sets_live_approved_true=False
operator_confirmed=False · live_approved=False · same_event_asserted=False · network_invoked=False · production_gold_count=0
```

- `acquisition_fn` 을 받지 않고 live runner 를 호출하지 않는다(payload 아님·live 트리거 0) · `_assert_pii_safe` 재귀 가드.
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `operator_regulatory_event_intake.OPERATOR_EVENT_REQUIRED_FIELDS` (operator 가 최종 채울 12개 confirmation 필드·단일 출처).
- `regulatory_event_seed_bank` (candidate 의 agency/action/official_query/news_query/date_window·기본 epa_final_rule_emissions).
- `reviewer_pilot_handoff._assert_pii_safe` 재귀 PII 가드.
- 테스트: `backend/tests/test_operator_verification_worksheet.py` — 15개(전부 통과).

## 6. 이것이 아니다

- 확정이 **아니다** — worksheet 완료는 검증 절차 기록일 뿐 사건 발생/같은 사건 단정이 아니다(same_event_asserted=False).
- payload 가 아니고 live 를 트리거할 수 없다 · 코드가 operator_confirmed/live_approved 를 true 로 설정하지 않는다.
- merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · production gold 0 — 사람이 외부 검증 후 직접 채워야 한다.

Status: ADR#95 · runtime 0
