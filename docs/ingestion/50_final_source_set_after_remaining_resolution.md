# docs/50 — Final Source Set After Remaining Resolution

**Date**: 2026-06-08  
**기준**: docs/42 + 이번 라운드 결과 반영

---

## 5그룹 재분류 (56개 소스)

### A. CORE_READY (수집 가능, 키 있음/불필요)

| source_id | layer | phase | 비고 |
|---|---|---|---|
| bbc | document_discovery | 1 | RSS |
| ap_news | document_discovery | 1 | RSS |
| techcrunch | document_discovery | 1 | |
| the_verge | document_discovery | 1 | |
| ars_technica | document_discovery | 1 | |
| wired | document_discovery | 1 | |
| hacker_news | community_signal | 1 | API (키 불필요) |
| gdelt | official_evidence | 3 | API (키 불필요) |
| sec_edgar | official_evidence | 3 | API (키 불필요) |
| federal_register | official_evidence | 3 | API (키 불필요) |
| coinbase_market | market_signal | 3 | API (키 불필요) |
| binance_market | market_signal | 4 | API (키 불필요) |
| naver_news_search | search_enrichment | 2 | API 키 present |
| naver_blog_search | search_enrichment | 2 | API 키 present |
| youtube | domain_signal | 3 | API 키 present |
| opendart | official_evidence | 3 | API 키 present |
| kofic | domain_signal | 4 | API 키 present |
| eu_press_corner | official_evidence | 3 | **Playwright LIVE_SUCCESS** (셀렉터 수정) |
| loword | fast_signal | 4 | **Playwright LIVE_SUCCESS** (셀렉터 수정), evidence_level=low |
| signal_bz | fast_signal | 4 | Playwright (기존 성공) |
| google_trending_now | fast_signal | 4 | Playwright (기존 성공) |
| finnhub | market_signal | 4 | API 키 present |
| twelve_data | market_signal | 4 | API 키 present |
| alpha_vantage | market_signal | 4 | API 키 present |
| igdb | domain_signal | 4 | OAuth2 present |

### B. READY_WITH_CAUTION (수집 가능, 주의 필요)

| source_id | layer | 주의 사항 |
|---|---|---|
| cnbc | document_discovery | consent banner |
| guardian | document_discovery | API 키 present, 할당량 모니터 |
| nyt | document_discovery | API 키 present, 할당량 모니터 |
| newsapi | search_enrichment | API 키 present, 100req/day 무료 상한 |
| dcinside | community_signal | Playwright, anti-bot 위험 |
| google_trends_explore | fast_signal | 429 RATE_LIMITED, 30분 cooldown 준수 |

### C. REPAIRABLE_NEXT (수리 가능, 사전 조건 미충족)

| source_id | layer | 필요 조치 |
|---|---|---|
| culture_info | domain_signal | culture.go.kr 현행 endpoint 경로 재확인 + 승인 |
| kma | domain_signal | apihub.kma.go.kr 키 승인 (코드 수리 완료) |
| tour | domain_signal | TourAPI 현행 endpoint 확인 + Decoding 키 확인 |
| its | domain_signal | its.go.kr 키 승인 + endpoint path 재확인 |
| kopis | domain_signal | KOPIS 키 미설정 |
| tmdb | domain_signal | TMDB 키 미설정 |
| aladin | domain_signal | 알라딘 TTB 키 미설정 |
| polygon | market_signal | 키 미설정 |
| serper | search_enrichment | 키 미설정 |
| tavily | search_enrichment | 키 미설정 |
| exa | search_enrichment | 키 미설정 |
| gnews | search_enrichment | 키 미설정 |
| krx_kind | official_evidence | 서버 오류 지속 (2026-06-08 재확인) |
| product_hunt | community_signal | 키 미설정 |
| eia | domain_signal | 키 미설정 |
| bok_ecos | official_evidence | 키 미설정 |

### D. MVP_EXCLUDED (의도적 제외, 기록 보존)

| source_id | layer | 제외 이유 |
|---|---|---|
| x | community_signal | API 유료, login wall |
| blind | community_signal | 직장 이메일 인증 필수 |
| reuters | news_verification | Thomson Reuters 라이선스 |
| fmkorea | community_signal | Cloudflare Turnstile BLOCKED |
| google_programmable_search | search_enrichment | CX 미설정, 400 응답 (코드 보존) |

### E. DROP_OR_RESEARCH (추가 조사 필요)

| source_id | 이유 |
|---|---|
| wsj | paywall 제한 |
| ft | paywall 제한 |
| nikkei | paywall 제한 |

---

## 우선순위 요약

| 우선순위 | 소스 | 이유 |
|---|---|---|
| P0 | A그룹 전체 | 즉시 수집 가능 |
| P1 | B그룹 전체 | 소수 주의 필요 |
| P2 | C그룹 키 발급 소스 | 사용자 키 발급 후 즉시 수집 가능 |
| P3 | C그룹 endpoint 수리 소스 | 추가 코드 수정 필요 |
| Hold | D그룹 | 구조적 장벽 |
| TBD | E그룹 | 조사 후 결정 |
