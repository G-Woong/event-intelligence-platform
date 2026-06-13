# 56 — Google Trends RATE_LIMITED 처리 및 재시도 보고

## 개요

Google Trends (`google_trends_explore`) 소스에서 발생하는 429 응답을 정확히 분류하고, `LIVE_PARTIAL` 로 degrade 되는 문제를 해결한 작업 내용을 기록한다.

---

## ProbeResult 신규 필드 (probes/models.py)

| 필드명 | 타입 | 설명 |
|--------|------|------|
| `cooldown_seconds` | `Optional[int]` | 429 발생 후 대기해야 하는 쿨다운 초 |
| `next_retry_at` | `Optional[str]` | ISO 8601 형식의 다음 재시도 시각 |
| `retry_after_reason` | `Optional[str]` | 재시도 불가 이유 설명 |
| `cache_hit` | `bool` | in-process 캐시 히트 여부 |
| `network_log` | `Optional[list]` | 네트워크 관찰 로그 (XHR/응답 기록) |

---

## playwright_probe.py 429 감지 개선

### 변경 전

- 429 응답이 담긴 HTML(500B 초과)이 `LIVE_PARTIAL` 로 분류되어 오탐

### 변경 후

- `_detect_429(html)` 헬퍼 함수를 추가하여 렌더된 HTML에서 429 신호를 감지
- 감지 시 `status=RATE_LIMITED` + cooldown/next_retry_at 메타 필드 자동 부착
- 처리 순서: 429 감지 → blocker 감지 순서로 배치 (playwright_probe.py L100 이전)

### 감지 신호 목록

```
"429 too many requests"
"rate limit exceeded"
"you have been rate limited"
"temporarily blocked"
"slow down"
"quota exceeded"
```

---

## rate_limit_policy.yaml — google_trends_explore 정책

```yaml
google_trends_explore:
  min_interval_seconds: 1800
  cooldown_on_429_seconds: 600
  max_retries_on_429: 0
  cache_ttl_seconds: 1800
```

- `min_interval_seconds: 1800` — 최소 30분 간격 유지
- `cooldown_on_429_seconds: 600` — 429 발생 시 10분 쿨다운
- `max_retries_on_429: 0` — 429 발생 즉시 `RATE_LIMITED` 반환, 재시도 없음
- `cache_ttl_seconds: 1800` — TTL 캐시 30분

---

## in-process TTL cache

- `rate_limit_policy.py` 내 `is_cached()` / `record_call()` 함수로 구현
- **주의**: in-process 캐시는 프로세스 재시작 시 휘발됨
- 다음 라운드에서 Redis 기반 persistent cache 도입 예정

---

## UNKNOWN/PARSE_ERROR degrade 방지 근거

- 429 감지 로직이 `classify_content_blocker()` 보다 앞에 위치 (playwright_probe.py L100 이전)
- 429 신호가 감지되면 blocker 분류 단계로 넘어가지 않고 즉시 `RATE_LIMITED` 반환
- 결과적으로 429 HTML이 `UNKNOWN` 또는 `PARSE_ERROR` 로 degrade 되는 경로 차단됨

---

## live probe 정책 요약

| 항목 | 값 |
|------|----|
| 최소 호출 간격 | 1800초 (30분) |
| 429 발생 시 동작 | 즉시 `RATE_LIMITED` 반환 |
| 재시도 횟수 | 0회 (재시도 없음) |
| 쿨다운 | 600초 |
| next_retry_at | 현재 시각 + 600초 (ISO 8601) |

---

## 다음 단계

- Redis 기반 persistent rate limit cache 도입 시 `cache_hit=True` 필드 활용 가능
- 현재 in-process 캐시 한계(프로세스 재시작 휘발) 해소 예정
- Celery 비동기 수집 연동 시 rate limit 상태 공유를 위해 Redis backend 필수
