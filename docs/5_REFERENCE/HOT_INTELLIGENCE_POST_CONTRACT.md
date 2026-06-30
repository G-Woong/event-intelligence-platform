# HOT_INTELLIGENCE_POST_CONTRACT (ADR#90)

> Status: **CONTRACT ONLY · RUNTIME No-Go**. 이 문서는 미래 제품(community-style intelligence post)의 field/gate
> 계약을 정의한다. **public post runtime 은 R1/R2 + MERGE_GATE 전까지 열리지 않는다.** 코드:
> `backend/app/tools/hot_intelligence_post_contract.py` (게시하지 않음 — 계약 검증만).

## 0. 왜 이 문서가 필요한가

이 프로젝트의 최종 목표는 raw news feed 가 아니라, 에이전트가 전세계 사건·사고·논쟁 중 **사람이 흥미로워할
정보**를 찾아 공식 증거·뉴스 교차·커뮤니티 반응·시장 신호·엔티티 맥락·시계열·불확실성을 통합해 **사람이 읽고
반응·댓글할 수 있는 intelligence post** 로 정제·게시하는 웹 인텔리전스다(`docs/0_ONBOARDING/00_MASTER_OVERVIEW`
PART 1, `13_COMMERCIALIZATION`, `19_SPEC §9 Agent Debate Layer`).

`INTELLIGENCE_UNIT_CONTRACT.md §2` 가 IU 구성(요약·official_evidence·news_corroboration·community_reaction·시장
신호·confidence)을 정의하지만, **post 로서의 필드**(why_it_is_hot·headline·public_readiness_status·reply_policy)는
없었다. 이 문서는 IU §2 를 **확장**(중복 0)해 Hot Intelligence Post 를 정의한다.

## 1. Field contract (21)

`hot_intelligence_post_contract.HOT_POST_FIELDS`:

```
post_id · event_id · post_status · headline · short_hook · why_it_is_hot
official_evidence · news_corroboration · timeline_updates · entity_context
community_reaction_layer · market_signal_layer · uncertainty_summary
human_label_status · merge_gate_status · source_agreement · source_disagreement
public_readiness_status · reply_policy · moderation_status · last_updated_at
```

IU §2 대비 **추가 필드**: `headline`, `why_it_is_hot`, `public_readiness_status`, `reply_policy`.

## 2. Gate rules (불변)

| 규칙 | 의미 |
|---|---|
| no public post before MERGE_GATE | gold→MERGE_GATE 통과 전 public_readiness=false |
| no official evidence → no authoritative claim | 공식 증거 없으면 단정 금지 |
| community reaction is reaction_to only | 커뮤니티는 verified event 뒤 `reaction_to` layer (anchor 금지) |
| market signal is signal only | 시장은 signal layer (anchor 금지) |
| catalog/entity is context only | 카탈로그/엔티티는 context (anchor 금지) |
| uncertainty must be visible | 불확실성 항상 노출 |
| human label provenance required | merged event 는 human label 출처 필수 |
| search URL candidate is not truth | fetch 전 search URL 은 truth 아님 |
| no post body before public-IU gate | 본문 생성 0 (runtime No-Go) |
| reply_policy disabled before community gate | 댓글 응답 runtime 전 reply_policy=disabled |

## 3. Anchor 정책

- **anchor_roles = {official, news}** — 이벤트 증거 기반이 될 수 있는 role.
- **non_anchor_roles** = community→`reaction_to` · market→`signal` · catalog/entity→`context` · search→`url_candidate`.
- `is_valid_anchor_role(role)` 는 official/news 만 True. community/market 를 anchor 로 쓰면 `evaluate_hot_post_readiness`
  가 위반(`community_reaction_used_as_anchor` / `market_signal_used_as_anchor`)으로 표면화.

## 4. Runtime No-Go (현 단계)

`build_hot_intelligence_post_contract()` 불변:

- `runtime_enabled=False` · `public_post_body_generated=False` · `llm_headline_generated=False`
- `reply_policy_default="disabled"` · `comment_auto_reply_enabled=False`
- `merge_allowed=False` · `public_iu_allowed=False` · `r2_r7_no_go=True`

`evaluate_hot_post_readiness(draft)` 는 **항상 `publishable=False`·`public_readiness_status=False`** 를 반환하고
(runtime disabled), draft 의 게이트 위반만 진단한다. 코드가 post 본문을 생성하지 않는다.

## 5. 언제 열리는가 (선행 게이트)

1. R1 production gold ≥ floor (live ≥200 / KO ≥50) — actual returned human labels.
2. MERGE_GATE 통과 (semantic identity·source agreement).
3. public-IU gate (`RAG_KG_ENTITY_GATE_CONTRACT §5`).
4. community interaction gate (`COMMUNITY_INTERACTION_FUTURE_GATE.md`) — 댓글/응답 runtime.

그 전까지 Hot Intelligence Post 는 **계약**으로만 존재한다.

## 6. Cross-links

- `INTELLIGENCE_UNIT_CONTRACT.md §2/§3` (확장 대상·community=반응 layer)
- `RAG_KG_ENTITY_GATE_CONTRACT.md §2/§4/§5` (reaction_to·attach-timing·public-IU gate)
- `AGENT_HOTNESS_REASONING_CONTRACT.md` (어떤 사건을 post 후보로 고를지)
- `COMMUNITY_INTERACTION_FUTURE_GATE.md` (댓글/응답 runtime gate)
- `HOT_POST_GATE_ALIGNMENT.md` (ADR#91·이 계약의 `evaluate_hot_post_readiness` 를 COMPOSE 해 public_readiness 를 R1/R2·gold·evidence 에 결속)
- `COMMUNITY_POSTING_ROADMAP_CONTRACT.md` (ADR#91·이 계약은 stage_2 draft·HOT_POST_GATE_ALIGNMENT 는 stage_3 gate)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (Agent Debate Layer)
