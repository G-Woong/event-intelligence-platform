# FIRST_PAYLOAD_CANDIDATE_EVIDENCE_BINDER (ADR#95)

> Status: **EVIDENCE-TO-VERIFY/OPERATOR-FACING · 확정 아님 · payload 아님 · RUNTIME No-Go**. candidate
> `epa_final_rule_emissions` 를 real payload 로 옮기기 전에 operator 가 **무엇을 증거로 직접 검증해야 하고 어떤 질문이
> 미해결인가**를 official/news 로 분리해 담는 binder. 코드:
> `backend/app/tools/first_payload_candidate_evidence_binder.py` (live 트리거 0·disk write 0·network 0).

## 0. 목적

`operator_confirmed_ready_package` 는 promote 용 PRE-payload 묶음을 주지만, "이 후보를 real payload 로 옮기기 전에
무엇을 증거로 검증해야 하고 어떤 질문이 아직 미해결인가"를 official(=evidence)·news(=reporting)로 **분리**해 담은
binder 가 한 곳에 없었다. 이 모듈은 regulatory seed bank(PURE) 위 thin 합성(재구현 0)으로 그 binder 를 낸다 — query 는
**초안**일 뿐 truth 가 아니고(query_drafts_are_not_truth=True), date window 는 code-proposed·UNVERIFIED 이며, 미해결
질문과 예상 실패 모드를 반드시 표면화한다. **이 binder 는 확정도 payload 도 아니다.**

## 1. 진입점

```
build_first_payload_candidate_evidence_binder(*, selected_candidate_id=None) -> dict   # 기본 epa_final_rule_emissions
보조: sanitized_first_payload_candidate_evidence_binder(out) · main(--candidate-id / --json)
```

## 2. 상태 vocab (`first_payload_evidence_binder_status`)

```
BINDER_READY        = "evidence_binder_ready"     # 후보 seed 있음 → 검증할 evidence binder 산출.
BINDER_NO_CANDIDATE = "no_candidate_to_bind"      # 일치하는 seed 없음(잘못된 candidate id).
```

후보 seed 가 없으면 `unresolved_questions` 선두에 "어떤 candidate 를 bind 할지" 질문이 추가된다.

## 3. 핵심 출력 필드

```
first_payload_evidence_binder_status · candidate_id · candidate_summary
official_evidence_to_verify · news_evidence_to_verify · date_window_to_verify
agency_entity_to_verify · action_phrase_to_verify · canonical_url_to_verify · published_at_to_verify
source_role_notes · expected_failure_modes · next_query_adjustments · unresolved_questions
```

- `official_evidence_to_verify`(provider·official_query_draft·document_type·overlap tokens)와 `news_evidence_to_verify`
  (providers·news_query_draft·angle)는 **분리** — 같은 role 로 섞지 않는다.
- `date_window_to_verify.note` = "code-proposed unverified, operator must confirm actual date" · `expected_failure_modes`
  는 title_token_divergence(seed.risk 인용)를 포함하고, `canonical_url`/`published_at` 은 code 가 보유 0(operator 가 채움).

## 4. 불변식 (절대 금지·NOT a confirmation / NOT a payload)

```
binder_is_confirmation=False · binder_is_payload=False · binder_can_trigger_live=False · binder_claims_event_occurred=False
query_drafts_are_not_truth=True · same_event_asserted=False · event_occurrence_verified=False
network_invoked=False · production_gold_count=0
```

- `acquisition_fn` 0·live runner 호출 0(live 트리거 불가) · query 는 검증 대상 초안일 뿐 truth 아님 · `_assert_pii_safe`
  재귀 가드.
- 이번 턴: real payload 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `regulatory_event_seed_bank` (후보 요약·official/news query 초안·date window·risk·source_role_policy·기본
  epa_final_rule_emissions·값 하드코딩 0).
- `reviewer_pilot_handoff._assert_pii_safe` 재귀 PII 가드.
- 테스트: `backend/tests/test_first_payload_candidate_evidence_binder.py` — 14개(전부 통과).

## 6. 이것이 아니다

- 확정이 **아니다** · payload 가 아니다 · live 를 트리거할 수 없다(acquisition_fn 0·network 0).
- 사건 발생을 단정하지 않는다(event_occurrence_verified=False) · query 는 truth 가 아니라 검증 대상 초안이다.
- merge 0 · LLM/embedding 0 · DB 0 · 전송 0 · production gold 0 — operator 가 official+news 를 외부 검증해야 한다.

Status: ADR#95 · runtime 0
