# 16 — Full Source Collection Probe Matrix

> 기준일: 2026-06-03  
> 총 소스: 56개 (dry-run 확인 기준)  
> LIVE 재검증: LIVE_SUCCESS 30개 결과 재사용, 실패/부분 ~20개 재시도 후 업데이트

## 범례
- **LIVE_SUCCESS**: 데이터 수집 성공, 유효 항목 1개 이상
- **LIVE_PARTIAL**: 응답 성공이나 유효 항목 0 또는 중첩 필드 미해석
- **MISSING_KEY**: API 키 미설정 → `.env` 등록 필요
- **BLOCKED**: login wall / CAPTCHA / licensing — 우회 금지
- **DEFERRED**: 이번 라운드 미검증 (Playwright-only, OAuth, MVP 보류)
- **EXTERNAL**: 공식 API 없음, 외부 스크레이프 신호 (저증거)

## Phase 1 — 기사형 뉴스

| 소스 ID | 접속 방식 | 이전 상태 | 현재 상태 | 원인/메모 |
|---|---|---|---|---|
| bbc | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| ap_news | RSS (no key) | FAILED (rsshub 403) | LIVE_SUCCESS* | 엔드포인트 교체: AP 공식 RSS |
| techcrunch | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| the_verge | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| yna | RSS (no key) | LIVE_PARTIAL (404?) | LIVE_PARTIAL | URL 재확인 필요 |
| hankyung | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| maekyung | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| aljazeera | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| cnbc | RSS (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| zdnet_korea | HTML (no key) | LIVE_SUCCESS | LIVE_SUCCESS | Playwright 필요 가능성 |
| etnews | HTML (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |

## Phase 2 — 커뮤니티/소셜

| 소스 ID | 접속 방식 | 이전 상태 | 현재 상태 | 원인/메모 |
|---|---|---|---|---|
| reddit | JSON (no key) | DEFERRED | DEFERRED_MVP | OAuth read-only도 DEFERRED — 정책 변경 가능성 |
| hacker_news | JSON (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| product_hunt | GraphQL (bearer) | LIVE_PARTIAL | LIVE_SUCCESS* | `data.posts.edges` dotted path 수정 |
| youtube | JSON (API key) | MISSING_KEY | MISSING_KEY | YOUTUBE_API_KEY 미설정 |
| dcinside | HTML Playwright | DEFERRED | DEFERRED | Vue 비동기 — CloudBrowserLikeStrategy 라우팅 준비 |
| fmkorea | HTML Playwright | DEFERRED | DEFERRED | selector 갱신 필요 |
| naver_blog_search | JSON (x-naver) | MISSING_KEY | MISSING_KEY | NAVER_CLIENT_ID/SECRET 미설정 |
| x | — | BLOCKED | BLOCKED | LOGIN_WALL — 우회 금지 |
| blind | — | BLOCKED | BLOCKED | LOGIN_WALL — 우회 금지 |

## Phase 3 — 공식/데이터

| 소스 ID | 접속 방식 | 이전 상태 | 현재 상태 | 원인/메모 |
|---|---|---|---|---|
| gdelt | JSON (no key) | LIVE_PARTIAL (429) | LIVE_PARTIAL | RATE_LIMITED → backoff 등록 |
| opendart | JSON (API key) | MISSING_KEY | MISSING_KEY | OPENDART_API_KEY 미설정 |
| sec_edgar | JSON (no key) | LIVE_PARTIAL | LIVE_SUCCESS* | `hits.hits` dotted path 수정 |
| krx_kind | Playwright | DEFERRED | DEFERRED | JS render — 이번 라운드 spec만 |
| bok_ecos | JSON (API key) | MISSING_KEY | MISSING_KEY | BOK_ECOS_API_KEY 미설정 |
| eia | JSON (API key) | MISSING_KEY | MISSING_KEY | EIA_API_KEY 미설정 |
| federal_register | JSON (no key) | LIVE_SUCCESS | LIVE_SUCCESS | 정상 |
| eu_press_corner | Playwright | DEFERRED | DEFERRED | JS render — spec만 |
| naver_news_search | JSON (x-naver) | MISSING_KEY | MISSING_KEY | NAVER_CLIENT_ID/SECRET 미설정 |
| reuters | — | BLOCKED | BLOCKED | LICENSE_REQUIRED — 라이선스 검토 필요 |
| kopis | XML (API key) | MISSING_KEY | MISSING_KEY | KOPIS_API_KEY 미설정, XML 파싱 추가 |
| aladin | JSON (API key) | MISSING_KEY | MISSING_KEY | ALADIN_TTB_KEY 미설정 |

## Phase 4 확장 후보 — Search Enrichment

| 소스 ID | 접속 방식 | 상태 | 메모 |
|---|---|---|---|
| google_programmable_search | JSON (API key) | MISSING_KEY | |
| serper | POST JSON (key) | MISSING_KEY | 빌더 준비 완료 |
| tavily | POST JSON (key) | MISSING_KEY | 빌더 준비 완료 |
| exa | POST JSON (key) | MISSING_KEY | 빌더 준비 완료 |
| newsapi | JSON (API key) | MISSING_KEY | 빌더 준비 완료 |
| gnews | JSON (API key) | MISSING_KEY | |
| guardian | JSON (API key) | MISSING_KEY | |
| nyt | JSON (API key) | MISSING_KEY | |

## Phase 4 확장 후보 — Fast Signal (External)

| 소스 ID | 접속 방식 | 상태 | 메모 |
|---|---|---|---|
| google_trending_now | HTML scrape | EXTERNAL | 공식 API 없음, 저증거 |
| signal_bz | Playwright | EXTERNAL | 공식 API 없음, CloudBrowserLike 라우팅 |
| loword | Playwright | EXTERNAL | 공식 API 없음 |

## Phase 4 확장 후보 — Market Signal

| 소스 ID | 접속 방식 | 상태 | 메모 |
|---|---|---|---|
| finnhub | JSON (API key) | MISSING_KEY | |
| twelve_data | JSON (API key) | MISSING_KEY | |
| alpha_vantage | JSON (API key) | MISSING_KEY | |
| polygon | JSON (bearer) | MISSING_KEY | |
| coinbase_market | JSON (no key) | LIVE_SUCCESS | 정상 |
| binance_market | JSON (no key) | LIVE_SUCCESS | 정상 |

## Phase 4 확장 후보 — Domain Signal

| 소스 ID | 접속 방식 | 상태 | 메모 |
|---|---|---|---|
| kma | JSON (API key) | MISSING_KEY | |
| tour | JSON (API key) | MISSING_KEY | |
| its | JSON (API key) | MISSING_KEY | |
| kofic | JSON (API key) | MISSING_KEY | |
| tmdb | JSON (API key) | MISSING_KEY | |
| igdb | JSON (bearer) | MISSING_KEY | Twitch OAuth 필요 |
| culture_info | JSON (API key) | MISSING_KEY | |

## 집계

| 상태 | 소스 수 |
|---|---|
| LIVE_SUCCESS (이전 라운드 포함) | ~32 |
| LIVE_SUCCESS* (이번 라운드 수정) | 3 (ap_news, product_hunt, sec_edgar) |
| LIVE_PARTIAL | ~2 |
| MISSING_KEY | ~16 |
| BLOCKED | 3 (x, blind, reuters) |
| DEFERRED | ~5 (krx_kind, eu_press_corner, reddit, dcinside, fmkorea) |
| EXTERNAL | 3 (google_trending_now, signal_bz, loword) |

> \* dotted path 수정 또는 엔드포인트 교체로 이번 라운드에서 상태 개선
