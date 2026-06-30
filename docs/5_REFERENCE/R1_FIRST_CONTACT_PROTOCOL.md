# R1_FIRST_CONTACT_PROTOCOL (ADR#92)

> Status: **PROTOCOL/CONTRACT · no sending · RUNTIME No-Go**. freeze→reviewer 접촉→label 회수→gold 승격의 end-to-end
> 운영을 **8단계 순서**로 고정한다(어떤 단계도 발송 0). 코드: `backend/app/tools/r1_first_contact_protocol.py` (전송 0·gold 0).

## 0. 왜 필요한가

freeze→reviewer contact/dropbox/intake/gold 의 각 조각은 ADR#88~#91 에서 준비됐으나, 실제 reviewer 와 *접촉 전후*
무엇을 어떤 순서로 하고 무엇이 금지인지 — 그 **end-to-end protocol** 이 한 곳에 product-quality 로 정리돼 있지 않았다.
이 문서는 그 순서를 8단계로 박는다(`community_posting_roadmap` 의 stage tuple + `_assert_pii_safe` 메커니즘 재사용·
명령/경로는 단일 출처 재사용).

## 1. 8단계 (`STAGE_ORDER`)

```
stage_0_freeze_ready                → hardened reviewer worklist 검토(freeze 를 truth/gold 로 취급 0)
stage_1_select_reviewer_outside_git → roster 밖(git 미커밋)에서 pair 당 ≥2 pseudonymous reviewer 선택
stage_2_manual_contact              → 수동 접촉(code 가 email/slack/webhook 발송 0)
stage_3_return_label_to_dropbox     → reviewer label JSONL 을 gitignored dropbox 로 회수
stage_4_validate_returned_label     → 회수 label schema/coverage 검증(무효 import 0)
stage_5_intake_to_r1_candidate      → 검증 label import → R1 gold 승격 시도
stage_6_agreement_check             → ≥2-reviewer 합의(unanimous=agreed·conflict=human adjudication)
stage_7_gold_promotion_gate         → 합의 decisive label 만 explicit gate 로 gold 승격
```

각 단계는 6필드를 갖는다: `entry_condition · allowed_action · forbidden_action · artifact_path · privacy_rule ·
next_command`. dropbox 는 `outputs/reviewer_batch/<batch_id>/intake` (gitignored).

## 2. 현 상태 (불변)

`build_r1_first_contact_protocol(batch_id="operator_regulatory_live", freeze_ready=False)`:

- `r1_first_contact_protocol_status` ∈ {`protocol_defined_awaiting_freeze`, `protocol_defined_freeze_ready`} — 현재
  freeze 미충족 → `awaiting_freeze`.
- `actual_sending_performed=False` (어떤 단계도 발송 0·접촉은 수동) · `reviewer_roster_committed=False` (roster 는 git
  밖·pseudonym 만 노출).
- `single_reviewer_label_is_gold=False` · `unsure_label_is_gold=False` · `agreement_required_for_gold=True` ·
  `gold_promotion_gated=True`.
- `production_gold_count=0` (실 returned human labels + 2-reviewer 합의 전까지 0) · `merge_allowed=False` ·
  `same_event_asserted=False`.

## 3. 경계 규칙

```
reviewer roster 는 git 미커밋 (real name/email/phone 0·pseudonym only)
returned label 은 gitignored dropbox 로만 회수 (reviewer_id/rationale PII 미커밋)
single reviewer 또는 unsure/needs_more_context label 은 절대 gold 아님
≥2-reviewer 합의 필수 · gold 승격은 explicit gate
production_gold_count 는 실 returned human labels 가 합의 통과 전까지 0
```

- shared `batch_id="operator_regulatory_live"` 는 returned-label dropbox + R1 label-return bridge 와 정렬된다(같은 batch
  관례). `validation_command`/`intake_command` 는 단일 출처 재사용(stage 가 재정의 0).
- gold 승격 후에도 R2 MERGE_GATE(precision ≥0.98·FPR ≤0.01·hard-neg FP=0) 전까지 merge 0.

## 4. Cross-links

- `LIVE_ATTEMPT_PACK_CONTRACT.md` (freeze 이전·operator-fill→live 후보 pack)
- `HOT_POST_GATE_ALIGNMENT.md` (gold→merge 이후 public_readiness gate)
- `COMMUNITY_POSTING_ROADMAP_CONTRACT.md` stage_1 (R1 gold + R2 MERGE_GATE 단계)
- `RAG_KG_AGENT_READINESS.md §6b` (R1 gold floor·현재 R1=FAIL·R2~R7 No-Go)
- `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9` (커뮤니티형 제품 방향)
