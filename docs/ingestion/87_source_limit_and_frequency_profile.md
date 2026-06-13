# 87. Source Limit & Frequency Profile

- 작성일: 2026-06-13 (live audit **전** — 실측 후 docs/92에서 확정)
- 근거: registry `rate_limit_summary`, `rate_limit_policy.yaml`, docs/80 quota 정책, 429 이력(docs/56/79)
- 원칙: **모르면 UNKNOWN + conservative 제안**. 추측을 실측처럼 적지 않는다.

quota_type: unknown | per_minute | per_day | per_month | site_policy | browser_risk

## API 소스

| source_id | role | quota_type | known_limit | observed_limit_signal | current_rate_policy | recommended_mvp_frequency | recommended_max_items | burst_allowed | cooldown_strategy | risk_level | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| naver_news_search | enrichment | per_day | 25,000/day | 없음 | default | query당 1회 | 3~10 | yes(소량) | 60s on 429 | low | 한글 query 핵심 소스 |
| naver_blog_search | enrichment | per_day | 25,000/day | 없음 | default | query당 1회 | 3~10 | yes(소량) | 60s | low | naver_news와 키 공유 |
| serper | enrichment | 일회성 크레딧 | 2,500 total | 없음 | default | query당 1회 (이벤트 트리거만) | 3~10 | no | 60s | medium | 크레딧 소진형 — 절약 필수 |
| tavily | enrichment | per_month | 1,000/month | 없음 | default | query당 1회 | 3~5 | no | 60s | medium | 월 한도 — 일 33회 수준 |
| exa | enrichment | per_month | 1,000/month | 없음 | default | query당 1회 | 3~5 | no | 60s | medium | 월 한도 |
| newsapi | enrichment | per_day | **100/day** | 없음 | default | 일 ≤20 query | 3~10 | no | 60s + 일일 budget | high | free tier 상업 사용 금지 |
| gnews | enrichment | per_day | **100/day** | 없음 | default | 일 ≤20 query | ≤10(고정) | no | 60s + 일일 budget | medium | 10 articles/req 고정 |
| guardian | enrichment | per_day | 5,000/day | 없음 | default | query당 1회 | 3~10 | yes(소량) | 60s | low | 전문 재배포 금지 |
| nyt | enrichment | per_day | 500/day | 없음 | default | 일 ≤50 query | 3~10 | no | 60s | medium | 상업 라이선스 필요 — 메타데이터만 |
| youtube | both | per_day(units) | 10,000 units/day (search=100u) | 없음 | default | 일 ≤50 search | 3~5 | no | 60s | medium | search 호출이 비쌈 (100배) |
| gdelt | both | unknown + 자체 정책 | UNKNOWN | 과거 과호출 이슈 → 정책 강화 | **min_interval 5s, ttl 900s, 429 시 300s** | 15분 (ttl 900s와 정합) | 3~10 | no | 300s | medium | cache_skip = dedup 동작 검증 사례 |
| sec_edgar | both | per_minute | 10 req/s | 없음 | default | 30~60분 | 3~10 | yes | 60s | low | UA 필수 (SEC_USER_AGENT) |
| opendart | primary(파라미터형) | per_day | ~10,000/day | 없음 | default | 30~60분 (장중) | 3~10 | yes(소량) | 60s | low | |
| federal_register | both | unknown | UNKNOWN(공개) | 없음 | default | daily | 3~10 | yes(소량) | 60s | low | |
| bok_ecos | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | daily | 3~10 | no | 60s | low | |
| eia | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | daily | 3~10 | no | 60s | low | |
| hacker_news | primary | unknown | UNKNOWN(firebase 공개) | 없음 | default | 30분 | 5~10 | yes | 60s | low | title은 item별 2차 호출 필요 |
| product_hunt | primary | unknown | UNKNOWN | 없음 | default | daily | 3~5 | no | 60s | low | |
| finnhub | primary(파라미터형) | per_minute | **60/min** | 없음 | default | 5~15분 × 감시 종목 수 | 1/symbol | yes(60/min 내) | 60s | low | 시뮬레이션 대상 (alpha_vantage 대체) |
| twelve_data | primary(파라미터형) | per_day(credits) | 800 credits/day | 없음 | default | 30~60분 | 3~5 | no | 60s | low | |
| alpha_vantage | primary(파라미터형) | per_day | **25/day** | 200응답 내 "Information" 메시지로 soft-limit 통지 확인됨 | default + 코드에 Note/Information→RATE_LIMITED 분류 | **daily 1회** | compact | no | wait_quota_reset | **high** | 이번 라운드 1회만 사용 |
| polygon | primary(파라미터형) | per_minute(추정) | free 5/min (공식), prev-day 무제한 표기 혼재 → conservative 5/min | 없음 | default | daily | 1 | no | 60s | low | UNKNOWN 부분은 conservative |
| coinbase_market | primary | unknown | UNKNOWN(공개) | 없음 | default | 15~30분 | 5~10 | yes | 60s | low | |
| binance_market | primary | per_minute(weight) | 1200 weight/min | 없음 | default | 5~15분 | 전 종목 1 req | yes | 60s + Retry-After | low | |
| kma | primary(파라미터형) | unknown | data.go.kr 일일 트래픽 (개발계정 통상 1,000/day 수준 — **UNKNOWN, conservative**) | 없음 | default | 1시간 | 10 | no | 60s | low | 정시+10분 발표 주기 |
| tour | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | weekly | 3~10 | no | 60s | low | 정적 데이터 성격 |
| its | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | 15~30분 | 10 | no | 60s | low | |
| kofic | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | daily 1회 (전일 확정 후) | 10 | no | 60s | low | |
| tmdb | both | per_hour(추정) | ~100/hr (비공식, 관대) | 없음 | default | seed daily / enrichment 일 ≤10 | 3~5 | yes(소량) | 60s | low | |
| kopis | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | daily | 3~10 | no | 60s | low | |
| aladin | primary(파라미터형) | unknown | UNKNOWN | 없음 | default | daily | 3~10 | no | 60s | medium | 상업 이용 별도 계약 |
| igdb | primary(파라미터형) | per_second | 4 req/s | 없음 | default | daily~weekly | 3~10 | yes(4/s 내) | 60s | low | Twitch OAuth 토큰 메모리 캐시 |

## RSS/HTML/Playwright 소스 (site_policy / browser_risk)

| source_id | role | quota_type | known_limit | observed_limit_signal | current_rate_policy | recommended_mvp_frequency | recommended_max_items | burst_allowed | cooldown_strategy | risk_level | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| bbc/ap_news/techcrunch/the_verge/yna/hankyung/maekyung/aljazeera/cnbc | primary | site_policy | 명시 없음 | 없음 | default | 30~60분 | feed 전체(절단 저장) | no | 60s + UA 유지 | low | RSS는 폴링 전제 포맷 |
| zdnet_korea/etnews | primary | site_policy | 명시 없음 | 없음 | default | 60분 | 후보 10 | no | 60s | low | html selector 의존 |
| dcinside | primary | browser_risk | UNKNOWN(anti_bot) | cloudflare 이력 | yaml min 10분 | 30~60분 | 3 | no | 차단 시 즉시 중단 | medium | playwright 전용 |
| eu_press_corner | primary | site_policy | 명시 없음 | 없음 | yaml min 120분 | 2~6시간 | 10 | no | 60s | low | playwright |
| signal_bz | primary | browser_risk | UNKNOWN | 없음 | yaml min 30분 | 30~60분 | 10 | no | 차단 시 중단 | medium | |
| loword | primary | browser_risk | UNKNOWN | 없음 | yaml min 30분 | 30~60분 | 10 | no | 차단 시 중단 | medium | selector 취약(CSS-in-JS) |
| google_trending_now | primary | browser_risk | UNKNOWN | **429 재발 이력 (1800s 간격에서도)** | **min_interval 7200s, 429 시 3600s, retry 0** | 2시간+ | 10 | **no (절대)** | 3600s, 루프 재시도 금지 | **high** | |
| google_trends_explore | enrichment | browser_risk | UNKNOWN | **429 재발 이력** | **min_interval 7200s, 429 시 3600s, retry 0** | 수동/특수 라운드만 | 5 | **no (절대)** | 3600s | **high** | 기본 audit 제외, opt-in 플래그 |

## 제외/보류 (참고)

| source_id | 상태 | 사유 |
|---|---|---|
| krx_kind | DEFERRED_SPECIAL_ROUND | 서버 오류 페이지 — 전용 라운드에서 재시도 |
| reddit | MVP_DEFERRED | 비로그인 rate limit 변동성 |
| x / blind / reuters / fmkorea / google_programmable_search | MVP_EXCLUDED | 유료 API / login wall / 라이선스 / Turnstile / CX 미설정 |

## 이번 라운드 호출 예산 대조 (docs/85 §5)

총 ~90회 — 일일 quota 대비 최대 소비율: alpha_vantage 1/25(4%), newsapi 2/100(2%), gnews 2/100(2%), nyt 2/500(0.4%). 전 소스 10% 미만 확인.
