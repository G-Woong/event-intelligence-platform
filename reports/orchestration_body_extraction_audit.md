# Orchestration Body Extraction Audit (5단계)

- (source, record_type) rows: 37 · classification: {'SNIPPET_ONLY': 8, 'BODY_OK': 11, 'STRUCTURED_NO_BODY_EXPECTED': 8, 'BODY_MISSING': 3, 'URL_CANDIDATE_DOWNSTREAM_SEPARATE': 7}
- extracted_text artifacts total: 68

## 판정 규칙
- article_candidate/official_record/community_signal → 본문 기대(present/extracted=성공, snippet_only/missing=미달)
- search_result → URL 후보형(downstream body fetch 별도, snippet_only는 설계상 정상)
- structured_signal(numeric/trend) → 본문 비대상(schema/record 수집 성공으로 판정)

| source | record_type | body_exp | queue | present | snippet | missing | extracted | success | class |
|---|---|---|---|---|---|---|---|---|---|
| ap_news | article_candidate | True | 284 | 0 | 284 | 0 | 10 | 10 | BODY_OK |
| yna | article_candidate | True | 240 | 0 | 240 | 0 | 2 | 2 | BODY_OK |
| bbc | article_candidate | True | 100 | 0 | 100 | 0 | 6 | 6 | BODY_OK |
| hankyung | article_candidate | True | 100 | 0 | 0 | 100 | 2 | 2 | BODY_OK |
| maekyung | article_candidate | True | 100 | 0 | 97 | 3 | 2 | 2 | BODY_OK |
| sec_edgar | official_record | True | 93 | 0 | 0 | 93 | 2 | 2 | BODY_OK |
| techcrunch | article_candidate | True | 60 | 0 | 60 | 0 | 2 | 2 | BODY_OK |
| aljazeera | article_candidate | True | 50 | 0 | 50 | 0 | 2 | 2 | BODY_OK |
| cnbc | article_candidate | True | 30 | 0 | 30 | 0 | 2 | 2 | BODY_OK |
| the_verge | article_candidate | True | 30 | 4 | 26 | 0 | 2 | 6 | BODY_OK |
| tmdb | official_record | True | 20 | 0 | 20 | 0 | 0 | 0 | SNIPPET_ONLY |
| culture_info | official_record | True | 10 | 0 | 8 | 2 | 0 | 0 | BODY_MISSING |
| kofic | official_record | True | 10 | 0 | 10 | 0 | 0 | 0 | SNIPPET_ONLY |
| nyt | article_candidate | True | 10 | 0 | 10 | 0 | 0 | 0 | SNIPPET_ONLY |
| product_hunt | community_signal | True | 6 | 0 | 6 | 0 | 0 | 0 | SNIPPET_ONLY |
| aladin | official_record | True | 3 | 0 | 3 | 0 | 0 | 0 | SNIPPET_ONLY |
| exa | search_result | False | 3 | 0 | 0 | 3 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| federal_register | official_record | True | 3 | 0 | 1 | 2 | 5 | 5 | BODY_OK |
| gnews | search_result | False | 3 | 0 | 3 | 0 | 1 | 1 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| igdb | official_record | True | 3 | 0 | 0 | 3 | 0 | 0 | BODY_MISSING |
| kopis | official_record | True | 3 | 0 | 3 | 0 | 0 | 0 | SNIPPET_ONLY |
| naver_blog_search | search_result | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| naver_news_search | search_result | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| opendart | official_record | True | 3 | 0 | 0 | 3 | 0 | 0 | BODY_MISSING |
| serper | search_result | False | 3 | 0 | 3 | 0 | 1 | 1 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| tavily | search_result | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| tour | official_record | True | 3 | 0 | 3 | 0 | 0 | 0 | SNIPPET_ONLY |
| youtube | community_signal | True | 3 | 0 | 3 | 0 | 0 | 0 | SNIPPET_ONLY |
| newsapi | search_result | False | 2 | 0 | 2 | 0 | 10 | 10 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| alpha_vantage | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| binance_market | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| coinbase_market | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| finnhub | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| google_trending_now | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| loword | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| signal_bz | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |
| twelve_data | structured_signal | False | 1 | 0 | 0 | 0 | 0 | 0 | STRUCTURED_NO_BODY_EXPECTED |

## extracted_text 전용(큐 미적재) 소스 — 본문 추출 레이어 실적

| source | extracted_artifacts |
|---|---|
| hacker_news | 4 |
| gdelt | 3 |
| dcinside | 2 |
| etnews | 2 |
| fmkorea | 2 |
| zdnet_korea | 2 |
| guardian | 1 |

## 핵심 결론(소스별 분리, 뭉뚱그리지 않음)
- 대부분 article_candidate는 **snippet_only**(RSS/검색 메타) — EventQueue 레이어는 URL+요약을 싣고, 전문은 **extracted_text/ 본문 추출 레이어**가 별도 적재(둔갑 아님). 두 레이어를 분리 집계.
- structured_signal은 본문 비대상 — numeric/trend schema 수집 자체가 성공(missing을 실패로 치지 않음).
- search_result는 URL 후보 확보가 1차 성공, 본문은 downstream 기사 fetch에서 별도 판정.

## Security
본문 전문은 보고서에 미포함(아티팩트 카운트/상태만). API 키/토큰 값 없음.