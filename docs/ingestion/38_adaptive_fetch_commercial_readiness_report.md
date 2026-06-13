# 38 — Adaptive Fetch Commercial Readiness Report

**검증 일시**: 2026-06-03  
**목적**: 5계약 점검 + Adaptive Fetch Framework 상용성 평가

---

## 1. 5계약 점검

### run_collection_probe
- **source_id 라우팅**: API/playwright-first/URL 3가지 경로 올바르게 구현됨
  - Route 1: `_PROBE_SPEC` 존재 → `run_api_live_probe`
  - Route 2: `_PLAYWRIGHT_FIRST_SOURCES` 또는 PLAYWRIGHT_REQUIRED → CloudBrowserLikeStrategy
  - Route 3: fallback → `run_fetch_strategy_loop`
- **상태**: PASS

### run_fetch_strategy_loop
- **ErrorType 통일**: `classify_failure()` → ErrorType 반환, BLOCKED_ERRORS 즉시 중단
- **BLOCKED 중단**: `BLOCKED_ERRORS`(captcha/login/paywall/robots) 감지 시 `status="blocked"` 즉시 반환
- **retryable 다음전략**: RATE_LIMITED는 cooldown 후 재시도(전략 전진 없음), 일반 실패는 select_next_strategy
- **strategy_budget 준수**: `max_strategies_per_url`로 제한
- **TTL 캐시**: 진입 시 is_cached, 성공 시 record_call (Fix 2 적용)
- **상태**: PASS

### classify_failure
- **ErrorType 통일**: exception 타입 → ErrorType 매핑
- **위치**: `fetch_strategies/failure_classifier.py`
- **상태**: PASS

### select_next_strategy
- **source_id 라우팅**: RSS 소스는 playwright 스킵, JS 실패 시 playwright 우선, 전부 실패 시 selenium 후보
- **_JS_RENDER_STRATEGIES 사용**: Fix 5 적용 — selenium 후보 판정에 실제 사용
- **상태**: PASS

### write_collection_artifacts
- **artifact 중복 방지**: source_id + run_id + url_hash 조합으로 파일명 생성
- **Agent 판독**: CollectionProbeResult에 status/items_found/artifact_paths/error_category 포함
- **상태**: PASS

---

## 2. 테스트 보강 현황

### 기존 (291개)
- `test_rate_limit_policy.py`: 캐시 히트/기록, TTL 만료, 소스별 정책
- `test_strategy_runner.py`: RATE_LIMITED 매핑, 전략 선택, RSS/budget
- `test_fetch_strategies.py`: 라우팅, 아티팩트, CloudBrowserLike, markdown

### 신규 추가 (이번 라운드, 14개)
- `test_rate_limit_policy.py` 추가: google_trends_explore 정책, TTL 캐시 배선
- `test_fetch_strategies.py` 추가: rate_limited→RATE_LIMITED, cached→LIVE_SUCCESS, selenium Windows 경로, _JS_RENDER_STRATEGIES

### 결과: 305 passed, 1 skipped (회귀 없음)

---

## 3. 정적 빈 DOM → playwright 제안 경로

```
httpx_direct → EXTRACTION_EMPTY
→ select_next_strategy → "playwright_basic" (강제 점프)
```
테스트: `test_empty_dom_on_httpx_jumps_to_playwright` — PASS

### playwright timeout → selenium 후보 경로

```
모든 playwright 전략 실패
→ _all_playwright_failed() = True
→ "selenium_rendered_dom" in _JS_RENDER_STRATEGIES → selenium_env_status()["ready"]
→ ready=True면 "selenium_rendered_dom" 반환
→ 현재 NOT_READY이므로 None 반환
```
단위 테스트로 검증됨 (ready=False mock).

### 429 → cooldown no-retry 경로

```
RATE_LIMITED 예외
→ _429_retries < max_retries_on_429: cooldown sleep, 동일전략 재시도
→ _429_retries >= max_retries_on_429: status="rate_limited"
→ _loop_status_to_probe_status("rate_limited") = "RATE_LIMITED"
```

### login/captcha → blocked no-retry

```
CAPTCHA_DETECTED / LOGIN_WALL_DETECTED
→ ErrorType in BLOCKED_ERRORS
→ status="blocked" 즉시 반환
→ _loop_status_to_probe_status("blocked") = "BLOCKED"
```

---

## 4. 상용성 종합 평가

| 기능 | 상태 | 비고 |
|---|---|---|
| source 라우팅 | IMPLEMENTED | API/playwright/URL 3경로 |
| 전략 순서 | IMPLEMENTED | STRATEGY_SEQUENCE 준수 |
| BLOCKED 즉시 중단 | IMPLEMENTED | BLOCKED_ERRORS 집합 |
| 429 cooldown 재시도 | IMPLEMENTED | per_source 정책 적용 |
| TTL 캐시 | IMPLEMENTED | Fix 2 완료 |
| rate_limited 매핑 | IMPLEMENTED | Fix 1 완료 |
| artifact 저장 | IMPLEMENTED | raw_payload/raw_signal/extracted |
| Agent 판독 가능 | IMPLEMENTED | CollectionProbeResult 필드 완비 |
| 회귀 테스트 | 305 passed | 14개 신규 포함 |

**종합**: 상용 수준 재시도 구조 달성. 미완성 사항은 selenium live (NOT_READY), GDELT 재호출 (5s 간격 준수 필요).
