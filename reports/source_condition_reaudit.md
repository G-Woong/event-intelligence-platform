# Conditional Source Re-audit Matrix (4단계)

- profiles: 57 · conditional(tested-scope): 48 · excluded(POLICY/BLOCKED): 9
- this-turn live: gdelt={'status': 'PROVIDER_429', 'rows': 0, 'body': 0} · dcinside={'status': 'LIMITED_PUBLIC_BODY', 'list': 30, 'body': 1}

## Excluded (POLICY_EXCLUDED / BLOCKED_EXTERNAL) — 감사 대상 제외, 목록만

| source | status | reason |
|---|---|---|
| google_trends_explore | POLICY_EXCLUDED | requires_official_api_or_contract |
| its | POLICY_EXCLUDED | not_service_useful |
| reddit | POLICY_EXCLUDED | disabled_by_policy |
| fmkorea | POLICY_EXCLUDED | disabled_by_policy |
| x | POLICY_EXCLUDED | login_wall_no_bypass |
| blind | POLICY_EXCLUDED | login_wall_no_bypass |
| krx_kind | POLICY_EXCLUDED | needs_api_integration |
| reuters | POLICY_EXCLUDED | paywall_no_bypass |
| google_programmable_search | POLICY_EXCLUDED | disabled_by_policy |

## Conditional sources (matrix)

| source | route | cond_before | cond_after | env | queue | raw | body_exp | body_ok | fail | fresh | action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ap_news | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 284 | 84 | True | 10 | - | has_records | ok |
| yna | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 240 | 240 | True | 2 | - | has_records | ok |
| bbc | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 100 | 66 | True | 6 | - | has_records | ok |
| hankyung | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 100 | 100 | True | 2 | - | has_records | ok |
| maekyung | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 100 | 100 | True | 2 | - | has_records | ok |
| sec_edgar | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 93 | 93 | True | 2 | - | has_records | ok |
| techcrunch | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 60 | 20 | True | 2 | - | has_records | ok |
| aljazeera | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 50 | 50 | True | 2 | - | has_records | ok |
| cnbc | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 30 | 30 | True | 2 | - | has_records | ok |
| the_verge | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 30 | 20 | True | 6 | - | has_records | ok |
| tmdb | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 20 | 20 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| culture_info | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 10 | 10 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| kofic | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 10 | 10 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| nyt | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 10 | 10 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| product_hunt | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 6 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| aladin | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| exa | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| federal_register | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 5 | - | has_records | ok |
| gnews | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 1 | - | has_records | ok |
| igdb | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| kopis | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| naver_blog_search | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| naver_news_search | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| opendart | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| serper | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 1 | - | has_records | ok |
| tavily | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| tour | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| youtube | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 3 | 3 | True | 0 | body_snippet_only_or_mis | has_records | needs_body_extraction_review |
| newsapi | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 2 | 2 | True | 10 | - | has_records | ok |
| alpha_vantage | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| binance_market | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| coinbase_market | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| finnhub | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| google_trending_now | playwright | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| loword | playwright | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| signal_bz | playwright | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| twelve_data | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 1 | 0 | False | 0 | body_not_expected_struct | has_records | ok |
| bok_ecos | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 0 | - | stale | needs_live_probe |
| dcinside | playwright | PRODUCTION_READY_COMMUNITY_PREVIEW | LIMITED_PUBLIC_BODY | present | 0 | 0 | True | 2 | - | stale | needs_live_probe |
| eia | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 0 | - | stale | needs_live_probe |
| etnews | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 2 | - | stale | needs_live_probe |
| eu_press_corner | playwright | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 0 | - | stale | needs_live_probe |
| gdelt | vendor_route | EXTERNAL_RATE_LIMITED | EXTERNAL_RATE_LIMITED_PENDING_RESUME | present | 0 | 0 | True | 3 | PROVIDER_429_external | never_collected | await_non_throttled_window_then_reprobe |
| guardian | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 1 | - | stale | needs_live_probe |
| hacker_news | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 4 | - | stale | needs_live_probe |
| kma | vendor_route | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 0 | - | stale | needs_live_probe |
| polygon | scrape:api_json_fetch | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | False | 0 | body_not_expected_struct | stale | needs_live_probe |
| zdnet_korea | api_probe | PRODUCTION_READY | PRODUCTION_READY | present | 0 | 0 | True | 2 | - | stale | needs_live_probe |

## Summary
- 조건부 소스 중 records 보유(또는 이번턴 라이브): 39/48
- records 0(미수집/재probe 필요): 9
- body_expected & body_success>0: 20
- structured(본문 비대상): 9

## Note
- 이번 턴 실제 라이브 probe: gdelt(PROVIDER_429), dcinside(LIMITED_PUBLIC_BODY). 나머지는 권위 production_state + 실적 아티팩트(queue/raw/extracted_text) 기준(직전 검증 상태).
- body_success는 queue body_state=present + extracted_text 아티팩트 합산(역사적 실적). 전수 라이브 재probe는 rate-limit/키 비용 때문에 분할 필요(action_required로 표시).