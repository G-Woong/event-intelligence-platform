# OPERATOR_LIVE_COMMAND_PACK (ADR#93)

> Status: **COMMAND PACK/STRING-ONLY · validate≠dry-run≠live · RUNTIME No-Go**. operator 가 validate-only / dry-run /
> live-run 을 혼동하지 않도록 세 명령을 *문자열로만* 묶는다 — validate/dry-run 은 network 0, live-run 은
> valid∧live_approved=true 를 요구하고 실행 *전* bounded provider 수+목록을 보여준다. 코드:
> `backend/app/tools/operator_live_command_pack.py` (명령 문자열만 emit·실행 0).

## 0. 목적

"지금 무엇을 치면 network 0 검증이고 무엇이 진짜 live 호출인가" 를 한눈에 구분할 단일 출처가 없었다. 이 모듈은
명령 문자열만 EMIT 한다(실행 0). 두 경로: operator_event(date-pinned)가 있으면 guardian/nyt 2 calls, 없으면
regulatory seed(federal_register + guardian/nyt) 3 calls.

## 1. 진입점

```
build_operator_live_command_pack(*, operator_event=None,
                                 real_payload_path=REAL_PAYLOAD_PATH,
                                 batch_id=DEFAULT_BATCH_ID) -> dict
보조: sanitized_operator_live_command_pack(out)
     main(--named-entity / --event-phrase / --occurrence-date / --event-json / --batch-id / --json)
```

`real_payload_path` 는 존재(stat)만 본다(본문 미독·secret 미접근).

## 2. 상태 vocab (`operator_live_command_pack_status`)

```
OLC_READY           = "command_pack_ready"                          # date-pinned operator_event 제공
OLC_PAYLOAD_PRESENT = "command_pack_ready_real_payload_present"     # event 없음·real payload 존재
OLC_NO_EVENT        = "command_pack_ready_no_event_template_only"   # event 없음·payload 없음(author 먼저)
```

## 3. 핵심 출력 필드

```
validate_payload_command · dry_run_command · live_run_command
expected_provider_calls(int) · provider_list · news_enforce_window_noted(True)
rate_limit_notes · output_paths(gitignored) · rollback_notes · next_action
```

- `rate_limit_notes` 는 `adapter_descriptor`(host min_spacing·하드코딩 0) 기반 + 운영 pacing floor(guardian≥6·nyt≥13 권장).
- validate-only/dry-run 명령에는 `--live-query` 가 없다 — live 명령만 live opt-in 을 가진다.

## 4. 불변식 (절대 금지)

```
validate_only_calls_network=False · dry_run_calls_live_network=False
live_run_requires_approved_payload=True
secret_in_command_pack=False · raw_payload_text_in_pack=False
routes_through_ungated_fidelity_probe=False
```

- live 명령은 approval-gated `operator_confirmed_live_runner` 만 가리킨다 — `provider_date_window_fidelity`
  (payload-gated 아님·승인 없이 호출 가능)로 라우팅하지 않는다(assert 로 결속).

## 5. 합성하는 기존 모듈

- `live_query_target` (provider_list·validity verdict·PURE·network 0)
- `provider_query_adapters` (`adapter_descriptor` host rate·단일 출처)
- `reviewer_batch_launch` (`build_intake_plan` output path)

## 6. 이것이 아니다

- live 실행이 **아니다** — string builder 일 뿐이다.
- dry-run 은 live network 가 아니다 · validate-only 는 network 0.
- fidelity probe 경유가 아니다(ungated 호출 금지).

Status: ADR#93 · runtime 0
