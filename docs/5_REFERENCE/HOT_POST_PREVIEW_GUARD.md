# HOT_POST_PREVIEW_GUARD (ADR#92)

> Status: **GUARD · RUNTIME No-Go**. 내부 preview 가 public post 와 혼동되거나 실수로 게시되지 않게 보호한다(body/reply
> 생성 0·게시 0). 코드: `backend/app/tools/hot_post_preview_guard.py` (public 항상 차단).

## 0. 왜 필요한가

최종 목표는 커뮤니티형 Hot Intelligence Post 지만, R1/R2 전에는 public 게시가 없다. 운영 중 reviewer/operator 가 보는
내부 preview(draft)가 생기더라도 그것이 public post 와 혼동되거나 실수로 게시되면 안 된다. 이 모듈은 그 경계를 지키는
**preview guard** 로, `build_hot_post_gate_alignment` + `build_community_interaction_future_gate` +
`is_valid_anchor_role` 를 합성한다(재구현 0).

## 1. internal-only preview structural 검사

다음 4개를 **전부** 통과해야 internal-only preview 가 허용된다(통과해도 public 은 막힌다):

```
official evidence anchor present   (hotness/community 단독은 preview 불가)
uncertainty summary present        (preview 전 필수)
community is reaction_to only      (community 를 anchor 로 사용 0)
source role guard passed           (anchor 는 official/news 여야 함)
```

- hotness-only · community-only draft 는 거부된다(preview 불가).
- `hot_post_preview_status` ∈ {`preview_blocked_fix_draft`(structural 미충족), `preview_internal_only_public_blocked`
  (structural 충족·public 차단)}.

## 2. 현 상태 (불변)

`build_hot_post_preview_guard(draft=None)`:

- `public_post_body_generated=False` · `comment_reply_generated=False` (body/reply 생성 0·placeholder only).
- `hot_post_preview_public_blocked=True` (이 턴 **항상**) — preview 는 NEVER publishable.
- `preview_publishable=False` · `preview_asserts_same_event=False` · `runtime_enabled=False` · `merge_allowed=False`.

## 3. public 게시 선행 게이트

preview → public 전환은 다음을 *모두* 요구한다(이 턴 전부 미충족·사유는 `requires_*` 로 표면화):

```
R1 production gold floor (live ≥200 / KO ≥50·actual returned human labels)
R2 MERGE_GATE (precision ≥0.98·FPR ≤0.01·hard-neg FP=0)
Hot Post public_readiness (11 requirements)
```

## 4. Known separate path (out of scope)

`backend/app/api/ai_replies.py` 는 **LEGACY·MOCK-ONLY** `POST /api/ai-replies/request` 를 노출한다
(`LLMClient(provider="mock")` · event-level). 이 엔드포인트는 **이 guard 나 community interaction gate 의 통제를 받지
않는다**. public post body 를 생성하지 않으며 ADR#92 범위 밖이다. 권고: 후속 ADR 에서 이 path 를 preview guard /
community interaction gate 아래로 편입. (이 문서는 기록만 — `ai_replies.py` 를 수정하지 않는다.)

## 5. Cross-links

- `HOT_POST_GATE_ALIGNMENT.md` (public_readiness 11개 요구·이 guard 가 COMPOSE)
- `COMMUNITY_INTERACTION_FUTURE_GATE.md` (comment reply 0 의 단일 출처)
- `LIVE_ATTEMPT_PACK_CONTRACT.md` · `R1_FIRST_CONTACT_PROTOCOL.md` (gold 이전 sourcing/reviewer 단계)
- `RAG_KG_AGENT_READINESS.md §6b` (R1 gold + R2 MERGE_GATE floor·현재 R1=FAIL·R2~R7 No-Go)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (Hot Post / 커뮤니티형 제품 방향)
