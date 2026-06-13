---
name: runner-contract-skill
description: Verify ingestion runner output contracts before orchestration — required fields, agent_ready state, and graceful handling of malformed input. Ensures runners are safe to wire into Celery/LangGraph later.
when_to_use: Before orchestration implementation, after adding/modifying a runner, or when validating runner output for downstream wiring. Invoke to confirm 13/13 agent_ready and contract field presence.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
---

# runner-contract-skill

runner의 JSONL/output contract를 오케스트레이션 전에 검증한다.

## when_to_use
- 오케스트레이션(plans/012) 구현 전
- 신규 runner 추가 / runner 수정 후
- "runner 계약 / agent_ready / output 스키마" 류 점검

## procedure
1. **readiness 실행**: `run_runner_orchestration_readiness` (네트워크 없음)
2. **JSONL 분석**: agent_ready 상태 집계 (목표 13/13)
3. **output contract 필드 확인** (runner 결과 record):
   - source_id, status, collected, error_category, next_action
   - artifact_path, next_retry_at, body_status
   - candidates_created, related_candidates_created
4. **malformed input 견고성**: 신규 runner는 잘못된 입력에도 죽지 않고 error_category로 분류
5. agent_ready=False면 목록 추출 → source-ingestion-engineer 핸드오프

## commands
```powershell
.\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
Get-ChildItem ingestion\outputs\jsonl -Filter *runner_orchestration_readiness* | Sort-Object LastWriteTime -Descending | Select-Object -First 1
```

## failure conditions
- agent_ready < 13 → NOT_READY (해당 runner 목록 보고)
- contract 필수 필드 누락 → NOT_READY
- malformed input에 runner crash → NOT_READY

## success criteria
- 13/13 runner agent_ready = True
- 필수 contract 필드 모두 존재
- readiness JSONL artifact 생성 확인

## safety constraints
- rate_limit 무시 반복 실행 금지
- runner 결함을 PASS로 보고 금지
- source runner 코드를 이 skill에서 직접 수정하지 않음 (핸드오프만)
- git push 금지 / rm·Remove-Item 금지 / .env 값 출력 금지

## output format
```
표: runner | agent_ready | missing_fields | notes
종합: N/13 READY
verdict: PASS | NOT_READY
handoff: [source-ingestion-engineer에게 넘길 runner, ...]
```
