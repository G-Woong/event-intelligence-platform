# 86. Source Role Classification Matrix (전체 소스)

- 작성일: 2026-06-13 (live audit **전** 분류 — 실측 반영은 docs/88~93)
- 근거: `source_registry.yaml`, `playwright_probe_sites.yaml`, `_PROBE_SPEC`, docs/70/80
- role 정의: `primary_seed`(주기 호출로 사건 후보 감지) / `enrichment`(query 확장 수집) / `both` / `deferred` / `excluded`

## 표기 원칙

- **전체 소스 누락 없이** 기재 (제외/보류 포함). `_dummy`(테스트 픽스처)만 생략.
- recommended_frequency는 이 시점에서는 **provisional** — 실측 후 docs/92에서 확정.
- minimum_required_fields = EventSeedCandidate 최소 필드 기준 (title_or_keyword, source_url, timestamp).

## 1. document_discovery (뉴스, 11)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| bbc | BBC News | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30~60분 | site policy, UA 명시 | P1 |
| ap_news | AP News | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30~60분 | site policy | P1 |
| techcrunch | TechCrunch | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 60분 | site policy, consent banner | P2 |
| the_verge | The Verge | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 60분 | site policy | P2 |
| zdnet_korea | ZDNet Korea | primary_seed | html | 없음 | 후보 URL 목록 + page title | title,url | 60분 | site policy | P2 |
| etnews | 전자신문 | primary_seed | html | 없음 | 후보 URL 목록 + page title | title,url | 60분 | site policy | P2 |
| yna | 연합뉴스 | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 15~30분 | site policy | P1 |
| hankyung | 한국경제 | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30분 | site policy | P1 |
| maekyung | 매일경제 | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30분 | site policy | P1 |
| aljazeera | Al Jazeera | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30~60분 | site policy | P1 |
| cnbc | CNBC | primary_seed | rss(xml) | 없음 | 기사 title/link/pubDate | title,url,timestamp | 30~60분 | site policy | P1 |

## 2. community_signal (8)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| hacker_news | Hacker News | primary_seed | api(json) | 없음 | top story id 목록 (title은 2차 호출 필요) | url(파생),source_id | 30분 | 공개 API, 제한 관대 | P2 |
| product_hunt | Product Hunt | primary_seed | api(graphql) | 없음 | 신규 제품 name/tagline | title,snippet | daily | API key, 복잡도 낮음 | P3 |
| youtube | YouTube | **both** | api(json) | (선택) q | 영상 title/desc/publishedAt/videoId | title,url,timestamp | seed daily / enrichment query당 | 10,000 units/day, search=100 units | P1 |
| dcinside | DCinside | primary_seed | playwright | 없음 | 게시글 title/링크 | title,url | 30~60분 | anti_bot, min 10분 | P2 |
| reddit | Reddit | **deferred** | api(json) | - | - | - | - | MVP_DEFERRED (rate limit 변동성) | - |
| fmkorea | 에펨코리아 | **excluded** | - | - | - | - | - | Cloudflare Turnstile (우회 금지) | - |
| x | X (Twitter) | **excluded** | - | - | - | - | - | 유료 API 필요 | - |
| blind | Blind | **excluded** | - | - | - | - | - | login wall | - |

## 3. search_enrichment (10)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| serper | Serper | enrichment | api(POST json) | q | SERP organic title/link/snippet | title,url,snippet | query당 (이벤트 트리거) | 2500 일회성 크레딧 | P1 |
| tavily | Tavily | enrichment | api(POST json) | query | AI search results title/url/content | title,url,snippet | query당 | 1000/month | P1 |
| exa | Exa | enrichment | api(POST json) | query | neural search results | title,url | query당 | 1000/month | P2 |
| naver_news_search | Naver News Search | enrichment | api(json) | query | 한글 뉴스 title/link/desc/pubDate | title,url,timestamp,snippet | query당 | 25,000/day (관대) | P1 |
| naver_blog_search | Naver Blog Search | enrichment | api(json) | query | 블로그 title/link/desc | title,url,snippet | query당 | 25,000/day | P2 |
| newsapi | NewsAPI | enrichment | api(json) | q | 헤드라인 title/url/desc/publishedAt | title,url,timestamp | query당 (절약) | **100/day**, 상업 사용 금지(free) | P2 |
| gnews | GNews | enrichment | api(json) | q | 기사 title/url/desc/publishedAt | title,url,timestamp | query당 (절약) | **100/day**, 10건/req | P2 |
| guardian | The Guardian | enrichment | api(json) | q | webTitle/webUrl/webPublicationDate | title,url,timestamp | query당 | 5000/day, 재배포 금지 | P1 |
| nyt | New York Times | enrichment | api(json) | q | headline/web_url/pub_date | title,url,timestamp | query당 (절약) | 500/day, 상업 라이선스 필요 | P2 |
| google_programmable_search | Google CSE | **excluded** | - | - | - | - | - | CX 미설정(400) — 재활성화 보류 | - |

## 4. official_evidence (8)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| gdelt | GDELT | **both** | api(json) | (선택) query | 기사 title/url/seendate/domain | title,url,timestamp | seed 15~30분 / enrichment query당 | min_interval 5s, cache ttl 900s | P1 |
| sec_edgar | SEC EDGAR | **both** | api(json) | (선택) q | filing display_names/file_date | title,timestamp | seed 30~60분 / enrichment query당 | 10 req/s, UA 필수 | P1 |
| opendart | OpenDART | primary_seed(파라미터형) | api(json) | 날짜 범위 | 공시 report_nm/corp_name/rcept_dt | title,timestamp | 30~60분 (장중) | ~10,000/day | P1 |
| federal_register | Federal Register | **both** | api(json) | (선택) conditions[term] | 관보 title/publication_date | title,url,timestamp | daily | 공개, 관대 | P2 |
| bok_ecos | 한국은행 ECOS | primary_seed(파라미터형) | api(json) | 통계코드/기간 | 지표 시계열 | title(지표명),timestamp | daily | key 필요, quota UNKNOWN | P3 |
| eia | EIA | primary_seed(파라미터형) | api(json) | route/기간 | 에너지 시계열 | title,timestamp | daily | key 필요 | P3 |
| eu_press_corner | EU Press Corner | primary_seed | playwright | 없음 | 보도자료 title/링크 | title,url | 2~6시간 | min 120분(yaml) | P2 |
| krx_kind | KRX KIND | **deferred** | - | - | - | - | - | DEFERRED_SPECIAL_ROUND (서버 오류 페이지) | - |

## 5. news_verification (1)

| source_id | source_name | role | 비고 |
|---|---|---|---|
| reuters | Reuters | **excluded** | 라이선스 제약 + bot protection — 공식 API 라이선스 확보 전 제외 |

## 6. fast_signal (4)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| signal_bz | Signal.bz | primary_seed | playwright | 없음 | 실시간 검색어 keyword 목록 | title(keyword),source_id | 30~60분 | min 30분(yaml), UNKNOWN | P1 |
| loword | Loword | primary_seed | playwright | 없음 | 실시간 검색어 keyword 목록 | title(keyword),source_id | 30~60분 | min 30분, CSS-in-JS selector 취약 | P2 |
| google_trending_now | Google Trending Now | primary_seed | playwright | (선택) region | 트렌딩 keyword 목록 | title(keyword),source_id | 2시간+ | **429 이력**, min_interval 7200s | P2 |
| google_trends_explore | Google Trends Explore | optional_enrichment | playwright | hot seed keyword | 연관 검색어 | title(keyword) | 수동/2시간+ | **CONFIRMED_EXTERNAL_RATE_LIMIT(429)**, min_interval 7200s / cooldown 3600s / max_retries_on_429=0, hot seed trigger, 실패 시 collected=false + **fallback chain**(아래 §Trends fallback), event queue 비차단, body_status=not_required, 반복 호출 금지 | P3 |
| google_trends_trending_now_export | Google Trends Trending Now RSS | primary_seed(fallback B) | rss | (선택) region | 트렌딩 keyword RSS entry | title(keyword),url | 2시간+ | 공개 RSS `trends.google.com/trending/rss?geo={region}` — **EXPORT_AVAILABLE 실측(2026-06-13)**. 내부 RPC 아님. 정식 registry 온보딩은 후속 라운드 | P2 |

## 7. market_signal (6)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| finnhub | Finnhub | primary_seed(파라미터형) | api(json) | symbol | 실시간 quote (c/h/l/o/pc) | source_id,timestamp(파생) | 5~15분 (감시 종목) | 60/min | P1 |
| twelve_data | Twelve Data | primary_seed(파라미터형) | api(json) | symbol/interval | 시계열 values | title(symbol),timestamp | 30~60분 | 800 credits/day | P2 |
| alpha_vantage | Alpha Vantage | primary_seed(파라미터형) | api(json) | function/symbol | 일봉 시계열 | title(symbol),timestamp | **daily 1회** | **25/day — 최우선 절약** | P3 |
| polygon | Polygon.io | primary_seed(파라미터형) | api(json) | ticker | 전일 aggs | title(symbol),timestamp | daily | prev-day 무제한(free) | P2 |
| coinbase_market | Coinbase | primary_seed | api(json) | 없음 | products 목록/시세 | title(symbol) | 15~30분 | 공개, 관대 | P2 |
| binance_market | Binance | primary_seed | api(json) | 없음 | 전 종목 ticker price | title(symbol) | 5~15분 | 1200 weight/min | P2 |

## 8. domain_signal (9)

| source_id | source_name | role | collection_method | expected_input | expected_output | minimum_required_fields | recommended_frequency | quota_or_rate_limit_notes | final_audit_priority |
|---|---|---|---|---|---|---|---|---|---|
| kma | 기상청 | primary_seed(파라미터형) | api(json) | base_date/time/격자 | 실황 관측값 | title(category),timestamp | 1시간 (정시+10분) | data.go.kr quota UNKNOWN | P1 |
| its | 국토부 ITS | primary_seed(파라미터형) | api(json) | bbox | 교통 돌발/소통 정보 | title,timestamp | 15~30분 | quota UNKNOWN | P2 |
| kofic | 영진위 KOBIS | primary_seed(파라미터형) | api(json) | targetDt | 일일 박스오피스 rank/movieNm | title,timestamp | **daily 1회** (전일 데이터) | quota UNKNOWN | P1 |
| tmdb | TMDB | **both** | api(json) | (선택) query → /search/movie | 영화 title/overview/release_date | title,timestamp | seed daily / enrichment query당 | ~100/hr | P2 |
| kopis | KOPIS | primary_seed(파라미터형) | api(xml) | 기간 | 공연 prfnm/기간 | title,timestamp | daily | quota UNKNOWN | P3 |
| aladin | 알라딘 | primary_seed(파라미터형) | api(json) | QueryType | 베스트셀러 title/pubDate | title,url,timestamp | daily | 개인 free, 상업 별도 | P3 |
| igdb | IGDB | primary_seed(파라미터형) | api(POST apicalypse) | apicalypse query | 게임 name/release/rating | title | daily~weekly | 4 req/s (OAuth) | P3 |
| culture_info | 문화포털 | primary_seed(파라미터형) | api(xml) | 기간 | 문화행사 title/기간/장소 | title,timestamp | daily | quota UNKNOWN | P3 |
| tour | TourAPI | primary_seed(파라미터형) | api(json) | areaCode | 관광지/행사 title/addr | title | weekly (정적 성격) | quota UNKNOWN | P3 |

## 9. 집계

| role | 수 | 소스 |
|---|---|---|
| primary_seed | 33 | 뉴스 11, 커뮤니티 3(hn/ph/dcinside), 공식 5, 트렌드 3, 시장 6, 도메인 8(tmdb 제외 시) — 파라미터형 lookup 포함 |
| enrichment 전용 | 10 | serper, tavily, exa, naver×2, newsapi, gnews, guardian, nyt, google_trends_explore |
| both | 5 | gdelt, sec_edgar, federal_register, youtube, tmdb |
| deferred | 2 | krx_kind, reddit |
| excluded | 5 | x, blind, reuters, fmkorea, google_programmable_search |

> 주: "파라미터형 lookup"(kofic/kma/finnhub 등)은 free-text query는 없지만 파라미터(날짜/symbol/지역)로 주기 호출하는 1차 소스로 분류. 2차 audit에서는 `query_unsupported`로 기록하고 1차 결과로 enrichment 용도(사건 검증용 수치 lookup)를 평가한다.

## 08 라운드 — numeric_signal 평가 경로 분리 (2026-06-13)

시장/지표 수치 소스는 title/url 개념이 없어 seed 5필드 체계로는 영원히 no가 된다(분류 오류). `_audit_common.NUMERIC_SIGNAL_SOURCES`로 분리하고 `seed_ready_label_for`가 **probe items_found>0 = signal_ready**로 평가한다.

- **numeric_signal role**: finnhub, alpha_vantage, polygon, coinbase_market, binance_market, twelve_data, its, eia, bok_ecos, kma.
- **both → event 보강**: federal_register(seed+query), igdb/culture_info(domain enrichment, sample=event_candidate).
- hacker_news: primary_seed(detail 2차 호출로 title+url+time 확보).
- flat quote(finnhub 등 list 없는 응답)도 데이터 수신 자체가 signal_ready — `_flat_numeric_signal`로 scalar 필드를 1 record로 묶는다.

## Google Trends 역할 3분할 + Trends fallback chain (PHASE 1/2, 2026-06-13)

**역할 3분할 (혼동 방지):**
- **Google Trends** — 제품/서비스 이름. source_id 아님.
- **google_trending_now** — 지금 급상승 검색어 seed를 뽑는 primary trend seed source. **PASS**(LIVE_SUCCESS). 이벤트 발견용으로 유지.
- **google_trends_explore** — 이미 확보한 hot seed의 연관 검색어를 확장하는 **optional_enrichment**. **CONFIRMED_EXTERNAL_RATE_LIMIT**. critical dependency에서 제외. 실패해도 event queue 전체를 막지 않는다.

**Trends fallback chain (google_trends_explore 429 시 대체 경로, `run_trend_fallback_enrichment_audit.py`):**
- **A. google_trending_now** (Playwright seed) — trend item ≥3 → event candidate. cooldown이면 직전 raw_signal artifact로 평가(재호출 없음).
- **B. google_trends_trending_now_export** (공개 RSS) — `trends.google.com/trending/rss?geo={region}` feed_discovery 검증. 실측 **EXPORT_AVAILABLE**. 404/blocked면 `EXPORT_UNAVAILABLE`로 기록하고 A를 primary로 유지.
- **C. 뉴스/검색 enrichment** — hot seed 1개를 serper/tavily/exa/naver/gnews/newsapi/guardian/ap_news에 질의 → title+snippet에서 규칙 기반 related_candidate 생성(`extract_related_candidates`, co-occurring term / title bigram / proper entity / 한글 2-gram). URL 결과는 본문 추출 ≥1회.
- **실측(trend_fallback_enrichment_audit_20260613_102354)**: A collected / B EXPORT_AVAILABLE / C serper·tavily·naver collected(related 8/3/12, body 1건 extracted) / explore RATE_LIMITED_CONFIRMED. aggregate related_candidates **19**(≥5), collected fallback source **5**(≥2). 우회 0건.
