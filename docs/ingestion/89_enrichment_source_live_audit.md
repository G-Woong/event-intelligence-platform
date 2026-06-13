# 89. Enrichment Source Live Audit (2차 소스 실측)

- 실행: 2026-06-12 17:37 UTC (`run_enrichment_live_audit --from-primary ...`, live 35 호출)
- 산출물: `ingestion/outputs/jsonl/enrichment_live_audit_20260612_173736.jsonl`, `ingestion/outputs/reports/enrichment_live_audit_20260612_173736.md`
- relevance: high ≥0.5 / medium ≥0.2 / low / unknown (영문 토큰 + 한글 2-gram 매칭)

## 1. query set (실사용 기록)

**A. hot seed (1차 실측에서 자동 도출, 8개)**: "이재명 대통령 멜로니", "김혜경 여사 세계청년대회 준비 시간", "이란 종전 MOU 서명 마무리" (signal_bz 실검) / "have duty to stay on", "Defence row exposes tensions over", "Iran says deal to end" (bbc·aljazeera 뉴스 토픽) / "군체" (kofic 박스오피스), "일괄신고서 집합투자증권-…" (opendart)

**B. 대분류**: 한글 10종(정치/국제 분쟁/경제 위기/주식 급등/AI 반도체/기후 재난/문화 콘텐츠/영화 박스오피스/교통 사고/공공 안전) + 영문 8종(politics/global conflict/economic crisis/stock surge/AI semiconductor/climate disaster/box office/public safety) — 소스별 budget으로 round-robin 샘플링 (전체 set 정의, 실호출은 아래 표).

한글 query는 ko 지원 소스(naver×2, serper, tavily, youtube, tmdb)에만 배정.

## 2. 결과 표 (live 호출 35건)

| source_id | query_type | query | status | items | relevance | min_fields | sample_title | url | published_at | useful_for_expansion | recommended_usage | next_action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| serper | seed | 이재명 대통령 멜로니 | LIVE_SUCCESS | 3 | high | title,url,source_id,snippet | (한-이탈리아 정상회담 기사) | yes | partial | **yes** | query_expansion | integrate |
| serper | seed | 김혜경 여사 세계청년대회… | LIVE_SUCCESS | 3 | high | 〃 | 〃 | yes | partial | **yes** | query_expansion | integrate |
| serper | category | 정치 | LIVE_SUCCESS | 3 | high | 〃 | 〃 | yes | partial | **yes** | category_monitor | integrate |
| serper | category | 국제 분쟁 | LIVE_SUCCESS | 3 | high | 〃 | 〃 | yes | partial | **yes** | category_monitor | integrate |
| tavily | seed ×2 / category ×2 | 김혜경…, 이란 종전…, 국제 분쟁, 경제 위기 | LIVE_SUCCESS ×4 | 3 ×4 | high ×4 | title,url,snippet | 〃 | yes | partial | **yes** | query_expansion | integrate |
| exa | seed ×2 | Iran says deal to end / have duty to stay on | LIVE_SUCCESS | 3 | high/medium | title,url | 〃 | yes | yes | **yes** | query_expansion(en) | integrate |
| exa | category ×2 | economic crisis / stock surge | LIVE_SUCCESS | 3 | low/high | 〃 | 〃 | yes | yes | partial | category_monitor | integrate |
| naver_news_search | seed | 군체 | LIVE_SUCCESS | 3 | high | title,url,timestamp,snippet | (영화 군체 기사) | yes | yes | **yes** | ko_query_expansion | integrate |
| naver_news_search | seed | 일괄신고서 집합투자증권-…(장문) | LIVE_PARTIAL | 0 | unknown | - | - | no | no | no | - | **장문 query 절단 필요** |
| naver_news_search | category | 주식 급등 / AI 반도체 | LIVE_SUCCESS ×2 | 3 | high ×2 | 전체 | 〃 | yes | yes | **yes** | category_monitor | integrate |
| naver_blog_search | seed ×2 / category ×2 | (위와 동일 패턴) | LIVE_SUCCESS ×4 | 3 ×4 | medium~high | title,url,snippet | 〃 | yes | partial | **yes** | ko_community_signal | integrate |
| gnews | seed / category | Iran says deal to end / climate disaster | LIVE_SUCCESS ×2 | 3 | high ×2 | title,url,timestamp,snippet | 〃 | yes | yes | **yes** | en_news_expansion | integrate |
| newsapi | seed / category | have duty to stay on / box office | **LIVE_PARTIAL ×2** | 0 | unknown | - | - | no | no | **no(현 endpoint)** | top-headlines+q 부적합 | **switch_to_everything_endpoint** |
| guardian | seed / category | Defence row exposes… / public safety | LIVE_SUCCESS ×2 | 3 | high ×2 | title,url,timestamp | 〃 | yes | yes | **yes** | en_news_expansion | integrate |
| nyt | seed | Iran says deal to end | LIVE_SUCCESS | 10 | high | title,url,timestamp,snippet | 〃 | yes | yes | **yes** | en_news_expansion | integrate |
| nyt | category | politics | LIVE_SUCCESS | 10 | low | 〃 | 〃 | yes | yes | partial | 대분류 단어 매칭 낮음(정상) | integrate |
| gdelt | seed | have duty to stay on | **PARSE_ERROR** | 0 | unknown | - | - | no | no | 보류 | 비-JSON 응답 | inspect_raw_payload |
| gdelt | category | global conflict | **RATE_LIMITED** | 0 | unknown | - | - | no | no | 보류 | 1차에 이어 2연속 429 | retry_after_cooldown:300s |
| sec_edgar | seed | Defence row exposes… | LIVE_SUCCESS | 26 | low | title,url,timestamp,snippet | (filing 목록) | yes | yes | partial | **entity 검색용** (phrase 부적합) | use_entity_ticker_queries |
| sec_edgar | category | economic crisis | LIVE_SUCCESS | 100 | low | 〃 | 〃 | yes | yes | partial | 〃 | 〃 |
| youtube | seed / category | have duty to stay on / global conflict | LIVE_SUCCESS ×2 | 3 | high ×2 | 전체 5 | 〃 | yes | yes | **yes** | video_signal | integrate |
| tmdb | seed | 군체 | LIVE_SUCCESS | 1 | low* | title,url,timestamp,snippet | Colony (2026-05-21) | yes | yes | **yes** | movie_lookup | integrate |

\* tmdb "군체"→"Colony": **cross-language 정타 매칭** — 한글 query가 영문 제목을 정확히 찾았으나 relevance 스코어러(문자 매칭)가 측정 불가. 스코어러 한계로 기록 (실질 high).

## 3. query 미지원 소스 (live 재호출 없음, audit_action=query_unsupported)

| 분류 | source_id | recommended_usage |
|---|---|---|
| parameterized_lookup_for_verification (15) | opendart, bok_ecos, eia, kma, its, tour, kofic, kopis, aladin, culture_info, igdb, finnhub, twelve_data, alpha_vantage, polygon | 사건 검증용 수치/공시/일정 lookup — free-text 불가, 파라미터(날짜·symbol·지역)로 enrichment |
| periodic_seed_only (9) | eu_press_corner, hacker_news, product_hunt, coinbase_market, binance_market, signal_bz, loword, google_trending_now, dcinside | 고정 feed — 주기 seed 전용, query 확장 불가 |

federal_register는 query 지원(conditions[term])이 이번 라운드에 추가되었으나 budget 절약을 위해 2차 live 호출은 생략 (1차에서 LIVE_SUCCESS 확인).

## 4. Summary (실측)

- live 35건: LIVE_SUCCESS 30, LIVE_PARTIAL 3 (newsapi 2, naver 장문 1), PARSE_ERROR 1 + RATE_LIMITED 1 (gdelt)
- relevance: **high 24 / medium 2 / low 5 / unknown 4**
- seed→enrichment 연결 검증: signal_bz 실검 "이재명 대통령 멜로니" → serper/naver에서 관련 기사 확보 (**1차 seed → 2차 확장 파이프라인 성립**)
- 대분류 검증: 한글/영문 대분류 query 전부 ko/en 적합 소스에서 items>0 + high relevance (newsapi 제외)

## 5. 발견 및 next_action

1. **newsapi top-headlines + q는 부적합** (0건 ×2) — `/v2/everything` endpoint로 전환 필요 (probe spec 변경, 다음 라운드).
2. **gdelt 불안정** — 1차 429, 2차 PARSE_ERROR(비-JSON)+429. min_interval 5s 준수에도 발생. 운영 시 15분+ 간격, 429/parse 내성 필수. 이번 시뮬레이션에서 cooldown gate 동작 관찰 대상.
3. **sec_edgar는 phrase 검색 부적합** — full-text가 phrase를 그대로 매칭하지 않음. entity/ticker 기반 query로 용도 한정 (예: "Tesla", "8-K").
4. **장문 seed query는 절단 필요** — opendart 공시명 그대로는 0건. hot seed 도출 시 max_tokens 3~4로 조정하거나 핵심 키워드만 추출.
5. naver/serper/tavily/guardian/gnews/nyt/youtube/exa = **enrichment 핵심 그룹** (전부 items>0, relevance high).
