# Source Layer Matrix

> Dry-run expanded source coverage report (Round 1.5 + Phase 4 candidates).
> Live 호출 없음. 상태는 key presence dry-run 기준.

## Layer 정의

| Layer | 설명 |
|---|---|
| `document_discovery` | 뉴스 기사/리포트 — 신뢰도 높은 원문 수집 |
| `community_signal` | 커뮤니티/소셜 반응 신호 |
| `search_enrichment` | 검색 API 기반 이벤트 후보 보강 |
| `official_evidence` | 공식 기관/데이터 소스 — 최고 신뢰도 |
| `news_verification` | 보도 검증 소스 (라이선스/API 필요) |
| `market_signal` | 시장 데이터 신호 (가격/거래량) |
| `domain_signal` | 도메인 특화 공공 데이터 |
| `fast_signal` | 실시간 트렌드 신호 (공식 API 없음, low evidence) |

---

## Phase 1–3 구현 소스 (30개)

| source_id | source_name | layer | input_type | auth_required | env_keys | evidence_level | mvp_priority | commercial_risk | terms_risk | status |
|---|---|---|---|---|---|---|---|---|---|---|
| bbc | BBC News | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| ap_news | AP News | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| techcrunch | TechCrunch | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| the_verge | The Verge | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| zdnet_korea | ZDNet Korea | document_discovery | HTML | no | - | tier2 | P0 | low | low | ALLOWED |
| etnews | 전자신문 | document_discovery | HTML | no | - | tier2 | P0 | low | low | ALLOWED |
| yna | 연합뉴스 | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| hankyung | 한국경제 | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| maekyung | 매일경제 | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| aljazeera | Al Jazeera | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| cnbc | CNBC | document_discovery | RSS | no | - | tier1 | P0 | low | low | ALLOWED |
| reddit | Reddit | community_signal | JSON API | no | - | tier2 | P0 | low | low | ALLOWED |
| hacker_news | Hacker News | community_signal | JSON API | no | - | tier2 | P0 | low | low | ALLOWED |
| product_hunt | Product Hunt | community_signal | GraphQL | yes | PRODUCT_HUNT_ACCESS_TOKEN | tier2 | P1 | low | low | ALLOWED (key required) |
| youtube | YouTube | community_signal | JSON API | yes | YOUTUBE_API_KEY | tier2 | P1 | low | low | ALLOWED (key required) |
| dcinside | DCinside | community_signal | HTML | no | - | tier3 | P1 | low | medium | ALLOWED (robots.txt 확인) |
| fmkorea | 에펨코리아 | community_signal | HTML | no | - | tier3 | P1 | low | medium | ALLOWED (robots.txt 확인) |
| naver_blog_search | Naver Blog Search | search_enrichment | JSON API | yes | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET | tier2 | P0 | low | low | ALLOWED (key required) |
| naver_news_search | Naver News Search | search_enrichment | JSON API | yes | NAVER_CLIENT_ID, NAVER_CLIENT_SECRET | tier2 | P0 | low | low | ALLOWED (key required) |
| x | X (Twitter) | community_signal | — | yes (login) | - | tier2 | — | — | — | BLOCKED |
| blind | Blind | community_signal | — | yes (login) | - | tier3 | — | — | — | BLOCKED |
| gdelt | GDELT Project | official_evidence | JSON API | no | - | tier1 | P0 | low | low | ALLOWED |
| opendart | OpenDART | official_evidence | JSON API | yes | OPENDART_API_KEY | tier1 | P0 | low | low | ALLOWED (key required) |
| sec_edgar | SEC EDGAR | official_evidence | JSON API | no | - | tier1 | P0 | low | low | ALLOWED |
| krx_kind | KRX KIND | official_evidence | HTML (JS) | no | - | tier1 | P1 | low | low | NEEDS_PLAYWRIGHT |
| bok_ecos | BOK ECOS | official_evidence | JSON API | yes | BOK_ECOS_API_KEY | tier1 | P0 | low | low | ALLOWED (key required) |
| eia | EIA | official_evidence | JSON API | yes | EIA_API_KEY | tier1 | P0 | low | low | ALLOWED (key required) |
| federal_register | Federal Register | official_evidence | JSON API | no | - | tier1 | P0 | low | low | ALLOWED |
| eu_press_corner | EU Press Corner | official_evidence | HTML (JS) | no | - | tier1 | P1 | low | low | NEEDS_PLAYWRIGHT |
| reuters | Reuters | news_verification | — | license | - | tier1 | P2 | high | high | NEEDS_LICENSE_OR_API |

---

## Phase 4 확장 후보 (implemented: false)

### search_enrichment

| source_id | source_name | layer | env_keys | free_plan | commercial_risk | terms_risk | status | next_action |
|---|---|---|---|---|---|---|---|---|
| google_programmable_search | Google Programmable Search | search_enrichment | GOOGLE_CUSTOM_SEARCH_API_KEY, GOOGLE_CUSTOM_SEARCH_CX | 100 req/day | low | low | MISSING_KEY | set keys via Google Cloud Console |
| serper | Serper | search_enrichment | SERPER_API_KEY | 2500 free | low | low | MISSING_KEY | set SERPER_API_KEY |
| tavily | Tavily | search_enrichment | TAVILY_API_KEY | 1000 req/month | low | low | MISSING_KEY | set TAVILY_API_KEY |
| exa | Exa | search_enrichment | EXA_API_KEY | 1000 req/month | low | low | MISSING_KEY | set EXA_API_KEY |
| newsapi | NewsAPI | search_enrichment | NEWSAPI_API_KEY | 100 req/day | medium | medium | MISSING_KEY | commercial plan review required |
| gnews | GNews | search_enrichment | GNEWS_API_KEY | 100 req/day | low | low | MISSING_KEY | set GNEWS_API_KEY |
| guardian | The Guardian | search_enrichment | GUARDIAN_API_KEY | 5000 req/day | medium | medium | MISSING_KEY | no commercial redistribution |
| nyt | New York Times | search_enrichment | NYT_API_KEY | 500 req/day | high | high | MISSING_KEY | commercial license required |

### fast_signal (external)

| source_id | source_name | layer | env_keys | evidence_level | status | next_action |
|---|---|---|---|---|---|---|
| google_trending_now | Google Trending Now | fast_signal | none | tier3 | EXTERNAL_SIGNAL_SOURCE | assess HTML scrape feasibility |
| signal_bz | Signal.bz | fast_signal | none | tier3 | EXTERNAL_SIGNAL_SOURCE | assess HTML scrape feasibility |
| loword | Loword | fast_signal | none | tier3 | EXTERNAL_SIGNAL_SOURCE | assess HTML scrape feasibility |

### market_signal

| source_id | source_name | layer | env_keys | free_plan | status | next_action |
|---|---|---|---|---|---|---|
| finnhub | Finnhub | market_signal | FINNHUB_API_KEY | 60 req/min | MISSING_KEY | set FINNHUB_API_KEY |
| twelve_data | Twelve Data | market_signal | TWELVE_DATA_API_KEY | 800 credits/day | MISSING_KEY | set TWELVE_DATA_API_KEY |
| alpha_vantage | Alpha Vantage | market_signal | ALPHA_VANTAGE_API_KEY | 25 req/day | MISSING_KEY | set ALPHA_VANTAGE_API_KEY |
| polygon | Polygon.io | market_signal | POLYGON_API_KEY | unlimited prev-day | MISSING_KEY | set POLYGON_API_KEY |
| coinbase_market | Coinbase Market | market_signal | none | public data | NO_KEY_REQUIRED | ready for live test |
| binance_market | Binance Market | market_signal | none | public data | NO_KEY_REQUIRED | ready for live test |

### domain_signal

| source_id | source_name | layer | env_keys | free_plan | status | next_action |
|---|---|---|---|---|---|---|
| kma | 기상청 KMA | domain_signal | KMA_API_KEY | free/data.go.kr | MISSING_KEY | set KMA_API_KEY |
| tour | 한국관광공사 TourAPI | domain_signal | TOUR_API_KEY | free/data.go.kr | MISSING_KEY | set TOUR_API_KEY |
| its | 국토교통부 ITS | domain_signal | ITS_API_KEY | free/its.go.kr | MISSING_KEY | set ITS_API_KEY |
| kofic | 영화진흥위원회 KOBIS | domain_signal | KOBIS_API_KEY | free/kobis.or.kr | MISSING_KEY | set KOBIS_API_KEY |
| tmdb | TMDB | domain_signal | TMDB_API_KEY | ~100 req/hour | MISSING_KEY | set TMDB_API_KEY |
| kopis | KOPIS | domain_signal | KOPIS_API_KEY | free/kopis.or.kr | MISSING_KEY | set KOPIS_API_KEY |
| aladin | 알라딘 | domain_signal | ALADIN_TTB_KEY | personal free | MISSING_KEY | commercial review required |
| igdb | IGDB | domain_signal | IGDB_CLIENT_ID, IGDB_CLIENT_SECRET | unlimited/Twitch OAuth | MISSING_KEY | set Twitch app credentials |
| culture_info | 문화포털 | domain_signal | CULTURE_INFO_API_KEY | free/culture.go.kr | MISSING_KEY | set CULTURE_INFO_API_KEY |
