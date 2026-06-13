# 79. Google Trends Rate Limit Guard 보고서 (RISK 12-6)

날짜: 2026-06-12

## 1. 무엇을 닫았는가

google_trends 계열은 1800s 간격 정책에서도 429가 재발했고(docs/33, 56 이력), cooldown이
in-process라 재기동하면 잊혀져 즉시 재호출 → 429 악순환 위험이 있었다. 또한 Route 2
(CloudBrowserLikeStrategy)에는 429 감지가 아예 없어 rate-limited 페이지가
LIVE_SUCCESS/BLOCKED으로 오분류될 수 있었다.

## 2. 변경 사항

### ① 정책 강화 (`rate_limit_policy.yaml`)

| 항목 | 기존 | 신규 | 근거 |
|------|------|------|------|
| min_interval_seconds | 1800 | **7200** | 1800s에서도 429 재발 이력; trends 신선도 요구는 수 시간 단위 |
| cooldown_on_429_seconds | 600 | **3600** | 짧은 cooldown 후 재호출이 연쇄 429 유발 |
| cache_ttl_seconds | 1800 | **7200** | min_interval과 정합 |
| max_retries_on_429 | 0 | 0 (유지) | 429 시 즉시 재시도 영구 금지 |

기존 테스트는 `>= 1800` assert이므로 무수정 통과. 신규 테스트가 `>= 7200` 하한을 고정.

### ② 429 cooldown 영속화 (`playwright_probe.py`)

429 감지 경로에서 ISO timestamp를 로컬 계산만 하던 것을 `record_rate_limited()` 호출로
교체 — deadline이 RateLimitStore(12-1)에 영속화된다. 반환 `ProbeResult` 형태는 동일
(`status=RATE_LIMITED`, `next_retry_at`, `cooldown_seconds`, `retry_after_reason`).

### ③ Route 2 429 감지 (`cloud_browser_like.py`)

rendered HTML에서 `_detect_429` 시그널 감지 시 `status="RATE_LIMITED"` +
`record_rate_limited` 호출. blocker 검사보다 먼저 수행 — RATE_LIMITED가
UNKNOWN/FAILED/BLOCKED으로 떨어지지 않는다.

### status literal 결정

`RATE_LIMITED_DEFERRED` 같은 신규 literal은 **추가하지 않았다** —
`ProbeResult.__post_init__`이 `PROBE_STATUS`를 강제하기 때문. status는 `RATE_LIMITED`
유지, 뉘앙스는 `retry_after_reason`/health state(`RATE_LIMITED_COOLDOWN`)로 표현.

## 3. 동작 흐름 (재기동 생존)

```
429 감지 → record_rate_limited("google_trends_explore", cooldown=3600)
        → store.set_next_retry_at(...)            # backend에 따라 디스크/redis 영속
재기동 후 재호출 → strategy_runner.in_cooldown() → 네트워크 없이 status="rate_limited"
                → collection_probe health gate    → RATE_LIMITED_COOLDOWN skip
```

주의: 기본 backend는 `memory`이므로 재기동 생존은 `INGESTION_RATE_LIMIT_BACKEND=local_file`
(또는 yaml `rate_limit_backend.backend: local_file`) 설정 시 활성화된다. Celery 라운드
(plans/012)에서는 redis backend가 이 역할을 맡는다.

## 4. 검증

`ingestion/tests/unit/test_google_trends_guard.py` — **6 passed**:
- 정책 하한 (trends 2종 × 4개 필드)
- rendered 429 mock → `RATE_LIMITED` + store에 next_retry_at 영속 (Route 2)
- playwright_probe 429 경로 → `next_retry_at` 영속 + ProbeResult 동일 형태
- cooldown 중 strategy loop 재호출 → 네트워크 미호출 (`attempts == []`)
- `RATE_LIMITED` ∈ PROBE_STATUS, `rate_limited` 매핑 보존, `RATE_LIMITED_DEFERRED` 미추가
