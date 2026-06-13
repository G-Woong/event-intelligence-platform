---
name: source-audit-skill
description: Audit source collection health — checklist status, rate-limit/cooldown compliance, fallback chain, body extraction, and runner readiness. Live calls only when rate gate allows. Never bypass provider limits.
when_to_use: When verifying source health, after adding/modifying a source, when diagnosing a collection issue, or during a routine audit. Invoke to produce a per-source status table grounded in artifacts and policy.
user-invocable: true
allowed-tools: Bash, Read, Grep, Glob
---

# source-audit-skill

소스 수집 상태, rate-limit, fallback chain, body extraction, artifact를 점검한다.
이 skill은 수집 정책을 우회하지 않고 정책 준수 상태를 확인하는 runbook이다.

## when_to_use
- 소스 health 이슈, 신규 소스 추가/수정 후, 정기 감사
- "소스 상태 / 수집 점검 / 어떤 소스가 살아있나" 류 요청

## procedure
1. **checklist 확인**: `docs/ingestion/70_source_status_master.md` 판정 기준 + `IMPLEMENTATION_TRACE_FINAL.md` §3 (PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1)
2. **role/registry 확인**: `source_registry.yaml`, `docs/ingestion/86_source_role_classification_matrix.md`
3. **rate-limit 정책 확인**: `ingestion/configs/rate_limit_policy.yaml`
   - gdelt: PASS이지만 **min_interval 60s / cooldown 900s** 준수
   - google_trends_explore: **CONFIRMED_EXTERNAL_RATE_LIMIT 유지** (PASS 아님)
4. **fallback chain 확인**: trends 429 시 `run_trend_fallback_enrichment_audit` 경로
   (google_trending_now → RSS export → serper/naver)
5. **runner readiness**: `run_runner_orchestration_readiness` JSONL (13/13 agent_ready)
6. **live call**: 필요할 때만, rate gate 통과 확인 후 1회. 결과를 70번 판정 기준으로 평가

## commands
```powershell
# 정적 점검 (네트워크 없음)
Get-Content ingestion\configs\rate_limit_policy.yaml
# 필요 시 readiness 재확인 (네트워크 없음)
.\.venv\Scripts\python.exe -m ingestion.runners.run_runner_orchestration_readiness
# live audit은 rate gate 확인 후에만 (예: enrichment)
.\.venv\Scripts\python.exe -m ingestion.runners.run_enrichment_live_audit
```

## failure conditions
- rate gate가 cooldown이면 live call 금지 → 직전 artifact로 평가
- google_trends_explore 429 → CONFIRMED_EXTERNAL_RATE_LIMIT 기록, fallback chain 안내
- 수집 실패를 PASS로 적으면 NOT_READY

## success criteria
- 소스별 status가 artifact 근거로 판정됨
- rate-limit 정책 위반 호출 0건
- google_trends_explore PASS 표기 0건

## safety constraints
- provider 429 반복 호출 금지
- Google Trends Explore 강제 우회 금지 (proxy/internal RPC/login 금지)
- CAPTCHA/로그인/페이월 우회 금지
- proxy rotation 금지
- git push 금지 / rm·Remove-Item 금지 / .env 값 출력 금지
- 실패를 PASS로 보고 금지

## output format
```
표: source_id | 수집방식 | status | items | body | 판정 | 주의사항
종합: CORE_READY N / CAUTION M / BLOCKED K
trends: CONFIRMED_EXTERNAL_RATE_LIMIT (fallback 가용 여부)
rate_limit_violations: 0
```
