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
