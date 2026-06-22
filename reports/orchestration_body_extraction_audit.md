# Orchestration Body Extraction Audit (5단계)

- (source, record_type) rows: 37 · classification: {'STRUCTURED_METADATA_COMPLETE': 14, 'BODY_OK': 11, 'BODY_MISSING': 2, 'URL_CANDIDATE_DOWNSTREAM_SEPARATE': 7, 'SNIPPET_ONLY': 1, 'COMMUNITY_SIGNAL_OK': 2}
- extracted_text artifacts total: 68

## 판정 규칙 (콘텐츠 타입 기준 — source_content_type)
- article/document/detail(예: bbc·nyt·opendart·culture_info) → body_expected=true(산문 본문 추출 대상)
- catalog/metadata API(aladin·tmdb·kofic·kopis·tour·igdb) → **metadata_complete**: summary/overview=metadata_summary, 본문 미추출이 실패 아님(STRUCTURED_METADATA_COMPLETE)
- search API → URL 후보형(downstream body fetch 별도)
- community/list → conditional(corroboration 후 판단)
- structured/numeric → schema 수집 자체가 성공

| source | record_type | content_type | body_exp | queue | present | snippet | missing | extracted | success | class |
|---|---|---|---|---|---|---|---|---|---|---|
| ap_news | article_candidate | article | True | 284 | 0 | 284 | 0 | 10 | 10 | BODY_OK |
| yna | article_candidate | article | True | 240 | 0 | 240 | 0 | 2 | 2 | BODY_OK |
| bbc | article_candidate | article | True | 100 | 0 | 100 | 0 | 6 | 6 | BODY_OK |
| hankyung | article_candidate | article | True | 100 | 0 | 0 | 100 | 2 | 2 | BODY_OK |
| maekyung | article_candidate | article | True | 100 | 0 | 97 | 3 | 2 | 2 | BODY_OK |
| sec_edgar | official_record | document | True | 93 | 0 | 0 | 93 | 2 | 2 | BODY_OK |
| techcrunch | article_candidate | article | True | 60 | 0 | 60 | 0 | 2 | 2 | BODY_OK |
| aljazeera | article_candidate | article | True | 50 | 0 | 50 | 0 | 2 | 2 | BODY_OK |
| cnbc | article_candidate | article | True | 30 | 0 | 30 | 0 | 2 | 2 | BODY_OK |
| the_verge | article_candidate | article | True | 30 | 4 | 26 | 0 | 2 | 6 | BODY_OK |
| tmdb | official_record | catalog_metadata | False | 20 | 0 | 20 | 0 | 0 | 20 | STRUCTURED_METADATA_COMPLETE |
| culture_info | official_record | detail | True | 10 | 0 | 8 | 2 | 0 | 0 | BODY_MISSING |
| kofic | official_record | catalog_metadata | False | 10 | 0 | 10 | 0 | 0 | 10 | STRUCTURED_METADATA_COMPLETE |
| nyt | article_candidate | article | True | 10 | 0 | 10 | 0 | 0 | 0 | SNIPPET_ONLY |
| product_hunt | community_signal | community | False | 6 | 0 | 6 | 0 | 0 | 6 | COMMUNITY_SIGNAL_OK |
| aladin | official_record | catalog_metadata | False | 3 | 0 | 3 | 0 | 0 | 3 | STRUCTURED_METADATA_COMPLETE |
| exa | search_result | search | False | 3 | 0 | 0 | 3 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| federal_register | official_record | document | True | 3 | 0 | 1 | 2 | 5 | 5 | BODY_OK |
| gnews | search_result | search | False | 3 | 0 | 3 | 0 | 1 | 1 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| igdb | official_record | catalog_metadata | False | 3 | 0 | 0 | 3 | 0 | 0 | STRUCTURED_METADATA_COMPLETE |
| kopis | official_record | catalog_metadata | False | 3 | 0 | 3 | 0 | 0 | 3 | STRUCTURED_METADATA_COMPLETE |
| naver_blog_search | search_result | search | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| naver_news_search | search_result | search | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| opendart | official_record | document | True | 3 | 0 | 0 | 3 | 0 | 0 | BODY_MISSING |
| serper | search_result | search | False | 3 | 0 | 3 | 0 | 1 | 1 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| tavily | search_result | search | False | 3 | 0 | 3 | 0 | 0 | 0 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| tour | official_record | catalog_metadata | False | 3 | 0 | 3 | 0 | 0 | 3 | STRUCTURED_METADATA_COMPLETE |
| youtube | community_signal | community | False | 3 | 0 | 3 | 0 | 0 | 3 | COMMUNITY_SIGNAL_OK |
| newsapi | search_result | search | False | 2 | 0 | 2 | 0 | 10 | 10 | URL_CANDIDATE_DOWNSTREAM_SEPARATE |
| alpha_vantage | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| binance_market | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| coinbase_market | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| finnhub | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| google_trending_now | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| loword | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| signal_bz | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |
| twelve_data | structured_signal | structured | False | 1 | 0 | 0 | 0 | 0 | 1 | STRUCTURED_METADATA_COMPLETE |

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
- **카탈로그형(aladin·tmdb·kofic·kopis·tour·igdb)은 본문 미추출이 아니라 구조화 메타데이터 수집 성공**(STRUCTURED_METADATA_COMPLETE) — 별도 산문 본문이 없으므로 BODY_MISSING/SNIPPET_ONLY 실패로 치지 않음.
- article(bbc/ap_news 등)은 EventQueue에 URL+요약(snippet)을 싣고 전문은 extracted_text/ 별도 레이어 적재.
- **body ladder 연결 대상은 산문형(nyt·opendart·culture_info)만** — body_ladder_probe로 별도 검증.
- search는 URL 후보 확보가 1차 성공, 본문은 downstream 별도. structured/numeric은 schema 수집이 성공.

## Security
본문 전문은 보고서에 미포함(아티팩트 카운트/상태만). API 키/토큰 값 없음.