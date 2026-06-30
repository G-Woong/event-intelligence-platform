# AGENT_HOTNESS_REASONING_CONTRACT (ADR#90)

> Status: **CONTRACT ONLY · RUNTIME No-Go**. 미래 에이전트가 "사람이 흥미로워할 사건"을 고르는 기준을 정의한다.
> 코드: `backend/app/tools/agent_hotness_reasoning_contract.py` (고르되 게시하지 않음). **hotness ≠ truth ≠ publish.**

## 0. 왜 필요한가

에이전트가 전세계 사건 중 무엇을 수집·정제·게시할지 스스로 고르려면 **human-interest 선정 rubric** 이 필요하다.
없으면 (a) LLM 으로 흥미를 환각하거나, (b) community buzz 를 증거로 둔갑하거나, (c) hotness 만으로 게시하는 위험.
`19_SPEC §2.4 heat`(half-life decay ranking score)는 *랭킹* 신호일 뿐 선정 rubric 이 아니다 — 이 문서가 그 공백을 메운다.

## 1. Criteria (15)

`HOTNESS_CRITERIA`:

```
novelty · stakes · social_impact · conflict · controversy · human_curiosity
community_reaction_potential · official_evidence_availability · cross_source_corroboration
time_sensitivity · follow_up_potential · local_relevance · global_relevance
uncertainty_risk · safety_sensitivity
```

## 2. Output (7)

`evaluate_hotness_candidate(signals)` 산출:

```
hotness_candidate · hotness_reasoning_summary · evidence_requirements · source_requirements
community_layer_requirements · publish_blockers · next_collection_actions
```

- **evidence_requirements**: official 증거 + cross-source 교차 + uncertainty 가시 (게시 전 필수).
- **source_requirements**: anchor 는 official/news 만 (community/market/catalog 는 anchor 아님), search URL ≠ truth.
- **community_layer_requirements**: community 는 verified event 뒤 `reaction_to` only (anchor 금지).
- **publish_blockers** (항상 비어있지 않음): `hotness_alone_does_not_publish` · `requires_official_evidence` ·
  `requires_cross_source_corroboration` · `requires_human_label_provenance` · `requires_merge_gate` ·
  `requires_public_iu_gate`.

## 3. Forbidden (§13)

- publish based on hotness alone
- treat hotness as truth
- use community buzz as an evidence anchor
- use an LLM to hallucinate interest

## 4. Runtime No-Go

`runtime_enabled=False` · `can_publish_on_hotness_alone=False` · `community_buzz_is_evidence_anchor=False` ·
`hotness_is_truth=False` · `llm_invoked=False` · `merge_allowed=False` · `r2_r7_no_go=True`.

hotness 는 **수집/우선순위 신호**다 — 무엇을 먼저 수집·교차할지 결정하는 데 쓰이고, 게시는 official 증거·human
label·MERGE_GATE·public-IU gate 뒤에만 일어난다.

## 5. Cross-links

- `HOT_INTELLIGENCE_POST_CONTRACT.md` (hotness 후보가 통과해야 할 post 계약)
- `COMMUNITY_INTERACTION_FUTURE_GATE.md` (community 반응/댓글 runtime gate)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §2.4 heat` (랭킹 score — 선정 rubric 과 구분)
- `RAG_KG_ENTITY_GATE_CONTRACT.md §2` (community = reaction_to·anchor 금지)
