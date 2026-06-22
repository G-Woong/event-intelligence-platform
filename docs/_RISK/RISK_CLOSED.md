# RISK CLOSED (완전 종결 위험 — 흐름만)

> 종결조건(Closure)이 **충족되어 닫힌** risk 만 여기에 둔다. **상세 본문은 남기지 않는다** —
> "왜 위험이었고 어떻게 닫혔나"를 흐름 1~3줄로만 보존하고, 상세는 `docs/_ARCHIVE_SUPERSEDED/` 로 archive.
> 열린/부분종결 risk 는 `RISK_REGISTER.md`. 이 분리는 매 턴 `turn-closeout` 이 관리한다(`docs/Harness_Construction/04`).

형식(예시 — 실제 항목은 `###`로 시작):
```
R-<id> · <제목>  — CLOSED (날짜)
- 종결 근거: (코드 path / 테스트 / 정책)
- 흐름: (열림→완화→종결까지 1~3줄)
- 상세: docs/_ARCHIVE_SUPERSEDED/<원본> (있으면)
```

---

### R-HookOutputEncoding · Stop hook 한글 출력 깨짐(cp949 stdout)  — CLOSED (2026-06-19)
- 종결 근거: `turn_state_snapshot._nudge_message`(ASCII-safe 영문)+`json.dumps`(ensure_ascii=True), harness CLI 4종(`harness_doctor`/`dead_code_scan`/`docs_lifecycle_audit`/`closeout_sig`) stdout UTF-8 reconfigure. 테스트 `tests/test_harness_hooks.py`(`test_nudge_message_is_ascii`/`test_stop_hook_stdout_is_ascii`/doctor crash 회귀).
- 흐름: Stop feedback 한글이 cp949 stdout에서 mojibake(`����`)→운영성 실패 → nudge를 ASCII 영문화 + CLI 스크립트 UTF-8 reconfigure(doctor의 em-dash crash 포함) → stdout이 순수 ASCII로 디코드(깨짐 불가) 검증.

### R-CodeReviewLivePath · 일반 코드 변경 턴 `/code-review` 실호출·증거 적재  — CLOSED (2026-06-19)
- 종결 근거: harmless ingestion 변경(`ingestion/core/source_registry.py` 주석)→`audit_flagger` `code_review` flag 발생→**`/code-review` 스킬 라이브 실호출**→CRLF churn 1건(`scripts/harness_doctor.py`) 적발→수정. 결과를 `closeout_stamp.audit_evidence`(code_review) 적재.
- 흐름: flag/게이트만 관찰(미검증)→실제 코드턴에서 skill end-to-end 실행·finding·fix·evidence 적재 1회 관찰로 종결. 잔여 한계는 R-CloseoutTrust(evidence 자기보고)로 흡수.

### R-EnvLoadAsymmetry · 엔트리포인트 간 .env 로딩 비대칭  — CLOSED (2026-06-22)
- 종결 근거: `run_one_source.run_source()`(run_one_source/run_phase/run_all_phases 공통 funnel) + `run_production_orchestration.main()` 에 명시적 `load_env()`(idempotent setdefault) 배선. 테스트 `ingestion/tests/unit/test_entrypoint_env_bootstrap.py`(run_source가 load_env 호출 + 키 보유 시 opendart precheck None / 부재 시 NEEDS_API_KEY). 값 비노출(존재 여부만).
- 흐름: production 경로는 audit_api_key_readiness 부수효과로 정상이나 run_one_source/run_phase는 .env 미로드 → 키 보유 소스가 NEEDS_API 오판 → 진입부 load_env 배선 + 계약 테스트로 대칭화·종결(ingestion 1307 green).

### R-GdeltMainLoopResume · rate-limited 소스 메인루프 auto-resume 부재  — CLOSED (2026-06-22)
- 종결 근거: `production_state.decide_production_strategy(now=)` 가 `RESUMABLE_RATE_LIMIT_STATES`(EXTERNAL_RATE_LIMITED/COOLDOWN)의 cooldown(`_cooldown_elapsed`; memory→`cooldown_until` 파생) 만료 시 not_ready skip 면제→재probe. 429는 run_production_orchestration에서 rate_limited(실패 아님)로 분류 유지. 테스트 test_production_state/scheduler/orchestration_runner.
- 흐름: gdelt가 EXTERNAL_RATE_LIMITED에 영구 정체(메인 not_ready skip, 전용 closure 단일 의존) → 메인 플래너에 cooldown 만료→재probe 전이 추가(우회 0, 429=외부제한) → cooldown 경과 시 메인루프가 자동 재시도하며 종결.

### R-GdeltGovernorSplitBrain · gdelt host rate-limit governor 이중 상태(메인루프 vs closure)  — CLOSED (2026-06-22)
- 종결 근거: 신규 `ingestion/orchestration/host_rate_gate.py`(`HostRateGate` — host 키 단일 출처, file-backed `host_rate_gate.json`, decide/record 시 파일 재읽기로 cross-process 가시성, `record_call` 호출 직전 즉시 atomic 영속). gdelt host 3경로(`run_production_orchestration`·`run_final_source_closure`·`run_last_chance_source_resurrection`)가 동일 gate 공유. source-level governor(메인 900s / closure 10s) 의미 보존 + host floor만 추가(우회/병렬/tight-retry 0). 테스트 `ingestion/tests/unit/test_host_rate_gate.py`(8): 공유 가시성·spaced-probe ladder 보존·메인 cooldown 자동재개 보존·호출직전 last_call 기록(성공/실패 무관)·spacing 전 양경로 미호출·후 호출 가능·429=외부 provider rate limit. ingestion 1315 green.
- 흐름: 두 루프가 별도 governor 파일로 gdelt host cooldown을 각각 추적 → R-GdeltMainLoopResume 종결로 메인루프도 재probe하게 되어 동시가동 시 host 호출 교차 가능 → host 키 단일 출처 gate를 실제 호출 직전에 양 경로가 통과(record 즉시 영속)하도록 배선 → 한 루프의 호출을 다른 루프가 즉시 보고 spacing 내 호출을 막아 종결.

