# 92. MVP Collection Frequency Draft (수집 주기 초안)

- 작성일: 2026-06-13
- 근거: docs/87(quota 프로파일) + docs/88~90 실측. 실측 없는 항목은 `provisional` 표기.
- 전제: Celery beat(plans/012) 도입 전 초안. cache_ttl을 주기와 정합하게 설정하는 작업이 후속.

## bucket 정의

| bucket | 주기 | 용도 |
|---|---|---|
| near_real_time | 5~15분 | 속보성 seed/시장 임계값 감시 |
| short_interval | 30~60분 | 일반 뉴스/커뮤니티/공시 |
| medium_interval | 2~6시간 | 저빈도 공식 소스/트렌드(429 민감) |
| daily | 일 1회 | 확정형 데이터(박스오피스 등)/quota 극소 소스 |
| manual_or_deferred | 수동/보류 | 특수 라운드 전용 |

## 소스별 배정

### near_real_time (5~15분)
| source_id | 근거 |
|---|---|
| yna | RSS 120건 실측, 한국어 속보 핵심 (15분, provisional) |
| finnhub | 60/min quota 여유, 시뮬레이션 검증 — 감시 종목 수 × 15분 내 안전 |
| binance_market | 1200 weight/min, 공개 (15분, provisional) |
| gdelt | **15분 고정, 연속 실패 시 자동 cooldown 900s** — cache ttl 900s와 정합. 429 실측 3회(2026-06-13 phrase-quoting 호출도 IP rate limit으로 429) → 더 짧은 주기 금지. 02 적용 후 min_interval 60s·cooldown 900s, soft limit(200+평문 "Please limit requests")도 RATE_LIMITED로 분류되어 01 cooldown 기록 경로로 보호됨. |

### short_interval (30~60분)
bbc, ap_news(endpoint 수리 후), techcrunch, the_verge, zdnet_korea, etnews, hankyung, maekyung, aljazeera, cnbc — RSS/html 실측 안정 (30~60분)
hacker_news (30분, item detail 설계 후), dcinside (60분, selector 보강 후 — yaml min 10분보다 보수)
opendart (30~60분 장중), sec_edgar (30~60분)
signal_bz, loword (30~60분 — yaml min 30분 준수)
naver_news_search (이벤트 트리거 + 정기 카테고리 query 60분, 25k/day 여유)
coinbase_market (30분, provisional), twelve_data (60분, credits 역산), kma (정시+10분, 1시간)
its (30분, provisional — sample 매핑 후)

### medium_interval (2~6시간)
google_trending_now (**2시간+ 고정** — min_interval 7200s 정책 준수, 429 이력)
eu_press_corner (2~6시간 — yaml min 120분, selector 보강 후)
serper/tavily/exa — 정기 폴링 금지, **이벤트 트리거 전용** + 일일 budget(아래) 내. 카테고리 모니터링은 6시간 1회 이하 (provisional)

### daily
kofic (전일 박스오피스 확정 후 1회), alpha_vantage (**25/day — 일 1회 고정**), polygon (전일 aggs), federal_register, bok_ecos, eia, product_hunt, tmdb(seed), kopis, aladin, igdb, culture_info, tour(weekly로 더 낮춤 가능)

### enrichment 일일 budget (정기 주기 아님 — 1차 seed 발생 시 트리거)
| source | 일일 query budget | 근거 |
|---|---|---|
| naver_news_search / naver_blog_search | ≤200 | 25,000/day 대비 1% 미만 |
| serper | ≤30 | 일회성 2500 크레딧 보존 |
| tavily / exa | ≤30 | 1000/month ≈ 33/day |
| guardian | ≤100 | 5000/day |
| nyt | ≤50 | 500/day |
| gnews / newsapi | ≤20 | 100/day (newsapi는 everything 전환 후) |
| youtube(search) | ≤50 | 10,000 units/day, search=100u |
| tmdb(search) | ≤10 | ~100/hr |
| gdelt(query) | ≤20 + 15분 간격 | 429 실측 |
| sec_edgar(entity query) | ≤50 | 10 req/s 공개 |

### manual_or_deferred
google_trends_explore (수동, gate 필수), krx_kind, reddit, x, blind, reuters, fmkorea, google_programmable_search

## 후속 권장 (주기 확정 시)
1. `rate_limit_policy.yaml`에 주기와 정합한 cache_ttl 추가 (예: RSS 30분 주기 → ttl 1500s) — 시뮬레이션에서 ttl 0 소스는 매 cycle 재호출됨을 확인.
2. Route 1 429 시 `record_rate_limited` 호출 추가 (docs/90 §3 gap) — cooldown bucket 자동 강등의 전제.
3. enrichment 일일 budget 카운터는 Celery 단계에서 rate_limit_store 확장으로 구현 (이번 라운드 범위 외).

## 08 라운드 — numeric_signal 소스 주기 (2026-06-13)

numeric_signal로 분류된 소스는 article seed가 아니라 지표 폴링이므로 주기를 값 변동성에 맞춘다 (provisional, quota 기준).

| source_id | bucket | 근거 |
|---|---|---|
| finnhub / binance_market / coinbase_market | near_real_time(5~15분) | 시세 변동성, finnhub 60/min |
| its | short_interval(30~60분) | 교통 속도 갱신 주기(createdDate 분 단위, 3만+건) |
| bok_ecos / eia | daily | 통계/에너지 지표 갱신 저빈도 |
| kma | short_interval(초단기실황 갱신) | 기상 관측 시각 단위 |
| federal_register / igdb / culture_info | daily | 문서/게임/문화행사 등록 저빈도 |
| hacker_news | short_interval(30~60분) | topstories 순위 변동 |

## 갱신 (docs/10 최종 closing, 2026-06-13)

- **provider rate-limit 근거 문서화**: `docs/ingestion/rate_limit_evidence.md` 신설 — gdelt/google_trends_explore의 한도 근거(검색+실측)와 `rate_limit_policy.yaml` 정합성 점검. 정책 값은 근거보다 보수적이라 변경 없음.
- **gdelt**: near_real_time(15~30m) 유지하되, **min_interval 60s 준수가 전제**(빠른 연속 호출은 soft-429). 실측 LIVE_SUCCESS로 수집 능력 확정.
- **google_trends_explore**: `manual_or_deferred` 유지 — provider 429 confirmed(robot.png). optional enrichment, 장주기(7200s)+재시도0. 재개 윈도우는 cooldown 만료 후 1회.

## Google Trends fallback chain (PHASE 2, 2026-06-13)

- **google_trending_now**: `short_to_medium`(2시간+, min_interval 7200s) — primary trend seed. PASS.
- **google_trends_trending_now_export**(공개 RSS): `short_to_medium`(2시간+) — `trends.google.com/trending/rss?geo={region}` 실측 **EXPORT_AVAILABLE**. google_trending_now의 안정 대체/병행 seed 경로.
- **google_trends_explore**: `manual_or_deferred` 유지 — **CONFIRMED_EXTERNAL_RATE_LIMIT**. optional_enrichment, 429 시 collected=false + fallback chain(news/search related expansion)로 동일 목적 충족. 재시도 0.
- **fallback enrichment(news/search)**: query 트리거형 — hot seed 발생 시 serper/tavily/naver(+영문 시 exa/gnews/newsapi/guardian/ap_news)로 related_candidate 확장. 별도 주기 편성 불필요(이벤트 트리거).
