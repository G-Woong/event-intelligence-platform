# docs/70 — Source Status Master (전체 소스 상태 마스터)

**생성일**: 2026-06-12
**대체 문서**: docs/60(현재 상태 총요약) + docs/61(소스 생존 매트릭스) — 두 문서를 통합·갱신하며 폐기
**근거**: 2026-06-12 live 실측 (라운드 A 22회 + 라운드 B 5회 호출, artifact: `ingestion/outputs/jsonl/api_live_probe_round_a.jsonl`, `api_live_probe_round_b.jsonl`) + source_registry.yaml + 코드 분석
**대상 독자**: 비개발자 포함 전체 이해관계자

---

## 이 시스템이 하는 일 (한 문장)

전세계 사건·이벤트를 다양한 소스(뉴스·커뮤니티·공식 데이터·시장·트렌드)에서 자동으로 수집하여 저장하는 "데이터 수집 레이어"이다.

---

## 이번 라운드에서 무엇이 바뀌었나 (직관적 설명)

직전 문서(docs/60~66)는 실제 API 호출 없이 과거 기록만으로 작성되어, **키가 멀쩡한데 "키 없음(MISSING_KEY)"으로 잘못 적힌 소스가 20개**나 있었다. 이번 라운드는 의심 소스 전부를 실제로 1회씩 호출(live 실측)해서 확인했고, 결과는 다음과 같다:

1. **22개 소스 호출 → 22개 전부 최종 성공.** 사용자가 발급한 API 키 중 무효인 키는 **하나도 없었다**.
2. 실패했던 공공 API 4개(기상청·관광공사·교통정보·문화포털)는 **키 문제가 아니라 전부 코드 쪽 원인**(낡은 엔드포인트 주소·잘못된 파라미터 이름)이었고, 이번에 코드를 고쳐 4개 모두 성공으로 전환했다.
3. "키 충돌(UNKNOWN)"이던 serper/tavily/exa 3개는 실측 결과 정상 동작 — 충돌 해소.
4. 그 결과 **즉시 수집 가능(CORE_READY) 소스가 23개 → 38개로 증가**했다.

---

## 판정 기준 (final_decision)

| 판정 | 정의 |
|------|------|
| **CORE_READY** | live 실측으로 수집 확인됨. 즉시 파이프라인 연결 가능 |
| **READY_WITH_CAUTION** | 수집 가능하나 quota/약관/봇감지 등 주의 필요 |
| **DEFERRED_SPECIAL_ROUND** | 전용 수집 방식(공식 API 등)이 필요하여 별도 라운드로 이관 |
| **MVP_DEFERRED** | 동작은 하나 운영 리스크로 MVP 수집 셋에서 보류 (사용자 확정) |
| **MVP_EXCLUDED** | 구조적 장벽(라이선스·로그인·봇 차단) — 코드 보존, 운영 제외 |
| **UNKNOWN** | 이번 라운드 미검증 — 확인 방법 명시 |

---

## 현재 상태 한눈 요약

| 분류 | 소스 수 | 의미 |
|------|--------|------|
| **CORE_READY** — 즉시 수집 가능 | **38** | 지금 바로 가동할 수 있음 (직전 23 → 38) |
| **READY_WITH_CAUTION** — 조건부 수집 가능 | **6** | 동작하지만 주의 필요 |
| **DEFERRED_SPECIAL_ROUND** | **1** | krx_kind — open.krx.co.kr 공식 API 전환 필요 |
| **MVP_DEFERRED** | **1** | reddit — MVP 적용 보류 (사용자 확정) |
| **MVP_EXCLUDED** — 의도적 제외 | **5** | 유료·라이선스·우회불가 차단 |
| **UNKNOWN (미검증)** | **6** | Phase 1 뉴스 소스 — 재프로브 필요 |
| **내부 테스트 픽스처** (`_dummy`) | 1 | 운영 대상 아님 |
| **합계** | **58** | registry 57개 + YAML 미등록 google_trends_explore 1개 |

---

## 2026-06-12 live 실측 결과표 (before → after)

이번 라운드의 핵심 산출물. "before"는 registry에 적혀 있던 낡은 status, "after"는 실제 호출 결과.

### 충돌 해소 (3개)

| source_id | before (registry) | 실측 결과 | items | 판정 |
|-----------|------------------|----------|-------|------|
| serper | MISSING_KEY | **LIVE_SUCCESS** (http 200) | 3 | CORE_READY |
| tavily | MISSING_KEY | **LIVE_SUCCESS** (http 200) | 3 | CORE_READY |
| exa | MISSING_KEY | **LIVE_SUCCESS** (http 200) | 3 | CORE_READY |

### 공공 API 4개 — 코드 수정으로 해결 (라운드 A 실패 → 라운드 B 성공)

| source_id | 라운드 A (수정 전) | 원인 (실측 확정) | 수정 내용 | 라운드 B (수정 후) |
|-----------|------------------|----------------|----------|------------------|
| kma | 401 INVALID_KEY | apihub.kma.go.kr는 `authKey` 전용 별도 키 필요 — 사용자 키는 data.go.kr 발급 키 | 엔드포인트를 data.go.kr 단기예보(`VilageFcstInfoService_2.0/getUltraSrtNcst`)로 전환 | **LIVE_SUCCESS** (items 8) |
| tour | 500 "Unexpected errors" | `KorService1` 구버전 폐기 | `KorService2/areaBasedList2`로 전환 | **LIVE_SUCCESS** (items 3) |
| its | 401 + resultCode 4004 "잘못된 URL" | `api/NCMInfra/getLinkTrafficInfo` 경로 자체가 무효 | `/trafficInfo` + bbox/getType=json 파라미터로 전환 | **LIVE_SUCCESS** (items 31,578) |
| culture_info | 200이지만 HTML 에러페이지 | 구 culture.go.kr REST 경로 폐기 ("페이지가 없거나 잘못된 경로") | data.go.kr `B553457/cultureinfo/period2`로 전환 | **LIVE_SUCCESS** (items 10) |

### 키 존재 미검증 → 전부 성공 (15개)

| source_id | before | 실측 결과 | items |
|-----------|--------|----------|-------|
| newsapi | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| gnews | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| guardian | MISSING_KEY | **LIVE_SUCCESS** | 1 |
| nyt | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| finnhub | MISSING_KEY | **LIVE_SUCCESS** | 297 |
| twelve_data | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| alpha_vantage | MISSING_KEY | **LIVE_SUCCESS** | 100 |
| polygon | MISSING_KEY | **LIVE_SUCCESS** | 8 |
| kopis | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| tmdb | MISSING_KEY | **LIVE_SUCCESS** | 4 |
| aladin | MISSING_KEY | **LIVE_SUCCESS** | 3 |
| igdb | MISSING_KEY | **LIVE_SUCCESS** (Twitch OAuth 정상) | 3 |
| eia | (docs/61: MISSING_KEY) | **LIVE_SUCCESS** | 14 |
| bok_ecos | (docs/61: MISSING_KEY) | **LIVE_SUCCESS** | 5 |
| product_hunt | (docs/61: MISSING_KEY) | **LIVE_SUCCESS** | 3 |

> 보안: 모든 호출의 응답은 `_sanitize_response()`로 키 redact 후 저장. 본 문서와 artifact에 키 값 없음.

---

## 레이어별 소스 현황

```
document_discovery  : 12개 (뉴스 기사 크롤)
community_signal    :  8개 (커뮤니티·소셜)
search_enrichment   : 10개 (검색 API)
official_evidence   :  8개 (공시·공식 데이터)
news_verification   :  1개 (Reuters — MVP_EXCLUDED)
fast_signal         :  3개 (실시간 트렌드, +YAML 미등록 google_trends_explore)
market_signal       :  6개 (금융·암호화폐)
domain_signal       :  9개 (영화·날씨·교통 등)
```

---

## 전체 소스 매트릭스

### Phase 1 — document_discovery (뉴스 기사)

| source_id | name | 수집 방식 | status | final_decision |
|-----------|------|----------|--------|----------------|
| bbc | BBC News | static HTML | LIVE_SUCCESS | **CORE_READY** |
| ap_news | AP News | static HTML | LIVE_SUCCESS | **CORE_READY** |
| techcrunch | TechCrunch | static HTML | LIVE_SUCCESS (consent 배너 통과 확인) | **CORE_READY** |
| the_verge | The Verge | static HTML | LIVE_SUCCESS (consent 배너 통과 확인) | **CORE_READY** |
| zdnet_korea | ZDNet Korea | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |
| etnews | 전자신문 | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |
| yna | 연합뉴스 | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |
| hankyung | 한국경제 | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |
| maekyung | 매일경제 | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |
| aljazeera | Al Jazeera | static HTML | 이번 라운드 미검증 | **UNKNOWN** [주석1] |

### Phase 2 — community_signal 등

| source_id | name | 수집 방식 | status | final_decision |
|-----------|------|----------|--------|----------------|
| reddit | Reddit | JSON API (키 불요) | 동작하나 rate_limit 변동성 | **MVP_DEFERRED** [주석2] |
| hacker_news | Hacker News | JSON API (키 불요) | LIVE_SUCCESS | **CORE_READY** |
| product_hunt | Product Hunt | GraphQL API | **LIVE_SUCCESS (06-12 실측)** | **CORE_READY** |
| youtube | YouTube | JSON API | LIVE_SUCCESS | **CORE_READY** |
| dcinside | DCinside | Playwright | LIVE_PARTIAL, anti-bot 위험 | **READY_WITH_CAUTION** |
| fmkorea | 에펨코리아 | Playwright | BLOCKED — Cloudflare Turnstile | **MVP_EXCLUDED** |
| naver_blog_search | Naver Blog Search | REST API | LIVE_SUCCESS | **CORE_READY** |
| x | X (Twitter) | API/Web | BLOCKED — 유료 API + 로그인 | **MVP_EXCLUDED** |
| cnbc | CNBC | static HTML | consent 배너 위험 | **READY_WITH_CAUTION** |
| blind | Blind | Web | BLOCKED — 직장 이메일 로그인 | **MVP_EXCLUDED** |

### Phase 3 — official_evidence 등

| source_id | name | 수집 방식 | status | final_decision |
|-----------|------|----------|--------|----------------|
| gdelt | GDELT Project | REST API (키 불요) | LIVE_SUCCESS | **CORE_READY** |
| opendart | OpenDART | REST API | LIVE_SUCCESS | **CORE_READY** |
| sec_edgar | SEC EDGAR | REST API (키 불요) | LIVE_SUCCESS | **CORE_READY** |
| krx_kind | KRX KIND | Playwright(XHR) | 서버 오류 페이지 지속 | **DEFERRED_SPECIAL_ROUND** [주석3] |
| bok_ecos | 한국은행 ECOS | REST API | **LIVE_SUCCESS (06-12 실측)** | **CORE_READY** |
| eia | EIA | REST API | **LIVE_SUCCESS (06-12 실측)** | **CORE_READY** |
| federal_register | Federal Register | REST API (키 불요) | LIVE_SUCCESS | **CORE_READY** |
| eu_press_corner | EU Press Corner | Playwright | LIVE_SUCCESS | **CORE_READY** |
| naver_news_search | Naver News Search | REST API | LIVE_SUCCESS | **CORE_READY** |
| reuters | Reuters | Web | BLOCKED — 라이선스·봇 차단 | **MVP_EXCLUDED** |

### Phase 4 — search_enrichment

| source_id | name | status (06-12 실측) | final_decision |
|-----------|------|--------------------|----------------|
| google_programmable_search | Google Custom Search | CONFIG_ERROR (CX 미설정 400) | **MVP_EXCLUDED** (코드 보존) |
| serper | Serper | **LIVE_SUCCESS** | **CORE_READY** |
| tavily | Tavily AI Search | **LIVE_SUCCESS** | **CORE_READY** |
| exa | Exa Neural Search | **LIVE_SUCCESS** | **CORE_READY** |
| newsapi | NewsAPI | **LIVE_SUCCESS** — 일 100 req 상한·비상업 약관 | **READY_WITH_CAUTION** |
| gnews | GNews | **LIVE_SUCCESS** | **CORE_READY** |
| guardian | The Guardian | **LIVE_SUCCESS** — 일 5000 req·재배포 금지 약관 | **READY_WITH_CAUTION** |
| nyt | New York Times | **LIVE_SUCCESS** — 상업 라이선스 필요 | **READY_WITH_CAUTION** |

### Phase 4 — fast_signal

| source_id | name | status | final_decision |
|-----------|------|--------|----------------|
| google_trending_now | Google Trending Now | LIVE_SUCCESS (Playwright) | **CORE_READY** |
| signal_bz | Signal.bz | LIVE_SUCCESS (Playwright) | **CORE_READY** |
| loword | Loword | LIVE_SUCCESS — 셀렉터 취약, 월 1회 검증 | **CORE_READY** |
| google_trends_explore | (YAML 미등록) | RATE_LIMITED — 쿨다운 정상 동작 | **READY_WITH_CAUTION** |

### Phase 4 — market_signal

| source_id | name | status (06-12 실측) | final_decision |
|-----------|------|--------------------|----------------|
| finnhub | Finnhub | **LIVE_SUCCESS** | **CORE_READY** |
| twelve_data | Twelve Data | **LIVE_SUCCESS** | **CORE_READY** |
| alpha_vantage | Alpha Vantage | **LIVE_SUCCESS** (무료 일 25 req 유의) | **CORE_READY** |
| polygon | Polygon.io | **LIVE_SUCCESS** | **CORE_READY** |
| coinbase_market | Coinbase Market | LIVE_SUCCESS (키 불요) | **CORE_READY** |
| binance_market | Binance Market | LIVE_SUCCESS (키 불요) | **CORE_READY** |

### Phase 4 — domain_signal

| source_id | name | status (06-12 실측) | final_decision |
|-----------|------|--------------------|----------------|
| kma | 기상청 | **LIVE_SUCCESS** (data.go.kr 단기예보로 전환) | **CORE_READY** |
| tour | 한국관광공사 | **LIVE_SUCCESS** (KorService2로 전환) | **CORE_READY** |
| its | 국토교통부 ITS | **LIVE_SUCCESS** (/trafficInfo로 전환) | **CORE_READY** |
| kofic | 영화진흥위원회 KOBIS | **LIVE_SUCCESS** (env key: `KOFIC_API_KEY`) | **CORE_READY** |
| tmdb | TMDB | **LIVE_SUCCESS** | **CORE_READY** |
| kopis | 공연예술 KOPIS | **LIVE_SUCCESS** | **CORE_READY** |
| aladin | 알라딘 Open API | **LIVE_SUCCESS** (비상업 약관 유의) | **CORE_READY** |
| igdb | IGDB | **LIVE_SUCCESS** (Twitch OAuth) | **CORE_READY** |
| culture_info | 문화포털→한국문화정보원 | **LIVE_SUCCESS** (data.go.kr period2로 전환) | **CORE_READY** |

### 내부 픽스처

| source_id | 비고 |
|-----------|------|
| _dummy | 테스트 전용, 운영 대상 아님 |

---

## CORE_READY 38개 집합 (즉시 수집 가능)

```
문서/뉴스:    bbc, ap_news, techcrunch, the_verge
커뮤니티:    hacker_news, youtube, product_hunt
검색:        naver_news_search, naver_blog_search, serper, tavily, exa, gnews
공식 데이터: gdelt, sec_edgar, federal_register, opendart, bok_ecos, eia, eu_press_corner
트렌드:      signal_bz, google_trending_now, loword (저증거, 모니터링 필요)
시장:        finnhub, twelve_data, alpha_vantage, polygon, coinbase_market, binance_market
도메인:      kofic, igdb, tmdb, kopis, aladin, kma, tour, its, culture_info
```

## READY_WITH_CAUTION 6개

```
cnbc                  (consent 배너 — 수집 후 확인)
guardian              (일 5000 req 상한 + 재배포 금지 약관)
nyt                   (상업 라이선스 약관 검토 필요)
newsapi               (일 100 req 상한 — 빈도 제한 필수, 비상업 약관)
dcinside              (Playwright, 봇 감지 위험 상존)
google_trends_explore (RATE_LIMITED — 30분+ 간격, Redis 캐시 연동 시 안전)
```

---

## 각주

**[주석 1] Phase 1 미검증 6개 (zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera)**
- `implemented: true`, known_blockers 없음 → 코드는 구현 완료 상태.
- 이번 라운드는 "문제 소스 집중" 원칙(quota 절약)으로 정적 HTML 뉴스 소스는 호출하지 않았다.
- **검증 방법**: `run_collection_probe("{source_id}")` 실행 후 status 확인.

**[주석 2] reddit MVP_DEFERRED (사용자 확정, 2026-06-12)**
- public `.json` 엔드포인트는 키 없이 동작하지만, 비로그인 접근의 rate_limit 변동성이 커서 주기 수집의 안정성을 보장할 수 없다.
- MVP 수집 셋에서 보류. 코드(`ingestion/sources/reddit.py`)와 registry 항목은 보존.
- 재평가 시: Reddit OAuth(공식 API) 전환을 함께 검토.

**[주석 3] krx_kind DEFERRED_SPECIAL_ROUND**
- kind.krx.co.kr 웹 인터페이스가 자동화 접근에 서버 오류 페이지(1.3KB)만 반환 — 브라우저 전략으로 해결 불가 (docs/71 참조).
- 올바른 경로: `open.krx.co.kr` OpenAPI 가입·키 발급 후 REST 직접 호출 (사용자 액션 — docs/73 참조).

---

## 수집 인프라 상태

| 항목 | 상태 |
|------|------|
| Selenium (Chrome 렌더링 fallback) | LIVE_SUCCESS — selenium==4.26.1, Selenium Manager 자동 chromedriver |
| Playwright (JS 렌더링 주력) | 정상 — CloudBrowserLikeStrategy + probe 경로 |
| per-source 전략 budget (신규) | **구현 완료** — `retry_policy.yaml` `per_source:` 섹션 (docs/72 참조) |
| Artifact 저장소 | 정상 — raw_html/screenshots/extracted_text/jsonl 등 9종 |
| 테스트 스위트 | **359 passed, 0 failed** (기존 349 + 신규 10) |
| 보안 (키 유출) | PASS — outputs/docs 실키 0건 (2026-06-12 재스캔) |

---

## 2026-06-13 갱신 — Live Collection Audit 라운드 (docs/85~93)

전 소스 **용도 기준 실측**(1차 seed 40회 + 2차 enrichment 35회 + 시뮬레이션 16회)을 수행했다. "살아있는가"가 아니라 "이벤트 큐 seed/확장 수집에 쓸 수 있는가" 기준의 상태는 다음과 같다 (상세: docs/88·89·91):

| 분류 | 수 | 소스 |
|------|----|------|
| event_queue_ready (seed 즉시 투입) | 21 | 뉴스 RSS 8 + zdnet/etnews + youtube + opendart/sec_edgar + 도메인 7 + twelve_data + product_hunt |
| enrichment_ready (query 확장 실측 검증) | 9 | serper, tavily, exa, naver×2, gnews, guardian, nyt, youtube |
| caution (조건부 — 정비 후 투입) | 8 | **gdelt(429 ×2 실측)**, **ap_news(RSS가 HTML 에러 페이지)**, **newsapi(top-headlines+q 0건 — everything 전환 필요)**, signal_bz, loword/google_trending_now/dcinside/eu_press_corner(selector 보강) |
| not_ready (이번 기준) | 7 | hacker_news(id만), bok_ecos/eia/its(sample 매핑), 시장 수치 5종(별도 MarketSignal 경로) |

status 변화: ap_news LIVE_SUCCESS → **API_RETURNED_HTML_ERROR_PAGE** (실측), gdelt LIVE_SUCCESS → **불안정(RATE_LIMITED/PARSE_ERROR)**. 나머지 38/40 LIVE_SUCCESS 유지. 테스트 스위트 **509 passed** (450 + 신규 59), secret scan PASS(896 files).
