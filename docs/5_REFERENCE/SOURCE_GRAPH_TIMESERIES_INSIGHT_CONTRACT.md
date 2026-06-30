# SOURCE_GRAPH_TIMESERIES_INSIGHT_CONTRACT (ADR#94)

> Status: **CANDIDATE-ONLY/COMPOSE-CITE · 신규 어휘 0 · RUNTIME No-Go**. "여러 소스를 그래프로 잇고 사건 시계열을
> 누적해 insight 후보를 만든다" 는 미래 방향을 **기존 게이트에 결속** 한다 — 새 enum·새 게이트 0, 이미 정의된 계약을
> 인용만. 코드: `backend/app/tools/source_graph_timeseries_insight_contract.py` (merge/LLM/embedding/network/public IU 0).

## 0. 목적

source/evidence/entity node + KG edge 로 소스를 잇고 timeline update 를 누적하는 제품 방향을, **재구현·신규 enum·신규
게이트 없이** 기존 문서 개념을 cite 해 한 곳에 묶는다. storage class/KG edge/community 경계 → RAG_KG_ENTITY_GATE_
CONTRACT, source role/catalog·market → INTELLIGENCE_UNIT_CONTRACT §3, anchor 정책 → HOT_INTELLIGENCE_POST_CONTRACT
§3(`is_valid_anchor_role` 재사용), uncertainty/must-NOT-assert/MERGE_GATE → LLM_EVIDENCE_PACKET_CONTRACT, timeline
append-only → EVENT_SCHEMA, human label/R1·R2 → RAG_KG_AGENT_READINESS·HOT_POST_GATE_ALIGNMENT.

## 1. 진입점

```
build_source_graph_timeseries_insight_contract() -> dict
보조: sanitized_source_graph_timeseries_insight_contract(out) · main(--json)
```

## 2. 상태 vocab (`source_graph_timeseries_contract_status`)

```
CONTRACT_STATUS_CANDIDATE_ONLY = "candidate_only_runtime_disabled"
CONTRACT_VERSION = "source_graph_timeseries_insight_v1"
```

15 component(component/role_or_storage_class/candidate_until_merge_gate/anchor_eligible/citation) — `anchor_eligible`
은 선언하지 않고 `is_valid_anchor_role(role_or_storage_class)` 로 계산(official/news 만 True).

## 3. 핵심 출력 필드

```
source_graph_timeseries_contract_status · runtime_enabled(False) · components · component_count(15)
storage_class_enum · source_role_enum · allowed_retrieval_use_enum · kg_edge_types · merge_gate_status_enum
anchor_roles · non_anchor_roles · rules · rule_count(9)
+ 9 rule 평탄화: graph_edge_candidate_until_merge_gate · community/market/catalog_is_evidence_anchor
  insight_candidate_publishable · timeseries_update_asserts_same_event · public_readiness_requires_r1_r2
  llm_summary_enabled · official_news_only_anchor
```

- 5개 enum 은 전부 기존 어휘 재사용(신규 0) · anchor 가능 component 는 `official_evidence`/`news_corroboration` 뿐.

## 4. 불변식 (절대 금지·CANDIDATE-ONLY)

```
runtime_enabled=False · merge_allowed=False · same_event_asserted=False · llm_invoked=False
embedding_invoked=False · public_iu_allowed=False · network_invoked=False · r2_r7_no_go=True
```

- graph edge 는 MERGE_GATE 전까지 candidate(truth 아님) · community/market/catalog 는 evidence anchor 금지 · insight
  후보는 게시 불가 · timeline update 는 same_event 단정 0 · LLM 요약은 gate 전 비활성(`_assert_pii_safe` 재귀 가드).
- 이번 턴: real payload 미존재가 정직한 block · production_gold_count 0 · R1 gap 200 · R2~R7 No-Go ·
  LLM/embedding/merge/DB/public-IU/Hot-Post/comment runtime disabled.

## 5. 합성하는 기존 모듈 (인용)

- `hot_intelligence_post_contract` (`ANCHOR_ROLES`·`NON_ANCHOR_ROLES`·`is_valid_anchor_role` 재사용) ·
  `reviewer_pilot_handoff._assert_pii_safe`
- cite-only 문서: EVENT_SCHEMA · INTELLIGENCE_UNIT_CONTRACT · RAG_KG_ENTITY_GATE_CONTRACT · RAG_KG_AGENT_READINESS ·
  LLM_EVIDENCE_PACKET_CONTRACT · HOT_INTELLIGENCE_POST_CONTRACT · HOT_POST_GATE_ALIGNMENT
- 테스트: `backend/tests/test_source_graph_timeseries_insight_contract.py` — 11개(전부 통과).

## 6. 이것이 아니다

- 신규 어휘/enum/게이트가 **아니다** — 기존 계약을 compose/cite 할 뿐이다.
- graph edge 는 MERGE_GATE 전 truth 가 아니고, insight 후보는 게시할 수 없다 · public_readiness 는 R1/R2 를 요구한다.
- community/market/catalog 는 anchor 가 아니다(official/news 만) · 게시하지 않는다 · runtime 0.

Status: ADR#94 · runtime 0
