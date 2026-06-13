# 33 — Google Trends Stabilization Report

**대상**: google_trending_now, google_trends_explore  
**원칙**: 429 시 즉시 중단. 대량 호출 절대 금지. 30~60분 주기 + 캐싱.

---

## 1. google_trending_now

### 현재 상태
- **artifact**: raw_signal/google_trending_now/20260603_143320 (365B, 10 keywords)
- **샘플 키워드**: 배우, 투표, 젠슨 황, mc몽, 이재명, 김희철, 멋진 신세계, 박민식, 임태희, 기부
- **수집 시각**: 2026-06-03 14:33 KST (선거일 맥락)
- **상태**: LIVE_SUCCESS

### Rate Limit 정책 (Step 1-3 적용)
```yaml
google_trending_now:
  min_interval_seconds: 1800    # 30분
  cooldown_on_429_seconds: 600  # 429 시 10분 대기
  max_retries_on_429: 0         # 재시도 없음 (대기 후 다음 사이클)
  cache_ttl_seconds: 1800       # 30분 캐시
```

### URL 구조
- `https://trends.google.com/trending?geo=KR` (KR 리전)
- selector: `.mZ3RIc` (관측됨) + fallback 3개

### 안정성 평가
- **봇 차단**: 없음 (현재)
- **비공식 API**: trends.google.com은 공식 API 아님
- **위험**: 과도한 호출 시 IP 차단 가능. 현재 1800s 주기로 안전.
- **결론**: STABLE (rate limit 준수 조건)

---

## 2. google_trends_explore

### 현재 상태
- **artifact**: 없음 (이번 라운드 probe 미실행)
- **spec**: playwright_probe_sites.yaml 등록됨
- **URL 구조**: `https://trends.google.com/trends/explore?q={query}&geo={region}`
- **목적**: 특정 키워드(삼성전자/엔비디아/OpenAI/유가) 관련 검색 트렌드

### Rate Limit 정책 (Step 1-3 적용)
```yaml
google_trends_explore:
  min_interval_seconds: 1800    # 30분
  cooldown_on_429_seconds: 600
  max_retries_on_429: 0
  cache_ttl_seconds: 1800
```

### selector (playwright_probe_sites.yaml 현재값)
```yaml
selectors:
  list:
    - ".fe-related-queries-item"
    - ".related-queries-table tr td:first-child"
    - "[jsname='CtgRsb']"
```

### 실행 계획 (이번 라운드 이연)
- **이연 이유**: 30~60분 주기 정책상 단발 probe 실행이 quota에 영향 없으나, 결과 재현을 위해 캐시 TTL 적용 후 다음 라운드 정식 실행.
- **다음 라운드 실행 명령**:
  ```
  python -m ingestion.runners.run_playwright_probe --site google_trends_explore --query "삼성전자" --region KR --max-items 5
  ```
- **상태**: DEFERRED (probe 미실행. spec은 완비됨)

---

## 3. 공통 원칙

- Google Trends는 비공식 크롤링이므로 **30분 이상 주기** 필수
- 캐시 히트 시 즉시 이전 결과 반환 (TTL 캐시 배선 완료, Step 1-2)
- 429 수신 시 `max_retries_on_429: 0` → 즉시 중단, 다음 사이클 대기
- KR region 고정: `geo=KR` 파라미터
- 쿼리 예시: 삼성전자, 엔비디아, OpenAI, 유가, 호르무즈

---

## 4. 결론

| source | status | rate_limit | cache | next |
|---|---|---|---|---|
| google_trending_now | LIVE_SUCCESS | 1800s 주기 | 1800s TTL | integrate |
| google_trends_explore | DEFERRED | 1800s 주기 | 1800s TTL | next_round_probe |
