# FIRST_REAL_PAYLOAD_EXECUTION_SPRINT (ADR#94)

> Status: **SPRINT/SINGLE-ENTRYPOINT · real payload 없으면 live 0 · RUNTIME No-Go**. valid ∧ live_approved ∧
> acquisition_fn 주입이면 **단 한 번** bounded live 실행(approval-gated runner 경유만)·없으면 blocked-reason + PRE-payload
> 묶음 안내. 코드: `backend/app/tools/first_real_payload_execution_sprint.py` (network 0 except the one gated live call).

## 0. 목적

operator 가 real payload 를 drop 했을 때 *첫 real payload 를 실제로 실행* 하는 단일 진입점이 없었다(payload 경계·gate·
runner·PRE-payload 묶음이 흩어짐). 이 모듈은 present/valid 판정(주입 `operator_payload_status` 기반·파일시스템 미접근·
결정론) 후 valid ∧ approved ∧ executor 가 모두 갖춰진 단 하나의 분기에서만 `run_operator_confirmed_live` 를 **정확히
한 번** 호출한다. 그 외는 live 0 이며 payload 가 없으면 PRE-payload 묶음으로 안내한다(결과는 runner 에서 취함·재구현 0).

## 1. 진입점

```
build_first_real_payload_execution_sprint(*, real_payload_path=None, operator_payload_status=None,
                                          live_approved=None, acquisition_fn=None,
                                          selected_candidate_id=None, batch_id=None) -> dict
보조: sanitized_first_real_payload_execution_sprint(out) · main(--candidate-id / --json)
```

## 2. 상태 vocab (`first_real_payload_sprint_status`)

```
SPRINT_AWAITING_PAYLOAD     = "awaiting_operator_payload"        # real payload 없음 → PRE-payload 묶음 안내.
SPRINT_PAYLOAD_INVALID      = "payload_invalid"                  # 있으나 무효 → live 0.
SPRINT_PAYLOAD_NOT_EXECUTED = "payload_present_not_executed"     # valid 이나 미승인/executor 없음 → live 0.
SPRINT_LIVE_EXECUTED        = "operator_confirmed_live_executed" # valid ∧ approved ∧ executor → 단 한 번 live.
```

4분기: ①present=False → awaiting(`missing_payload`·ready package 생성) · ②valid=False → invalid · ③valid ∧ approved ∧
executor → 단 한 번 gated live(`network_invoked=True`) · ④그 외 → not_executed(`approved_but_no_executor`∨`not_approved`).

## 3. 핵심 출력 필드

```
first_real_payload_sprint_status · real_payload_present · real_payload_valid · selected_candidate_id
operator_verification_required · payload_required_fields · real_payload_path
validate_payload_command · dry_run_command · live_run_command · expected_provider_calls · provider_list
bounded_live_policy · live_query_executed · operator_event_status · live_no_yield_taxonomy_status
production_candidate_status · reviewer_handoff_ready · operator_confirmed_ready_package · blocked_reason · next_action
```

- `bounded_live_policy`: `routes_only_through_operator_confirmed_live_runner=True` · `routes_through_ungated_fidelity_probe=False` — provider_date_window_fidelity 라우팅 0.
- 명령(validate/dry/live)·provider 목록은 `operator_live_command_pack` 인용(string only·실행 0).

## 4. 불변식 (절대 금지)

```
routes_through_ungated_fidelity_probe=False · raw_payload_text_exposed=False · secret_values_exposed=False
actual_sending_performed=False · merge_allowed=False
```

- `network_invoked` 는 ③분기에서만 True · `production_gold_count`/`live_query_executed` 는 runner 결과 passthrough(`_assert_pii_safe` 가드·raw payload 본문/`confirmed_by` 마커 미노출).
- 이번 턴: real payload 미존재가 정직한 block · `production_gold_count=0` · R1 gap 200 · R2~R7 No-Go ·
  LLM/embedding/merge/DB/public-IU/Hot-Post/comment runtime disabled.

## 5. 합성하는 기존 모듈

- `operator_confirmed_live_runner` (`run_operator_confirmed_live`·gated live 의 유일 경로)
- `operator_confirmed_ready_package` (real payload 없을 때 PRE-payload 안내)
- `operator_live_command_pack` (validate/dry/live 명령·provider 미리보기) · `operator_regulatory_event_intake`
  (`OPERATOR_EVENT_REQUIRED_FIELDS`) · `operator_regulatory_event_payload` (`PAYLOAD_*`·`REAL_PAYLOAD_PATH`)
- 테스트: `backend/tests/test_first_real_payload_execution_sprint.py` — 13개(전부 통과).

## 6. 이것이 아니다

- real payload 가 **아니다** · provider_date_window_fidelity 경유가 아니다.
- network 0 — valid ∧ approved ∧ executor 가 모두 갖춰진 단 한 번을 제외하면 어떤 호출도 없다.
- 코드가 payload 를 디스크에 쓰거나 same_event 를 단정하지 않는다 · merge/gold 생성 0.

Status: ADR#94 · runtime 0
