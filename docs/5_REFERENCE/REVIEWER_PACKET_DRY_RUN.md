# REVIEWER_PACKET_DRY_RUN (ADR#95)

> Status: **DRY-RUN/SHAPE-ONLY · 전송 0 · reviewer PII/score 0 · gold 0 · RUNTIME No-Go**. freeze 가 성공하면 reviewer
> 가 받을 packet 의 *모양*을 SAFE dry-run 으로 조립한다 — 진짜 freeze 가 없으면 production packet 은 BLOCKED, 그렇다고
> 가짜 gold 도 만들지 않는다. 코드: `backend/app/tools/reviewer_packet_dry_run.py` (sending 0·merge 0·network 0·
> disk write 0·secret 0).

## 0. 목적

freeze→handoff bridge·hardening·freeze→R1 checklist 는 준비됐으나, "freeze 가 진짜로 성공했을 때 reviewer 가 받는
**packet 그 자체의 모양**"을 operator 가 미리 한 화면에서 보지 못했다. 진짜 freeze 가 없으면 production packet 을 만들
수 없고(BLOCKED), 모양 확인을 위해 가짜 gold 를 만들어서도 안 된다. 이 모듈은 그 간극을 dry-run 으로 메운다 —
진짜 freeze 면 production packet, 없고 synthetic=True(기본)면 명백히 SYNTHETIC 표식 packet, 없고 synthetic=False 면
정직하게 BLOCKED. 어떤 경로도 발송/merge/gold/디스크/secret 를 건드리지 않는다.

## 1. 진입점

```
build_reviewer_packet_dry_run(*, production_candidate=None, synthetic=True, batch_id=None) -> dict
보조: sanitized_reviewer_packet_dry_run(out) · main(--batch-id / --no-synthetic / --json)
```

## 2. 상태 vocab (`reviewer_packet_dry_run_status` · 4-state)

```
PACKET_SYNTHETIC_DRY_RUN = "synthetic_reviewer_packet_dry_run_ready"   # 진짜 freeze 없음 + synthetic=True
PACKET_PRODUCTION_READY  = "production_reviewer_packet_ready"          # 진짜 freeze → handoff bridge packet
PACKET_BLOCKED_NO_FREEZE = "blocked_no_production_candidate_freeze"    # freeze 없음 + synthetic=False
PACKET_BLOCKED_UNSAFE    = "blocked_freeze_artifact_unsafe"            # record pair 가 hardening 실패
```

진짜 freeze gate = `production_candidate_batch_ready` ∧ `production_batch_id` ∧ `production_frozen_pair_count`>0.

## 3. 핵심 출력 필드

```
reviewer_packet_dry_run_status · synthetic_or_fake · is_production · batch_id · candidate_count
official_news_role_explanation · label_instruction · expected_return_file_pattern · dropbox_path
validation_command · intake_command · forbidden_fields_hidden · packet · blocked_reason · next_action
```

- `packet` 은 safe 필드만 담고 forbidden field 는 부재 — score/rationale/predicted_status/same_event_truth/raw_body/
  reviewer_pii 는 `*_hidden=True` 선언만 보인다.
- synthetic packet 은 `synthetic_or_fake=True`·`is_production=False`(절대 production gold 아님) · BLOCKED 는 packet=None.

## 4. 불변식 (절대 금지·synthetic ≠ production ≠ gold)

```
actual_sending_performed=False · reviewer_roster_committed=False · merge_allowed=False
score_hidden · rationale_hidden · predicted_status_hidden · same_event_truth_hidden · raw_body_hidden · reviewer_pii_hidden (전부 True)
network_invoked=False · production_gold_count=0
```

- 어떤 채널로도 자동 발송 0(operator 수동 배포) · 반환 직전 `_assert_pii_safe` 재귀 가드가 forbidden-key 0 을 보장
  (poisoned 후보가 끼면 handoff bridge 의 가드가 fail-loud).
- 이번 턴: 진짜 freeze 미존재가 정직한 block · R1 gap 200 · R2~R7 No-Go · LLM/embedding/merge/DB/public-IU/Hot-Post/
  comment runtime disabled.

## 5. 합성하는 기존 모듈

- `reviewer_handoff_bridge.build_reviewer_handoff_bridge` (production packet 모양 + freeze gate 단일 출처).
- `first_live_freeze_r1_dry_run_harness` (synthetic safe 후보) · `first_freeze_package_hardening`
  (record pair 가 있을 때만 reviewer-facing 안전성 검사·unsafe 면 미방출).
- `r1_label_return_operational_bridge` (`DEFAULT_BATCH_ID`·`intake_command` 미러·import 격리) ·
  `reviewer_batch_launch.build_intake_plan` · `reviewer_pilot_handoff._assert_pii_safe`.
- 테스트: `backend/tests/test_reviewer_packet_dry_run.py` — 15개(전부 통과).

## 6. 이것이 아니다

- 발송이 **아니다**(actual_sending_performed=False·reviewer_roster_committed=False) · reviewer PII/score/rationale/
  predicted_status/same_event_truth/raw_body 를 담지 않는다.
- synthetic packet 은 production 도 gold 도 아니다 · 진짜 freeze 없이는 production packet 을 만들지 않는다.
- merge 0 · network 0 · 디스크 쓰기 0 · secret 0 · production gold 0 — 모양을 보여줄 뿐 gold 가 생기지 않는다.

Status: ADR#95 · runtime 0
