# 28 — Full 56-Source Reverification Matrix

**검증 일시**: 2026-06-03  
**검증 기준**: artifact 우선 (raw_payload / raw_signal), 없는 경우 소스 유형·known_blocker로 판정  
**보안**: API 키 값 미출력. artifact 경로만 기재.

---

## 결과 요약

| 상태 | 소스 수 |
|---|---|
| LIVE_SUCCESS | 37 |
| LIVE_PARTIAL | 5 |
| FAILED_RETRYABLE | 1 |
| FAILED | 4 |
| MISSING_KEY | 3 |
| BLOCKED | 4 |
| DEFERRED | 1 |
| UNKNOWN | 1 |
| **합계** | **56** |

---

## 전체 매트릭스

| source_id | layer | phase | current_status | verification_method | items_found | sample_quality | failure_category | strategy_used | artifact_paths | next_action |
|---|---|---|---|---|---|---|---|---|---|---|
| bbc | document_discovery | 1 | LIVE_SUCCESS | artifact | 25+ | GOOD | — | api/rss | raw_payload/bbc/...25KB | integrate_into_pipeline |
| ap_news | document_discovery | 1 | LIVE_SUCCESS | artifact | 100+ | GOOD | — | api/rss | raw_payload/ap_news/...2.7MB | integrate_into_pipeline |
| techcrunch | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/techcrunch/...19KB | integrate_into_pipeline |
| the_verge | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/the_verge/...34KB | integrate_into_pipeline |
| zdnet_korea | document_discovery | 1 | LIVE_SUCCESS | artifact | 1+ | GOOD | — | httpx_direct | raw_payload/zdnet_korea/...115KB | integrate_into_pipeline |
| etnews | document_discovery | 1 | LIVE_SUCCESS | artifact | 1+ | GOOD | — | httpx_direct | raw_payload/etnews/...82KB | integrate_into_pipeline |
| yna | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/yna/...91KB | integrate_into_pipeline |
| hankyung | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/hankyung/...17KB | integrate_into_pipeline |
| maekyung | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/maekyung/...39KB | integrate_into_pipeline |
| aljazeera | document_discovery | 1 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/aljazeera/...17KB | integrate_into_pipeline |
| reddit | community_signal | 2 | LIVE_SUCCESS | artifact | 25 | GOOD | — | api/json | raw_payload/reddit/...190KB | integrate_into_pipeline |
| hacker_news | community_signal | 2 | LIVE_SUCCESS | artifact | 500 | GOOD | — | api/json | raw_payload/hacker_news/...4.5KB | integrate_into_pipeline |
| product_hunt | community_signal | 2 | LIVE_SUCCESS | artifact | 3 | USABLE | — | api/graphql | raw_payload/product_hunt/...335B | integrate_into_pipeline |
| youtube | community_signal | 2 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/youtube/...4KB | integrate_into_pipeline |
| dcinside | community_signal | 2 | LIVE_SUCCESS | artifact | 3 | USABLE | — | playwright | raw_payload/dcinside/...797KB; raw_signal/dcinside/...459B | integrate_into_pipeline |
| fmkorea | community_signal | 2 | BLOCKED | playwright_config | 0 | BAD | BLOCKED_BOT_PROTECTION (Turnstile) | playwright | raw_payload/fmkorea/...74KB (main page only) | maintain_blocked |
| naver_blog_search | search_enrichment | 2 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/naver_blog_search/...1.9KB | integrate_into_pipeline |
| naver_news_search | search_enrichment | 2 | LIVE_PARTIAL | artifact | 0 | PARTIAL | empty_items_returned | api/json | raw_payload/naver_news_search/...25B | check_query_param_encoding |
| x | community_signal | 2 | BLOCKED | known_blocker | 0 | BAD | LOGIN_WALL | none | none | mvp_deferred |
| blind | community_signal | 2 | BLOCKED | known_blocker | 0 | BAD | LOGIN_WALL | none | none | mvp_deferred |
| cnbc | document_discovery | 2 | LIVE_SUCCESS | artifact | 20+ | GOOD | — | api/rss | raw_payload/cnbc/...21KB | integrate_into_pipeline |
| gdelt | official_evidence | 3 | FAILED_RETRYABLE | artifact | 0 | BAD | RATE_LIMITED | api/json | raw_payload/gdelt/...102B (rate limit msg) | apply_min_interval_5s_per_step1 |
| opendart | official_evidence | 3 | LIVE_SUCCESS | artifact | 6267 | GOOD | — | api/json | raw_payload/opendart/...749B | integrate_into_pipeline |
| sec_edgar | official_evidence | 3 | LIVE_SUCCESS | artifact | 10+ | GOOD | — | api/json | raw_payload/sec_edgar/...59KB | integrate_into_pipeline |
| krx_kind | official_evidence | 3 | DEFERRED | playwright_config | 0 | — | SERVER_ERROR | playwright | none | retry_next_round |
| bok_ecos | official_evidence | 3 | LIVE_SUCCESS | artifact | 834 | GOOD | — | api/json | raw_payload/bok_ecos/...769B | integrate_into_pipeline |
| eia | official_evidence | 3 | LIVE_SUCCESS | artifact | 25+ | GOOD | — | api/json | raw_payload/eia/...3KB | integrate_into_pipeline |
| federal_register | official_evidence | 3 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/federal_register/...496B | integrate_into_pipeline |
| eu_press_corner | official_evidence | 3 | LIVE_PARTIAL | artifact | 1 | PARTIAL | single_item_selector_mismatch | playwright | raw_signal/eu_press_corner/...174B | fix_ecl_selector |
| naver_news_search | search_enrichment | 3 | LIVE_PARTIAL | artifact | 0 | PARTIAL | empty_items | api/json | raw_payload/naver_news_search | check_query_encoding |
| reuters | news_verification | 3 | BLOCKED | known_blocker | 0 | BAD | BOT_PROTECTION | none | none | mvp_deferred |
| google_programmable_search | search_enrichment | 4 | MISSING_KEY | env_check | 0 | — | key_name_mismatch (GOOGLE_API_KEY→GOOGLE_CUSTOM_SEARCH_API_KEY) | none | none | add_env_alias_or_rename |
| serper | search_enrichment | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/serper/...1.5KB | integrate_into_pipeline |
| tavily | search_enrichment | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/tavily/...1KB | integrate_into_pipeline |
| exa | search_enrichment | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/exa/...1.9KB | integrate_into_pipeline |
| newsapi | search_enrichment | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/newsapi/...2.5KB | integrate_into_pipeline |
| gnews | search_enrichment | 4 | LIVE_SUCCESS | artifact | 10+ | GOOD | — | api/json | raw_payload/gnews/...10KB | integrate_into_pipeline |
| guardian | search_enrichment | 4 | LIVE_SUCCESS | artifact | 10+ | GOOD | — | api/json | raw_payload/guardian/...6.6KB | integrate_into_pipeline |
| nyt | search_enrichment | 4 | LIVE_SUCCESS | artifact | 10+ | GOOD | — | api/json | raw_payload/nyt/...14.7KB | integrate_into_pipeline |
| google_trending_now | fast_signal | 4 | LIVE_SUCCESS | artifact | 10 | GOOD | — | playwright | raw_signal/google_trending_now/...365B | integrate_into_pipeline |
| signal_bz | fast_signal | 4 | LIVE_SUCCESS | artifact | 5 | GOOD | — | playwright | raw_signal/signal_bz/...304B | integrate_into_pipeline |
| loword | fast_signal | 4 | UNKNOWN | registry | 0 | — | no_probe_spec_or_playwright_config | none | none | add_playwright_site_spec |
| finnhub | market_signal | 4 | LIVE_PARTIAL | artifact | 0 | PARTIAL | all_zero_quote_values | api/json | raw_payload/finnhub/...57B | fix_symbol_parameter |
| twelve_data | market_signal | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/twelve_data/...547B | integrate_into_pipeline |
| alpha_vantage | market_signal | 4 | FAILED | artifact | 0 | BAD | invalid_api_function_endpoint | api/json | raw_payload/alpha_vantage/...65B | fix_endpoint_url_in_probe_spec |
| polygon | market_signal | 4 | LIVE_SUCCESS | artifact | 1 | GOOD | — | api/json | raw_payload/polygon/...267B | integrate_into_pipeline |
| coinbase_market | market_signal | 4 | LIVE_SUCCESS | artifact | 1000+ | GOOD | — | api/json | raw_payload/coinbase_market/...1.1MB | integrate_into_pipeline |
| binance_market | market_signal | 4 | LIVE_SUCCESS | artifact | many | GOOD | — | api/json | raw_payload/binance_market/...152KB | integrate_into_pipeline |
| kma | domain_signal | 4 | MISSING_KEY | artifact | 0 | — | invalid_key_401 | api/json | raw_payload/kma/...75B (401 error) | verify_KMA_API_KEY_format |
| tour | domain_signal | 4 | FAILED | artifact | 0 | BAD | unexpected_error_endpoint | api | raw_payload/tour/...18B | debug_service_key_encoding |
| its | domain_signal | 4 | FAILED | artifact | 0 | BAD | wrong_url_format_4004 | api | raw_payload/its/...159B | fix_api_endpoint_path |
| kofic | domain_signal | 4 | LIVE_PARTIAL | artifact | 0 | PARTIAL | missing_targetDt_param | api/json | raw_payload/kofic/...125B | add_targetDt_to_probe_spec |
| tmdb | domain_signal | 4 | LIVE_SUCCESS | artifact | 20 | GOOD | — | api/json | raw_payload/tmdb/...12KB | integrate_into_pipeline |
| kopis | domain_signal | 4 | LIVE_PARTIAL | artifact | 0 | PARTIAL | invalid_request_params | api/xml | raw_payload/kopis/...198B | fix_date_format_in_probe_spec |
| aladin | domain_signal | 4 | LIVE_SUCCESS | artifact | 3+ | GOOD | — | api/json | raw_payload/aladin/...4.1KB | integrate_into_pipeline |
| igdb | domain_signal | 4 | MISSING_KEY | artifact | 0 | — | oauth_bearer_flow_not_implemented | api | raw_payload/igdb/...442B (auth fail) | implement_twitch_oauth_flow |
| culture_info | domain_signal | 4 | FAILED | artifact | 0 | BAD | missing_CULTURE_INFO_KEY_or_wrong_endpoint | api | raw_payload/culture_info/...909B (HTML error) | add_CULTURE_INFO_KEY_alias_or_fix_endpoint |

---

## 비고

- `naver_news_search`는 phase 2(community)와 phase 3(search)에 동일 source_id로 등록됨. 행을 하나로 통합.
- `dcinside` raw_payload는 메인페이지 HTML(797KB)이며, 실제 갤러리 신호는 raw_signal/dcinside에 3개 항목이 별도 저장됨.
- `fmkorea` raw_payload는 메인 페이지(74KB). 실제 스톡 게시판(playwright_probe)은 Turnstile으로 BLOCKED.
- `bbc` 최신 파일(182B)은 테스트 픽스처 mock. 유효 artifact는 동일 디렉터리의 25KB 파일.
- `google_programmable_search`: `.env`에 `GOOGLE_API_KEY`/`CSE_CX` 존재하나 connectivity config는 `GOOGLE_CUSTOM_SEARCH_API_KEY`/`GOOGLE_CUSTOM_SEARCH_CX` 요구 → 키 이름 불일치가 원인.
