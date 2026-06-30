# COMMUNITY_POSTING_ROADMAP_CONTRACT (ADR#91)

> Status: **CONTRACT ONLY · RUNTIME No-Go**. 최종 커뮤니티형 제품의 게시→반응→댓글→후속수집 경로를 **8단계 순서**로
> 고정한다. 코드: `backend/app/tools/community_posting_roadmap_contract.py` (게시·응답 0).

## 0. 왜 필요한가

`COMMUNITY_INTERACTION_FUTURE_GATE.md` 는 runtime 개방의 11개 요구를 **flat checklist** 로 정의한다. 그러나 제품은
증거→gold→merge→게시→커뮤니티 반응→moderation→댓글 응답→후속 수집이라는 **순서** 가 있어야 안전하게 열린다. 이
문서는 그 *순서* 를 8단계 roadmap 으로 박는다(gate 와 DISTINCT — terminal 단계가 그 gate 를 precondition 으로 참조).

## 1. 8단계 (`STAGE_ORDER`)

```
stage_0_internal_evidence_pipeline      → 수집/bridge/overlap 진단(merge·publish 0)
stage_1_reviewer_gold_and_merge_gate    → R1 gold(≥2 reviewer 합의) + R2 MERGE_GATE
stage_2_hot_intelligence_post_draft_contract → Hot Post draft field 조립(본문 생성 0)
stage_3_public_readiness_gate           → HOT_POST_GATE_ALIGNMENT 11개 요구(publish 0)
stage_4_community_reaction_attachment   → community 반응을 reaction_to layer 로만 부착(anchor 0)
stage_5_moderation_and_safety_gate      → moderation/abuse/privacy 정책(댓글 응답 전 필수)
stage_6_comment_reply_gate              → community_interaction_future_gate.all_requirements_met 참조(runtime 0)
stage_7_agent_followup_collection       → 후속 수집(source policy + rate limit·사실 날조 0)
```

각 단계는 7필드를 갖는다: `entry_conditions · allowed_actions · forbidden_actions · evidence_requirements ·
human_label_requirements · runtime_status · next_gate`.

## 2. 현 상태 (불변)

`build_community_posting_roadmap_contract()`:

- `community_posting_roadmap_status` = `community_posting_roadmap_defined_runtime_disabled`.
- `runtime_enabled=False` · `public_post_runtime_enabled=False` · `comment_reply_generation=False` ·
  `comment_reply_runtime_open=False` (전 단계 `publish_runtime="disabled"` · `comment_reply_runtime="disabled"`).
- `community_reaction_anchor=False` · `agent_followup_fabricates_facts=False` · `publish_requires_r1_r2=True`.
- `privacy_user_data_gate_required=True` · `moderation_gate_required=True` · `audit_log_required=True`.

## 3. 경계 규칙 (§14)

```
public readiness 전 게시 0 (stage_3 전 publish 금지)
moderation 전 댓글 응답 0 (stage_5 가 stage_6 보다 먼저)
community reaction 은 reaction_to only (stage_4·anchor 금지)
agent follow-up 은 사실 날조 0 (stage_7·source policy + rate limit 필수)
user data/privacy · moderation · audit log gate 필수
```

terminal 단계(stage_6/7)는 `community_interaction_future_gate` 의 `all_requirements_met` 를 **참조** 한다 — 11개 요구를
재나열하지 않는다(그 gate 가 단일 출처).

## 4. Cross-links

- `COMMUNITY_INTERACTION_FUTURE_GATE.md` (11개 요구의 단일 출처·stage_6 precondition)
- `HOT_POST_GATE_ALIGNMENT.md` (stage_3 public_readiness gate)
- `HOT_INTELLIGENCE_POST_CONTRACT.md` (stage_2 draft contract)
- `RAG_KG_AGENT_READINESS.md §6b` (stage_1 R1 gold + R2 MERGE_GATE floor)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (커뮤니티형 제품 방향·debate/comment layer)
