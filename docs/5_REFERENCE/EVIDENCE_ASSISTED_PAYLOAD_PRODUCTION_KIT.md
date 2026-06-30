# EVIDENCE_ASSISTED_PAYLOAD_PRODUCTION_KIT (ADR#95)

> Status: **PRE-PAYLOAD/OPERATOR-FACING · NOT a payload · live 트리거 불가 · RUNTIME No-Go**. operator-confirmed-ready
> 묶음을 operator 가 실제로 들고 움직일 수 있는 **EVIDENCE-REQUIREMENTS kit**(official record 조건 + news 보도 조건을
> acceptance 기준까지 분리·명시)으로 변환한다. 코드: `backend/app/tools/evidence_assisted_payload_production_kit.py`
> (disk write 0·network 0·live 실행 0·secret 0).

## 0. 목적

`operator_confirmed_ready_package` 는 "operator 가 외부에서 무엇을 검증할지" 체크리스트와 query 초안·real path·명령을
한 묶음으로 준다. 그러나 candidate `epa_final_rule_emissions` 를 real payload 로 옮기려면 **정확히 어떤 official/news
증거를 어떤 acceptance 기준으로 모아야 하는가** — official record 가 만족할 조건(provider/agency/document_type/overlap
tokens)과 news 보도가 만족할 조건(provider/angle/action phrase)이 분리·구조화돼 있지 않았다. 이 모듈은 ready package +
regulatory seed bank 위 thin 합성(재구현 0)으로 그 kit 을 낸다 — **payload 가 아니고**, **live 를 트리거할 수 없으며**,
사건이 일어났다고 단정하지 않는다.

## 1. 진입점

```
build_evidence_assisted_payload_production_kit(*, selected_candidate_id=None, operator_payload_status=None) -> dict
보조: sanitized_evidence_assisted_payload_production_kit(out) · main(--candidate-id / --json)
```

## 2. 상태 vocab (`evidence_payload_kit_status`)

```
KIT_READY        = "evidence_payload_kit_ready"   # 후보 있음 → operator 가 아래 증거를 모아 외부 검증.
KIT_NO_CANDIDATE = "no_candidate_to_prepare"      # 준비할 후보 없음.
```

ready package 의 `candidate_id` 존재 여부로 분기한다(있으면 READY·없으면 NO_CANDIDATE).

## 3. 핵심 출력 필드

```
evidence_payload_kit_status · selected_candidate_id
official_evidence_required · official_evidence_required_count · news_evidence_required · news_evidence_required_count
agency_or_entity_required · action_phrase_required · date_window_required · expected_news_angle_required
source_role_requirements · real_payload_path · validation_command · live_command · operator_next_action
```

- `official_evidence_required` = {provider·query·agency·document_type·expected_overlap_tokens·acceptance_criteria},
  `news_evidence_required` = {provider·query·expected_news_angle·action_phrase·divergence_risk·acceptance_criteria} —
  official(authoritative evidence)과 news(public reporting)는 **별개 리스트**다.
- `source_role_requirements` 는 not_same_role=True · community_or_market_not_anchor=True 를 명시한다.

## 4. 불변식 (절대 금지·THIS IS NOT A PAYLOAD)

```
kit_is_payload=False · kit_can_trigger_live=False · operator_confirmed=False · live_approved=False
same_event_asserted=False · code_claims_event_occurred=False · network_invoked=False · production_gold_count=0
```

- 시그니처에 `acquisition_fn` 자리가 없고 live runner 를 호출하지 않는다 — validate/live 명령은 ready package 가 만든
  **문자열 그대로**(실행 0) · `_assert_pii_safe` 재귀 가드.
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `operator_confirmed_ready_package` — candidate identity·official/news query 초안·date window·real path·validate/
  live 명령을 상속.
- `regulatory_event_seed_bank` — ready package 가 drop 한 evidence-shaping 필드(expected_overlap_tokens·
  expected_news_angle·document_type·risk·source_role_policy)를 복원(값 하드코딩 0·기본 epa_final_rule_emissions).
- `reviewer_pilot_handoff._assert_pii_safe` 재귀 PII 가드.
- 테스트: `backend/tests/test_evidence_assisted_payload_production_kit.py` — 15개(전부 통과).

## 6. 이것이 아니다

- payload 가 **아니다** · live 를 트리거할 수 없다(acquisition_fn 0·runner 호출 0·network 0).
- 사건 발생/같은 사건을 단정하지 않는다 · operator_confirmed/live_approved 를 코드가 true 로 두지 않는다.
- merge 0 · 전송 0 · production gold 0 — operator 가 official+news 증거를 외부 검증한 뒤에야 real payload 가 된다.

Status: ADR#95 · runtime 0
