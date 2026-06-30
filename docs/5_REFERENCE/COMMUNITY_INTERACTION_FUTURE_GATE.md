# COMMUNITY_INTERACTION_FUTURE_GATE (ADR#90)

> Status: **CONTRACT ONLY · RUNTIME No-Go**. 유저 댓글/에이전트 응답 runtime 이 *언제* 열릴 수 있는지의 선행
> 게이트를 조립한다. 코드: `backend/app/tools/community_interaction_future_gate.py` (댓글 생성·발송 0).

## 0. 미래 목표 vs 현 단계

미래: 유저가 intelligence post 에 댓글을 달고, 에이전트가 근거를 들어 응답하고, 반응을 보고 후속 수집/글을
갱신한다. 현 단계: **runtime No-Go** — 댓글 응답 생성 0·자동 발송 0·LLM 0. 지금은 evidence/gold/MERGE_GATE 를
닦는 단계이며, community 반응은 verified event 뒤 `reaction_to` layer 로만 붙는다(anchor 금지).

## 1. 개방 전 선행 요구 (11)

`COMMUNITY_GATE_REQUIREMENTS`:

```
verified_event · public_iu_gate_passed · moderation_policy · abuse_spam_guard
privacy_user_data_policy · reply_provenance · source_citation_policy · uncertainty_policy
human_override · rate_limit · audit_log
```

이 전부가 갖춰지고, 그 위에서 public-IU/MERGE_GATE 가 통과한 **뒤에만** community interaction runtime 을 검토한다.

## 2. 현 상태 (불변)

`build_community_interaction_future_gate()`:

- `runtime_enabled=False` · `comment_reply_generation=False` · `comment_auto_reply_enabled=False` ·
  `user_comment_runtime_open=False`
- `community_is_evidence_anchor=False` · `llm_invoked=False` · `merge_allowed=False` · `r2_r7_no_go=True`
- `community_interaction_gate_status` ∈ {`community_interaction_requirements_unmet`,
  `community_interaction_runtime_disabled`} — **all_requirements_met 이어도 runtime 은 disabled**(public-IU/MERGE_GATE
  가 아직 No-Go).

## 3. 선행 게이트 시퀀스

1. R1 production gold ≥ floor (actual returned human labels).
2. MERGE_GATE (semantic identity).
3. public-IU gate (`RAG_KG_ENTITY_GATE_CONTRACT §5`).
4. Hot Intelligence Post 게시 (`HOT_INTELLIGENCE_POST_CONTRACT.md`, public_readiness=true).
5. **이 문서의 11개 요구** + moderation/privacy/abuse/audit → community interaction runtime.

## 4. 정책 비고

- 응답은 근거(reply_provenance)와 출처 인용(source_citation_policy)을 동반해야 하며, 불확실성을 표기한다.
- rumor 와 fact 를 절대 섞지 않는다(community buzz 는 evidence anchor 아님).
- 투자 조언·매수/매도 추천을 출력하지 않는다(`19_SPEC §9.3` blocking regression 과 정합).
- human_override·rate_limit·audit_log 가 항상 켜진다.

## 5. Cross-links

- `RAG_KG_ENTITY_GATE_CONTRACT.md §2/§4/§5` (reaction_to·attach-timing·public-IU gate)
- `HOT_INTELLIGENCE_POST_CONTRACT.md §2/§4` (reply_policy disabled·public_readiness)
- `AGENT_HOTNESS_REASONING_CONTRACT.md §2` (community_layer_requirements)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9.3` (debate 수용 기준·investment-advice/evidence-less blocking)
