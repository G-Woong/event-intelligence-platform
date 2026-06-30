# COMMUNITY_FEEDBACK_LOOP_CONTRACT (ADR#93)

> Status: **CONTRACT-ONLY/LOOP SEQUENCE · runtime DISABLED · RUNTIME No-Go**. 미래 user-comment ↔ agent-followup
> 피드백 LOOP 의 순서를 계약으로만 기술한다(runtime 0·어떤 댓글도 생성·발송 0). 코드:
> `backend/app/tools/community_feedback_loop_contract.py` (`CONTRACT_VERSION="community_feedback_loop_v1"`).

## 0. 목적

유저가 intelligence post 에 댓글을 남기면 분류→moderation→질문/반응 판별→(질문이면) 에이전트가 *출처 있는* 후속
증거 수집→post 갱신/응답 후보→사람/정책 리뷰→(미래) 응답 게시→audit log 로 흐른다. moderation+privacy+audit+citation+
uncertainty 가 필수이고 agent follow-up 은 사실을 날조하지 못한다. 선행 요구 11개는 `community_interaction_future_gate`
가 단일 출처 — 이 모듈은 그것을 **COMPOSE**(11 요구 재선언 0)하며 *순서* 만 정의한다.

## 1. 진입점

```
build_community_feedback_loop_contract() -> dict
보조: sanitized_community_feedback_loop_contract(out) · main(--json)
```

## 2. 상태 vocab (`community_feedback_loop_status`)

```
CFL_DEFINED_RUNTIME_DISABLED = "community_feedback_loop_defined_runtime_disabled"
```

11 loop step(순서·각 step = step / description / requires(`COMMUNITY_GATE_REQUIREMENTS` 참조) / forbidden_now /
runtime_status):

```
user_comment_received · comment_classification · safety_moderation
question_or_reaction_detection · source_followup_needed · agent_followup_collection
post_update_candidate · human_or_policy_review · reply_candidate · reply_publish_gate · audit_log
```

## 3. 핵심 출력 필드

```
loop_steps · loop_step_order · loop_step_count(11)
references_community_interaction_gate · community_gate_requirements_count
moderation_required · privacy_gate_required · audit_log_required
source_citation_required · uncertainty_required (전부 True) · agent_followup_can_fabricate_facts(False)
```

## 4. 불변식 (절대 금지)

```
runtime_enabled=False · comment_auto_reply_enabled=False
reply_generated=False (gate passthrough) · user_comment_runtime_open=False
community_is_evidence_anchor=False · r2_r7_no_go=True
```

- `runtime_enabled`·`reply_generated` 는 gate 의 `runtime_enabled`·`comment_reply_generation`(둘 다 항상 False)
  passthrough — 응답 생성 0.

## 5. 합성하는 기존 모듈

- `community_interaction_future_gate` (`COMMUNITY_GATE_REQUIREMENTS` 11요구 단일 출처 ·
  `comment_reply_generation`/`runtime_enabled` passthrough)

## 6. 이것이 아니다

- runtime 이 **아니다** · reply 생성이 아니다.
- 요구를 재선언하지 않는다(gate 참조 — 새 requirement 발명 시 fail-loud).
- community 는 reaction_to only(evidence anchor 아님).

Status: ADR#93 · runtime 0
