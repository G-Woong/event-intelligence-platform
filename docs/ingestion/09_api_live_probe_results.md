# 09 API Live Probe Results

실행일: 2026-06-03  
총 소스: 56 | LIVE_SUCCESS: 30 | LIVE_PARTIAL: 5 | MISSING_KEY: 3 | BLOCKED: 3 | DEFERRED: 5 | Other: 10

---

## P0 개별 실호출 결과

| source_id | status | HTTP | items | artifact | next_action |
|---|---|---|---|---|---|
| hacker_news | LIVE_SUCCESS | 200 | 500 | raw_payload + extracted | integrate_into_pipeline |
| federal_register | LIVE_SUCCESS | 200 | 3 | raw_payload + extracted | integrate_into_pipeline |
| naver_news_search | LIVE_SUCCESS | 200 | 3 | raw_payload + extracted | integrate_into_pipeline |
| naver_blog_search | LIVE_SUCCESS | 200 | 3 | raw_payload + extracted | integrate_into_pipeline |
| youtube | LIVE_SUCCESS | 200 | 3 | raw_payload + extracted | integrate_into_pipeline |
| gdelt | RATE_LIMITED | 429 | 0 | raw_payload | retry_with_backoff |
| sec_edgar | LIVE_PARTIAL | 200 | 0 | raw_payload | nested_hits_field |
| opendart | LIVE_PARTIAL | 200 | 0 | raw_payload | needs_recent_3day_range_or_corp_code |
| eia | LIVE_PARTIAL | 200 | 0 | raw_payload(sanitized) | routes_nested_inside_response |
| product_hunt | LIVE_PARTIAL | 200 | 0 | raw_payload | graphql_nested_data.posts.edges |
| bok_ecos | LIVE_PARTIAL | 200 | 0 | raw_payload | key_in_url_replacement_issue |

---

## --all-safe 전체 스캔 결과

### LIVE_SUCCESS (실데이터 수신)

| source_id | HTTP | items | meaningful_fields |
|---|---|---|---|
| bbc | 200 | 1 | (XML content present) |
| techcrunch | 200 | 1 | (XML content present) |
| the_verge | 200 | 1 | (XML content present) |
| zdnet_korea | 200 | 1 | (HTML content present) |
| etnews | 200 | 1 | (HTML content present) |
| hankyung | 200 | 1 | (XML content present) |
| maekyung | 200 | 1 | (XML content present) |
| aljazeera | 200 | 1 | (XML content present) |
| hacker_news | 200 | 500 | (JSON list) |
| dcinside | 200 | 1 | (HTML content) |
| fmkorea | 200 | 1 | (HTML content) |
| naver_blog_search | 200 | 3 | items, total |
| cnbc | 200 | 1 | (XML content) |
| naver_news_search | 200 | 3 | items, total |
| federal_register | 200 | 3 | results, count |
| youtube | 200 | 3 | items, pageInfo |
| gnews | 200 | 3 | articles |
| guardian | 200 | 1 | results |
| nyt | 200 | 3 | response.docs |
| finnhub | 200 | 8 | (JSON object) |
| alpha_vantage | 200 | 1 | (JSON object) |
| polygon | 200 | 8 | results |
| coinbase_market | 200 | 922 | products |
| binance_market | 200 | 3593 | (JSON array) |
| tmdb | 200 | 4 | results |

### LIVE_PARTIAL (응답 있으나 필드 구조 불일치)

| source_id | 원인 | next_action |
|---|---|---|
| sec_edgar | hits 필드가 중첩됨 (`hits.hits[]`) | update_probe_spec |
| opendart | corp_code 없이 3영업일 이내만 허용 | use_recent_date_range |
| eia | routes 필드가 `response.routes`에 중첩 | update_probe_spec |
| product_hunt | data가 `data.posts.edges`로 중첩 | update_probe_spec_graphql |
| bok_ecos | URL path key 치환 성공, StatisticTableList 중첩 | update_probe_spec |

### MISSING_KEY (키 미설정)

| source_id | 필요 키 |
|---|---|
| google_programmable_search | GOOGLE_CUSTOM_SEARCH_API_KEY + CX |
| kofic | KOBIS_API_KEY |
| culture_info | CULTURE_INFO_API_KEY |

### BLOCKED (정책·라이선스)

| source_id | 이유 |
|---|---|
| x | LOGIN_WALL |
| blind | LOGIN_WALL |
| reuters | LICENSE_REQUIRED |

### DEFERRED (이번 라운드 제외)

| source_id | 이유 |
|---|---|
| krx_kind | PLAYWRIGHT_REQUIRED |
| eu_press_corner | PLAYWRIGHT_REQUIRED |
| google_trending_now | EXTERNAL_SIGNAL_SOURCE (Playwright probe 별도 실행) |
| signal_bz | EXTERNAL_SIGNAL_SOURCE (Playwright probe 별도 실행) |
| loword | EXTERNAL_SIGNAL_SOURCE (Playwright probe 미실행) |

### 기타 이슈 (조치 필요)

| source_id | status | HTTP | 원인 |
|---|---|---|---|
| ap_news | PERMISSION_DENIED | 403 | RSShub 엔드포인트 차단 |
| yna | UNKNOWN | 404 | RSS 엔드포인트 변경됨 |
| gdelt | RATE_LIMITED | 429 | 무료 플랜 속도 제한 |
| reddit | PERMISSION_DENIED | 403 | 공개 .json 엔드포인트 폐지 |
| serper | UNKNOWN | 400 | 요청 body 필요 (POST) |
| tavily | UNKNOWN | 405 | POST body 필요 |
| exa | UNKNOWN | 404 | 엔드포인트 변경 |
| newsapi | UNKNOWN | 400 | 필수 파라미터 누락 |
| twelve_data | UNKNOWN | 404 | 엔드포인트 변경 |
| kma | INVALID_KEY | 401 | 키 등록 필요 |
| tour | NETWORK_ERROR | 500 | 서버 오류 |
| its | INVALID_KEY | 401 | 키 등록 필요 |
| kopis | PARSE_ERROR | 200 | XML 응답 (JSON 파싱 실패) |
| aladin | PARSE_ERROR | 200 | XML 응답 (JSON 파싱 실패) |
| igdb | INVALID_KEY | 401 | Twitch OAuth 클라이언트 검증 필요 |

---

## 보안 메모

- **EIA 응답**: EIA API가 응답 본문에 `request.params.api_key`를 포함해 반환합니다.
  `_sanitize_response()` 함수가 추가되어 이후 실행분에서 자동 제거됩니다.
  기존 `ingestion/outputs/raw_payload/eia/` 파일은 사용자가 직접 삭제 바랍니다.
- 모든 artifact는 응답 본문만 저장. 요청 헤더/URL 쿼리 파라미터 미저장.
