# FIRST_LIVE_FREEZE_R1_DRY_RUN_HARNESS (ADR#94 §13)

> Status: **DRY-RUN/SYNTHETIC · NEVER production gold · RUNTIME No-Go**. 합성/가짜 freeze 후보로 freeze→hardening→R1
> 체크리스트 경로를 미리 한 번 통과시켜 경로가 *깨지지 않음* 을 증명한다(진짜 live 후보가 나타나기 전 안전망). 코드:
> `backend/app/tools/first_live_freeze_r1_dry_run_harness.py` (전송 0·reviewer roster 미커밋·merge 0·network 0·gold 0).

## 0. 목적

freeze package hardening(§11)과 freeze→R1 executable checklist(§12)는 준비됐으나, *실제* live production candidate 가
아직 0 이라 그 전체 경로가 한 번도 end-to-end 로 실행된 적이 없다 — 진짜 후보가 나타나는 바로 그 순간 경로가 깨져
있으면 늦다. 이 모듈은 **합성/가짜(synthetic/fake)** freeze 후보(`iter_freeze_eligible_record_pairs` 형태)를 만들어
hardening→R1 체크리스트 경로를 미리 한 번 통과시킨다. 합성은 reviewer worklist 흉내일 뿐 **절대 production gold 가
아니다** — gold 는 진짜 returned human label + ≥2-reviewer 합의 전까지 0 으로 고정된다.

## 1. 진입점

```
build_first_live_freeze_r1_dry_run_harness(*, synthetic_pair=None, batch_id=None) -> dict
보조: sanitized_first_live_freeze_r1_dry_run_harness(out) · main(--batch-id / --json)
```

`synthetic_pair` 미제공 시 `_default_synthetic_pair()`(SAFE·allowlist 키만·내용이 명백히 SYNTHETIC 표식) 사용.

## 2. 상태 vocab (`freeze_r1_dry_run_status`)

```
DRY_RUN_READY    = "synthetic_freeze_r1_dry_run_ready"   # safe 합성 → 체크리스트 통과(경로 살아있음).
DRY_RUN_REJECTED = "synthetic_artifact_rejected"         # unsafe 합성 → 거부(경로 guard 가 결함을 막음).
```

safe → `build_freeze_to_r1_executable_checklist` 통과 · unsafe(forbidden/extra 키·canonical 누락) → 체크리스트 미생성.

## 3. 핵심 출력 필드

```
freeze_r1_dry_run_status · synthetic_or_fake(True) · freeze_candidate_present · freeze_artifact_safe
freeze_package_hardening_status · freeze_to_r1_status · batch_id · batch_id_consistent
label_dropbox_ready · validation_command_ready · intake_command_ready · agreement_command_ready
production_gold_count · blocked_reason · all_blockers · next_action
```

- `production_gold_count` 는 freeze→R1 bridge **exact passthrough** — 합성이어도 0(증가 0).
- `batch_id` 는 `DEFAULT_BATCH_ID` 재사용 · 명령/배치 id 재저작 0(단일 출처).

## 4. 불변식 (절대 금지·합성은 진짜가 아니다)

```
synthetic_or_fake=True · is_production_gold=False · actual_sending_performed=False
reviewer_roster_committed=False · real_label_counted=False · merge_allowed=False · network_invoked=False
```

- 출력은 flag/status/count 만 담고 합성 record 본문을 echo 하지 않는다(`_assert_pii_safe` 재귀 가드).
- 이번 턴: real payload 미존재가 정직한 block · production_gold_count 불변 0 · R1 gap 200 · R2~R7 No-Go ·
  LLM/embedding/merge/DB/public-IU/Hot-Post/comment runtime disabled.

## 5. 합성하는 기존 모듈

- `first_freeze_package_hardening` (reviewer-facing 안전성 검사·unsafe 합성 거부)
- `freeze_to_r1_executable_checklist` (safe 일 때 contact→label→gold 명령 준비·production_gold_count passthrough)
- batch id = `r1_label_return_operational_bridge.DEFAULT_BATCH_ID` · `reviewer_pilot_handoff._assert_pii_safe`
- 테스트: `backend/tests/test_first_live_freeze_r1_dry_run_harness.py` — 13개(전부 통과).

## 6. 이것이 아니다

- production gold 가 **아니다** — 합성은 항상 `synthetic_or_fake=True`·gold 0 으로 표식된다.
- 발송/merge/gold 생성/디스크 쓰기/secret 읽기를 하지 않는다 · reviewer roster 미커밋.
- 진짜 live 후보의 대체가 아니다 — 후보가 frozen 되면 *같은 경로* 를 그 위에 다시 돌려야 한다.

Status: ADR#94 · runtime 0
