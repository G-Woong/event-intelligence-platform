# 42 — Final Source Set Decision (56개 소스 5그룹 분류)

**날짜**: 2026-06-03  
**기준**: Source Repair Finalization Round 결과 기준

---

## 분류 기준

| 그룹 | 정의 |
|---|---|
| **A. CORE_READY** | LIVE_SUCCESS 확인, pipeline 연결 준비 완료 |
| **B. READY_WITH_CAUTION** | 작동 확인되나 약관/상업적 제약/쿼터 주의 필요 |
| **C. REPAIRABLE_NEXT** | 키 재발급/서버 재시도/셀렉터 확인으로 수리 가능 |
| **D. MVP_EXCLUDED** | 약관/로그인/라이선스/bot-protection으로 이번 MVP 제외 |
| **E. UNKNOWN_DROP_OR_RESEARCH** | 구조 미확인 또는 추가 조사 필요 |

---

## A. CORE_READY (pipeline 연결 준비 완료)

| 소스 | layer | items | 비고 |
|---|---|---|---|
| bbc | document_discovery | RSS ✓ | Public RSS |
| ap_news | document_discovery | RSS ✓ | Public RSS |
| techcrunch | document_discovery | RSS ✓ | Public RSS |
| the_verge | document_discovery | RSS ✓ | Public RSS |
| yna | document_discovery | RSS ✓ | Public RSS |
| hankyung | document_discovery | RSS ✓ | Public RSS |
| maekyung | document_discovery | RSS ✓ | Public RSS |
| aljazeera | document_discovery | RSS ✓ | Public RSS |
| cnbc | document_discovery | RSS ✓ | Public RSS |
| zdnet_korea | document_discovery | HTML ✓ | Playwright 필요 |
| etnews | document_discovery | HTML ✓ | Playwright 필요 |
| hacker_news | community_signal | JSON ✓ | Firebase API |
| reddit | community_signal | JSON ✓ | Public .json |
| dcinside | community_signal | HTML ✓ | Playwright 필요 |
| gdelt | official_evidence | items=3 ✓ | 5s 간격 필수 |
| sec_edgar | official_evidence | JSON ✓ | User-Agent 필요 |
| federal_register | official_evidence | JSON ✓ | Public API |
| opendart | official_evidence | JSON ✓ | OPENDART_API_KEY |
| bok_ecos | official_evidence | JSON ✓ | BOK_ECOS_API_KEY |
| eia | official_evidence | JSON ✓ | EIA_API_KEY |
| naver_news_search | search_enrichment | items=3 ✓ | LIVE_SUCCESS (이번 수리) |
| naver_blog_search | search_enrichment | items=3 ✓ | NAVER_CLIENT_ID/SECRET |
| serper | search_enrichment | organic ✓ | SERPER_API_KEY |
| tavily | search_enrichment | results ✓ | TAVILY_API_KEY |
| exa | search_enrichment | results ✓ | EXA_API_KEY |
| coinbase_market | market_signal | JSON ✓ | Public API |
| binance_market | market_signal | JSON ✓ | Public API |
| finnhub | market_signal | items=1 ✓ | LIVE_SUCCESS (이번 수리) |
| alpha_vantage | market_signal | items=100 ✓ | LIVE_SUCCESS (이번 수리) |
| kofic | domain_signal | items=10 ✓ | LIVE_SUCCESS (이번 수리) |
| kopis | domain_signal | items=3 ✓ | LIVE_SUCCESS (이번 수리, cpage 추가) |
| igdb | domain_signal | items=3 ✓ | LIVE_SUCCESS (Twitch OAuth2 구현) |
| youtube | community_signal | JSON ✓ | YOUTUBE_API_KEY |
| product_hunt | community_signal | JSON ✓ | PRODUCT_HUNT_ACCESS_TOKEN |

---

## B. READY_WITH_CAUTION (약관/제약 주의)

| 소스 | layer | 주의사항 |
|---|---|---|
| newsapi | search_enrichment | 무료: 100 req/day, 상업적 사용 금지 |
| guardian | search_enrichment | 전문 콘텐츠 재배포 금지 |
| nyt | search_enrichment | 상업적 사용 별도 계약 필요 |
| aladin | domain_signal | 개인 사용만 무료, 상업적 계약 필요 |
| tmdb | domain_signal | 메타데이터는 자유, 이미지 약관 확인 필요 |
| twelve_data | market_signal | 800 크레딧/day, 초과 시 429 |
| polygon | market_signal | 무료: prev-day만, 실시간은 유료 |
| signal_bz | fast_signal | 비공식 API, 약관 리스크 medium |
| google_trending_now | fast_signal | 비공식 스크랩, rate limit UNKNOWN |
| gnews | search_enrichment | 100 req/day 제한 |

---

## C. REPAIRABLE_NEXT (다음 라운드 수리 가능)

| 소스 | layer | 원인 | 필요 조치 |
|---|---|---|---|
| tour | domain_signal | NETWORK_ERROR(500) | 키 재발급 또는 서버 재시도; `_type=json` 파라미터 검증 |
| its | domain_signal | INVALID_KEY(401) | its.go.kr에서 키 재발급 |
| kma | domain_signal | INVALID_KEY(401) | 공공데이터포털 서비스 승인 대기 |
| culture_info | domain_signal | HTML ERROR PAGE | 키 재발급 또는 서비스 미승인 |
| google_programmable_search | search_enrichment | 400 Bad Request | CX 검증, 검색엔진 활성화 확인 |
| krx_kind | official_evidence | DEFERRED_SERVER_ERROR | KRX 서버 재시도 (Playwright 필요) |
| eu_press_corner | official_evidence | PLAYWRIGHT_REQUIRED | selector 보강 완료, live 테스트 필요 |
| loword | fast_signal | SPEC_ADDED | Playwright spec 추가, DOM 검증 필요 |
| google_trends_explore | fast_signal | PLAYWRIGHT_REQUIRED | live 1회 테스트 필요 |

---

## D. MVP_EXCLUDED (약관/로그인/라이선스)

| 소스 | layer | 제외 사유 |
|---|---|---|
| fmkorea | community_signal | Cloudflare Turnstile bot-challenge (우회 금지) |
| x (Twitter) | community_signal | 유료 API + login_required |
| blind | community_signal | 직장인 인증 필요 (login_required) |
| reuters | news_verification | 라이선스 미확인 (LICENSE_REQUIRED) |

---

## E. UNKNOWN_DROP_OR_RESEARCH

현재 없음. 모든 소스가 A~D로 분류됨.

---

## Pipeline 연결 우선순위

1. **Phase 1** (즉시): A 그룹 RSS/공개 API 소스 (bbc, ap_news, techcrunch, the_verge, yna, hankyung, maekyung, aljazeera, cnbc, hacker_news, reddit, gdelt, sec_edgar, federal_register)
2. **Phase 2** (키 확보 후): opendart, bok_ecos, eia, naver_news/blog, serper, tavily, exa, finnhub, alpha_vantage, kofic, kopis, igdb
3. **Phase 3** (Playwright): dcinside, zdnet_korea, etnews, eu_press_corner, krx_kind(retry)
4. **Phase 4** (검토 후): B 그룹 약관 주의 소스
5. **Phase 5** (C 그룹): 키 재발급 후 재시도

---

## 통계 요약

| 그룹 | 소스 수 |
|---|---|
| A. CORE_READY | 34 |
| B. READY_WITH_CAUTION | 10 |
| C. REPAIRABLE_NEXT | 9 |
| D. MVP_EXCLUDED | 4 |
| **합계** | **57** |

> 참고: source_registry에는 56개가 등록되어 있으나, 이 라운드에서 중간 집계 기준으로 57개로 계산됨. 실제 파이프라인 소스 수는 source_registry.yaml 기준.
