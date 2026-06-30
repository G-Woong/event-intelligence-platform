# HOT_POST_GATE_ALIGNMENT (ADR#91)

> Status: **GATE ALIGNMENT · RUNTIME No-Go**. Hot Intelligence Post 의 `public_readiness` 를 R1(gold)·R2(MERGE_GATE)·
> evidence·source-role·community 경계에 결속한다. 코드: `backend/app/tools/hot_post_gate_alignment.py` (게시 0).

## 0. 왜 필요한가

`HOT_INTELLIGENCE_POST_CONTRACT.md` 의 `evaluate_hot_post_readiness` 는 merge_gate·official_evidence·human_label·
uncertainty·anchor 만 검사했다. 그러나 public 게시는 "production gold 가 있는가·news 교차가 있는가·public safety/
moderation/reply policy 가 준비됐는가" 같은 **상위 게이트** 를 *모두* 요구해야 한다. 이 모듈은 그 11개 요구를 한 곳에
결속한다(기존 readiness 를 COMPOSE·재구현 0).

## 1. 11개 게이트 요구 (`HOT_POST_GATE_REQUIREMENTS`)

```
verified_event_identity · production_gold_available · merge_gate_passed
official_evidence_present · news_corroboration_present · source_role_guard_passed
uncertainty_summary_present · community_layer_reaction_to_only
public_safety_review · moderation_policy_ready · reply_policy_ready
```

- **기존 readiness 재사용(5)**: merge_gate_passed · official_evidence_present · source_role_guard_passed ·
  uncertainty_summary_present · community_layer_reaction_to_only.
- **새로 결속(5)**: verified_event_identity · production_gold_available(gold>0) · news_corroboration_present ·
  public_safety_review · moderation_policy_ready · reply_policy_ready.
- `community_layer_reaction_to_only` 은 community 레이어가 없으면 vacuously 충족(오용이 없을 때만 통과).

## 2. 현 상태 (불변)

`build_hot_post_gate_alignment(draft=None)`:

- `public_readiness` = 11개 요구 **전부** 충족(현 단계 evidence/gold/merge 부재 → `False`·`missing_requirements` 10).
- `hot_post_gate_status` ∈ {`blocked_requirements_unmet`, `requirements_met_runtime_disabled`}.
- **모든 요구 충족이어도** `runtime_enabled=False` · `public_post_body_generated=False` · `comment_reply_generation=False`
  · `publishable=False`(runtime 은 후속 ADR 의 별도 auth/safety gate 후에만 개방).

## 3. 게시 불가 규칙 (§13)

```
hotness alone cannot publish      (hotness_alone_publishable=False)
community buzz cannot publish     (community_buzz_publishable=False)
official record alone cannot publish (official_record_alone_publishable=False)
LLM headline cannot publish       (llm_headline_publishable=False)
public_readiness requires evidence/gold/merge gates
```

## 4. 선행 게이트 시퀀스

1. R1 production gold ≥ floor (live ≥200 / KO ≥50·actual returned human labels).
2. R2 MERGE_GATE (precision ≥0.98 / FPR ≤0.01 / hard-neg FP=0).
3. public-IU gate (`RAG_KG_ENTITY_GATE_CONTRACT §5`).
4. Hot Post public_readiness(이 문서의 11개 요구) → **그 후에도** runtime 은 별도 ADR 의 auth/safety gate 후 개방.

## 5. Cross-links

- `HOT_INTELLIGENCE_POST_CONTRACT.md §2/§4/§5` (field/gate 계약·이 모듈이 COMPOSE 하는 readiness)
- `COMMUNITY_POSTING_ROADMAP_CONTRACT.md` stage_3_public_readiness_gate (이 게이트가 stage_3 의 진입 조건)
- `COMMUNITY_INTERACTION_FUTURE_GATE.md` (moderation/reply policy 요구의 단일 출처)
- `RAG_KG_AGENT_READINESS.md §6b` (R1~R7 ladder·현재 R1=FAIL·R2~R7 No-Go)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (Hot Post 제품 방향)
