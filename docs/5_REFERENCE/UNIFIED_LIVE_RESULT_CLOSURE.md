# UNIFIED_LIVE_RESULT_CLOSURE (ADR#94)

> Status: **DIAGNOSTIC/CLOSURE-ONLY · truth/gold 아님 · RUNTIME No-Go**. 한 번의 bounded live 결과를 여섯 단일 출처로
> 의존 순서대로 합성해 하나의 closure dict 로 닫고, dominant gap 으로 다음 iteration 을 권고한다. 코드:
> `backend/app/tools/unified_live_result_closure.py` (merge 0·LLM 0·network 0·전송 0·disk-write 0).

## 0. 목적

bounded live 를 한 번 돌리면 그 결과를 해석하는 도구가 여섯 개(no-yield taxonomy·overlap diagnostics·news breadth
trigger·next provider expansion·freeze hardening·freeze→R1 checklist)로 흩어져 있어, operator 가 "이번 live 가 무엇을
남겼고 다음에 무엇을 해야 하는가" 를 한 화면에서 받지 못한다. 이 모듈은 그 여섯 단일 출처를 **의존 순서대로 compose**
(재구현 0·thin orchestration)해 닫고, dominant gap(payload/news/official/overlap/freeze)을 골라 recommended_iteration
과 operator/R1 next action 을 낸다.

## 1. 진입점

```
build_unified_live_result_closure(*, live_query_executed=False, acquisition_out=None, payload_entrypoint_out=None,
                                  overlap_candidates=None, seed=None, official_records_count=0, news_records_count=0,
                                  in_window_news_count=0, bridge_candidate_count=0, freeze_artifact=None,
                                  real_payload_present=False, batch_id=None) -> dict
보조: sanitized_unified_live_result_closure(out) · main(--real-payload / --json)
```

## 2. 상태 vocab (`unified_live_closure_status` / `dominant_gap`)

```
closure: closed_missing_payload · closed_freeze_candidate · closed_no_yield_{taxonomy_status}
gap: GAP_PAYLOAD=missing_payload · GAP_NEWS=news_side_gap · GAP_OFFICIAL=official_side_gap
     GAP_OVERLAP=overlap_gap · GAP_FREEZE=freeze_candidate · GAP_NONE=no_dominant_gap
```

`_dominant_gap` 우선순위: payload 부재 → freeze 후보 → trigger status(NBT_* 인용으로 official/news/overlap) → none.
`_GAP_TO_ITERATION` 가 gap → recommended_iteration 한 줄을 매핑한다(상위 출처 인용·새 정책 0).

## 3. 핵심 출력 필드

```
unified_live_closure_status · live_query_executed · real_payload_present · dominant_gap
live_no_yield_taxonomy_status · taxonomy_next_action · overlap_diagnostic_status · overlap_blocked_dimension
news_breadth_trigger_status · next_provider_expansion_status · freeze_readiness_status · freeze_artifact_safe
freeze_to_r1_status · r1_next_action · operator_next_action · recommended_iteration
no_live_result_without_payload(True) · no_candidate_no_freeze(True)
```

- payload 가 없으면 closure 는 missing-payload 로 닫고 operator_confirmed_ready_package 작성을 권한다(live 결과 단정 0).
- freeze 후보(artifact)가 없으면 hardening 은 no_artifact — freeze 가 일어나지 않는다.

## 4. 불변식 (절대 금지)

```
is_truth=False · same_event_asserted=False · merge_allowed=False · llm_invoked=False
network_invoked=False · production_gold_count=0 · increases_gold=False
```

- closure 는 **truth 가 아니고 gold 가 아니다** — 여섯 builder 의 status/next_action 을 인용만 한다(`_assert_pii_safe`).
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈 (의존 순서)

- `live_no_yield_taxonomy` → `official_news_overlap_diagnostics` → `news_breadth_trigger`
- `next_provider_expansion_pack` → `first_freeze_package_hardening` → `freeze_to_r1_executable_checklist`
- batch id 는 `r1_label_return_operational_bridge.DEFAULT_BATCH_ID` 재사용(재저작 0).
- 테스트: `backend/tests/test_unified_live_result_closure.py` — 10개(전부 통과).

## 6. 이것이 아니다

- truth/gold 가 **아니다** · gold 를 증가시키지 않는다 · same_event 를 단정하지 않는다.
- 새 정책/임계값을 만들지 않는다 — 상위 단일 출처를 인용·요약할 뿐이다.
- 어떤 경로도 merge/LLM/network/secret/disk-write 를 건드리지 않는다.

Status: ADR#94 · runtime 0
