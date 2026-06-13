# 37 — GDELT Rate Limit Stabilization Report

**대상**: GDELT Project API  
**문제**: 직전 probe에서 rate limit 응답 수신. Step 1-2 TTL 캐시 배선 적용 완료.

---

## 1. 현황

### artifact 분석
- **파일**: raw_payload/gdelt/20260603_195335_phase0_gdelt_...json (102B)
- **내용**: `"Please limit requests to one every 5 seconds or contact kalev.leetaru5@gmail.com for larger queries."`
- **상태**: FAILED_RETRYABLE (RATE_LIMITED)

---

## 2. GDELT API 구조

| 항목 | 내용 |
|---|---|
| endpoint | api.gdeltproject.org/api/v2/doc/doc |
| auth | 없음 (공개 API) |
| query params | query, mode=artlist, format=json, maxrecords |
| rate limit | 공개: 1 req/5s (문서 없음, 응답 메시지로 확인) |
| 상업적 이용 | 제한 없음 (공개 데이터) |

---

## 3. 적용된 정책 (Step 1-2, Step 1-3)

```yaml
# configs/rate_limit_policy.yaml
gdelt:
  min_interval_seconds: 5       # 5초 간격
  cooldown_on_429_seconds: 300  # rate limit 시 5분 대기
  max_retries_on_429: 1         # 1회 재시도
  cache_ttl_seconds: 900        # 15분 캐시
```

### TTL 캐시 동작 (Fix 2)
- `run_fetch_strategy_loop` 진입 시 `is_cached("gdelt", query)` 확인
- 캐시 히트 → 즉시 `status="cached"` 반환 (live 호출 없음)
- 성공 시 `record_call("gdelt", query)` 기록

---

## 4. 429 처리 흐름 검증

```
RATE_LIMITED 수신
→ _429_retries < max_retries_on_429(1) 이면:
  → cooldown_on_429_seconds(300) 대기
  → 동일 strategy 재시도 (전략 전진 없음)
→ _429_retries >= max_retries_on_429:
  → status="rate_limited" 반환
→ _loop_status_to_probe_status("rate_limited") == "RATE_LIMITED"  # Fix 1 적용
```

---

## 5. 범용성 확인

rate_limit_policy는 GDELT 전용이 아님:
- `default` 섹션: 모든 API 소스에 적용
- `per_source` 섹션: 소스별 오버라이드
- Step 1-3에서 google_trends_explore/google_trending_now도 추가됨
- `load_rate_limit_policy(source_id)` → default + per_source 병합

**구조**: 어떤 source_id든 정책 적용 가능. GDELT가 가장 엄격한 per_source 설정을 가짐.

---

## 6. 다음 라운드 검증 방법

```python
# gdelt 캐시 우선 확인 후 live 조건부 호출
from ingestion.core.rate_limit_policy import is_cached
if not is_cached("gdelt", "samsung"):
    result = run_fetch_strategy_loop("gdelt", gdelt_url, query="samsung")
```

또는:
```
python -m ingestion.runners.run_api_live_probe --service gdelt --env-path "..." --max-calls 1
```

---

## 7. 결론

| 항목 | 상태 |
|---|---|
| 직전 상태 | FAILED_RETRYABLE (rate limited) |
| 정책 적용 | DONE (min_interval=5s, cooldown=300s, cache_ttl=900s) |
| TTL 캐시 배선 | DONE (Fix 2) |
| 매핑 수정 | DONE (rate_limited → RATE_LIMITED, Fix 1) |
| 다음 라운드 | 5s 간격 준수 후 재시도 → LIVE_SUCCESS 예상 |
