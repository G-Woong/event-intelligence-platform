# FREEZE_TO_R1_EXECUTABLE_CHECKLIST (ADR#93)

> Status: **CHECKLIST/EXECUTABLE-CLI · no sending · RUNTIME No-Go**. production-candidate freeze 가 성공한 순간
> reviewer contact→returned label→R1 gold 까지를 *실행 가능한* operator checklist + CLI 명령으로 묶는다. 코드:
> `backend/app/tools/freeze_to_r1_executable_checklist.py` (전송 0·gold 0·network 0).

## 0. 목적

freeze→contact/dropbox/intake/gold 조각과 8단계 protocol(산문)은 준비됐으나, freeze 성공 *바로 그 순간* operator 가
"어떤 명령을 순서대로 치면 contact→label→gold 인가" 를 실행 가능한 명령으로 받지 못했다. 이 모듈이 그 간극을 잇는다
— actual sending 0 · reviewer roster 미커밋 · single/unsure ≠ gold · 실 label 전 `production_gold_count` 불변
(명령/배치 id 재저작 0·단일 출처 재사용).

## 1. 진입점

```
build_freeze_to_r1_executable_checklist(*, freeze_artifact=None, batch_id=DEFAULT_BATCH_ID,
                                        production_gold_count_before=0,
                                        production_gold_count_after=0) -> dict
보조: sanitized_freeze_to_r1_executable_checklist(out) · main(--batch-id / --json)
```

실 freeze artifact 형상 = `iter_freeze_eligible_record_pairs`(pair_id·official_record·news_record·shared_tokens·date_proximity_days).

## 2. 상태 vocab (`freeze_to_r1_status`)

```
FR1_READY                   = "freeze_to_r1_checklist_ready"
FR1_BLOCKED_NO_FREEZE       = "blocked_no_production_candidate_freeze"
FR1_BLOCKED_UNSAFE_ARTIFACT = "blocked_freeze_artifact_unsafe"
FR1_BLOCKED_BATCH_MISMATCH  = "blocked_freeze_batch_mismatch"
```

## 3. 핵심 출력 필드

```
freeze_to_r1_status · batch_id · freeze_batch_id · batch_id_mismatch · freeze_artifact_safe
reviewer_contact_checklist_ready · manual_contact_steps · dropbox_path
expected_returned_file_pattern(*.jsonl) · label_validation_command · label_intake_command
agreement_check_command(=label_intake_command) · gold_promotion_gate_status · production_gold_count · next_action
```

- batch_id 분기: contact lane = `DEFAULT_BATCH_ID`("operator_regulatory_live") · freeze = `PROD_BATCH_ID`
  ("reviewer_prod_cand_001") — 둘이 다르면 혼합 금지·`batch_id_mismatch` 표면화·blocked.
- `agreement_check_command` == `label_intake_command`(`agreement_performed_by_intake_run=True` — 별도 CLI 없음).
- `production_gold_count` 는 bridge exact passthrough.

## 4. 불변식 (절대 금지)

```
actual_sending_performed=False · reviewer_roster_committed=False
single_reviewer_label_is_gold=False · unsure_label_is_gold=False
agreement_required_for_gold=True · gold_promotion_gated=True
```

- `production_gold_count` 는 실 returned human label + 2-reviewer 합의 전까지 0.

## 5. 합성하는 기존 모듈

- `r1_label_return_operational_bridge` (명령/경로/패턴/gold passthrough 단일 출처)
- `first_freeze_package_hardening` (freeze artifact reviewer-facing 안전성)
- `reviewer_contact_launch_checklist` (manual contact steps)

## 6. 이것이 아니다

- freeze artifact ≠ gold · checklist ready ≠ actual contact.
- agreement 별도 CLI 가 **아니다** — intake run 안에서 수행된다.
- 코드가 발송/merge/gold 생성/디스크 쓰기를 하지 않는다.

Status: ADR#93 · runtime 0
