# SOURCE_GRAPH_HOT_POST_INTEGRATION_MAP (ADR#95)

> Status: **CONTRACT-ONLY/CANDIDATE-ONLY · runtime 0 · public post body 0 · RUNTIME No-Go**. source-graph/time-series
> insight 계약의 15 component 를 Hot Intelligence Post 계약의 21 field 에 **필드 단위로 결속**한다(new 어휘 0·
> compose/cite only). 코드: `backend/app/tools/source_graph_hot_post_integration_map.py` (merge 0·LLM 0·network 0·
> 게시 0).

## 0. 목적

source-graph/time-series insight 계약(15 component)과 Hot Intelligence Post 계약(21 field)이 따로 있어, "어느
component 가 어느 post field 로 들어가고 무엇이 anchor 가 될 수 있는가"를 한 곳에서 선언한 매핑이 없었다. 이 모듈은 두
계약을 인용(cite)해 field-by-field 매핑만 선언한다 — 런타임도, public post body 도, merge 도 만들지 않는다. anchor 가
될 수 있는 component 는 official_evidence/news_corroboration 뿐이고, insight 후보는 게시 불가, timeline 은 merge gate
전 same_event 단정 0, community/market 은 anchor 금지다.

## 1. 진입점

```
build_source_graph_hot_post_integration_map() -> dict
보조: sanitized_source_graph_hot_post_integration_map(out) · main(--json)
```

## 2. 상태 vocab (`source_graph_hot_post_integration_status`)

```
MAP_READY = "integration_map_candidate_only_runtime_disabled"   # 단일 상태 — 매핑 조립·검증만, 게시 0
```

매핑 component 가 cited 15 밖이거나 field 가 21 `HOT_POST_FIELDS` 밖이면 drift → KeyError(lock 테스트가 잡음).

## 3. 핵심 출력 필드

```
source_graph_hot_post_integration_status · mappings(16) · mapping_count
hot_post_fields · hot_post_field_count(21) · mapped_hot_post_fields · post_only_fields(7)
anchor_components · non_anchor_components · anchor_roles
```

- 16 매핑(예: event_identity→event_id · official_evidence→official_evidence[anchor] · news_corroboration→
  news_corroboration[anchor] · entity_nodes→entity_context · insight_candidates→why_it_is_hot[candidate-only] ·
  evidence_edges→source_agreement/source_disagreement · source_nodes→provenance note only).
- `anchor_eligible` 은 선언이 아니라 `is_valid_anchor_role` 로 계산(official/news 만 True) · `post_only_fields` =
  post_id·post_status·headline·short_hook·reply_policy·moderation_status·last_updated_at.

## 4. 불변식 (절대 금지·CONTRACT-ONLY)

```
runtime_enabled=False · public_post_body_generated=False · community_is_anchor=False · market_is_anchor=False
insight_candidate_publishable=False · timeline_update_asserts_same_event=False · public_readiness_requires_r1_r2=True
merge_allowed=False · same_event_asserted=False · llm_invoked=False · network_invoked=False · production_gold_count=0
```

- insight 후보(why_it_is_hot)는 suggestion 일 뿐 truth 가 아니라 게시 불가 · public_readiness 는 R1(gold)+R2(MERGE_GATE)
  요구 · `_assert_pii_safe` 가드.
- 이번 턴: public post runtime 은 정직한 No-Go · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `source_graph_timeseries_insight_contract.build_source_graph_timeseries_insight_contract` (15 component 단일 출처·cite).
- `hot_intelligence_post_contract` (`HOT_POST_FIELDS` 21·`is_valid_anchor_role`·`ANCHOR_ROLES`={official,news}).
- `reviewer_pilot_handoff._assert_pii_safe` 재귀 PII 가드.
- 테스트: `backend/tests/test_source_graph_hot_post_integration_map.py` — 12개(전부 통과).

## 6. 이것이 아니다

- 런타임이 **아니다** · public post body 를 생성하지 않는다(매핑을 조립·검증만 한다).
- community/market 은 anchor 가 아니다 · insight 후보는 게시 불가 · timeline update 는 merge gate 전 same_event 를
  단정하지 않는다.
- merge 0 · LLM 0 · network 0 · production gold 0 — public_readiness 는 R1/R2 를 요구하므로 이 단계에서 게시되지 않는다.

Status: ADR#95 · runtime 0
