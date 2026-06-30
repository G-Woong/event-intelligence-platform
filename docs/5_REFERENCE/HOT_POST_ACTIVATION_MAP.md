# HOT_POST_ACTIVATION_MAP (ADR#93)

> Status: **CONTRACT-ONLY/ACTIVATION GATE · runtime DISABLED · RUNTIME No-Go**. R1→R2 이후 public Hot Post runtime 이
> *어떤 순서의 게이트* 로 열리는지를 계약으로만 고정한다(이번 턴 runtime 0). 코드:
> `backend/app/tools/hot_post_activation_map.py` (`CONTRACT_VERSION="hot_post_activation_map_v1"`·게시 0·comment reply 0).

## 0. 목적

`community_posting_roadmap_contract`(제품 LIFECYCLE: evidence→label→post→reaction→reply)와 **구분**된다 — 이 모듈은
그 lifecycle 이 아니라 **public-runtime ACTIVATION GATE SEQUENCE**(내부 preview→공개 게시→댓글 응답이 *열리는* 게이트
순서)다. 게이트 요구를 재선언하지 않고 기존 상수/빌더를 COMPOSE 한다.

## 1. 진입점

```
build_hot_post_activation_map() -> dict
보조: sanitized_hot_post_activation_map(out) · main(--json)
```

## 2. 상태 vocab (`hot_post_activation_map_status`)

```
HPA_DEFINED_RUNTIME_DISABLED = "hot_post_activation_map_defined_runtime_disabled"
```

9 stage(순서 고정·각 stage = entry_conditions / allowed_actions / forbidden_actions / required_evidence /
runtime_status / next_gate):

```
stage_0_internal_preview_blocked
stage_1_r1_gold_available
stage_2_r2_merge_gate_passed
stage_3_hot_post_public_readiness_check
stage_4_internal_preview_allowed
stage_5_public_publish_candidate
stage_6_public_publish_requires_operator_approval
stage_7_community_reaction_attachment
stage_8_comment_reply_gate
```

## 3. 핵심 출력 필드

```
activation_stages · stage_order · stage_count(9)
public_readiness_requires_r1(True) · public_readiness_requires_r2(True)
references_hot_post_gate_requirements · comment_gate_requirements_count
```

## 4. 불변식 (절대 금지)

```
runtime_enabled=False · public_post_body_generated=False · comment_reply_generated=False
publish_requires_r1_r2=True · community_reaction_anchor=False
hotness_alone_publishable=False · r2_r7_no_go=True
```

- public publish 는 R1 AND R2 전 차단 · stage_6 operator 승인 필요 · stage_7 community-as-anchor 금지
  (`is_valid_anchor_role('community')`=False) · stage_8 comment reply 는 community gate 전 차단.

## 5. 합성하는 기존 모듈

- `hot_post_gate_alignment` (`HOT_POST_GATE_REQUIREMENTS`·R1=production_gold_available·R2=merge_gate_passed)
- `hot_post_preview_guard` (stage_0 preview 차단 증명)
- `community_interaction_future_gate` (stage_8 comment gate precondition)
- `is_valid_anchor_role` (stage_7 anchor 금지 결속·official/news only)

## 6. 이것이 아니다

- runtime 활성화가 **아니다** · public post 생성이 아니다.
- preview ≠ public(internal preview 는 public surface 를 열지 않는다).
- 게이트 요구를 재선언하지 않는다(gate 단일 출처 참조).

Status: ADR#93 · runtime 0
