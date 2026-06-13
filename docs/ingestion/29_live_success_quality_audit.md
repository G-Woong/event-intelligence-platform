# 29 — LIVE_SUCCESS Quality Audit

**감사 기준**: raw_payload / raw_signal artifact에서 sample_title, payload_fields, 데이터 밀도 확인.  
**등급**: GOOD (실제 콘텐츠 충분) / USABLE (최소한의 유효 데이터) / PARTIAL (구조는 있으나 내용 빈약) / BAD (차단/광고/빈 DOM)

---

## GOOD 등급 (충분한 실 데이터)

| source_id | artifact_size | payload_fields 확인 | 비고 |
|---|---|---|---|
| bbc | 25KB XML | channel/item/title/link/pubDate | 뉴스 피드 정상 |
| ap_news | 2.7MB XML | channel/item/title/description/link | 대형 RSS, 100+ 기사 |
| techcrunch | 19KB XML | channel/item/title/link/pubDate | RSS 정상 |
| the_verge | 34KB XML | channel/item/title/link/pubDate | RSS 정상 |
| zdnet_korea | 115KB HTML | title/article 구조 | httpx 수집 정상 |
| etnews | 82KB HTML | 기사 목록 HTML | httpx 수집 정상 |
| yna | 91KB XML | 뉴스 RSS | 정상 |
| hankyung | 17KB XML | RSS 표준 | 정상 |
| maekyung | 39KB XML | RSS 표준 | 정상 |
| aljazeera | 17KB XML | RSS 표준 | 정상 |
| cnbc | 21KB XML | RSS 표준 | 정상 |
| reddit | 190KB JSON | data.children[].data.title/url/score/subreddit | 25 items |
| hacker_news | 4.5KB JSON | 상위 스토리 ID 배열 | Firebase JSON 정상 |
| youtube | 4KB JSON | items[].snippet.title/description/publishedAt | 3 비디오 |
| naver_blog_search | 1.9KB JSON | items[].title/description/link/postdate | 3 블로그 |
| opendart | 749B JSON | list[].corp_name/report_nm/rcept_no | 3건 |
| sec_edgar | 59KB JSON | hits.hits[].\_source.file_date/display_names | 10+ 파일링 |
| bok_ecos | 769B JSON | StatisticTableList.row[].STAT_CODE/STAT_NAME | 834개 통계표 |
| eia | 3KB JSON | response.routes[].id/name/description | 25개 에너지 데이터 경로 |
| federal_register | 496B JSON | results[].title/document_number/publication_date | 3건 |
| serper | 1.5KB JSON | organic[].title/link/snippet | 3 검색결과 |
| tavily | 1KB JSON | results[].title/url/content | 3 결과 |
| exa | 1.9KB JSON | results[].title/url/text | 3 결과 |
| newsapi | 2.5KB JSON | articles[].title/url/publishedAt/source | 3건 |
| gnews | 10KB JSON | articles[].title/url/publishedAt/source | 10건 |
| guardian | 6.6KB JSON | response.results[].webTitle/webUrl/sectionName | 10건 |
| nyt | 14.7KB JSON | response.docs[].headline/pub_date/section_name | 10건 |
| google_trending_now | 365B JSON | keyword[] | 10개 실시간 검색어 (한국어, 날짜 기준 유효) |
| signal_bz | 304B JSON | keyword[] | 5개 실시간 순위 (선거 관련, 날짜 기준 유효) |
| twelve_data | 547B JSON | values[].datetime/open/high/low/close | 3일치 시계열 |
| polygon | 267B JSON | results[].T/v/vw/o/c/h/l | AAPL 일봉 1건 |
| coinbase_market | 1.1MB JSON | products[].product_id/price/volume_24h | 1000+ 거래쌍 |
| binance_market | 152KB JSON | [].symbol/price | 전종목 현재가 배열 |
| tmdb | 12KB JSON | results[].title/overview/release_date/popularity | 20건 |
| aladin | 4.1KB JSON | item[].title/author/pubDate/isbn | 베스트셀러 3건 |
| product_hunt | 335B JSON | data.posts.edges[].node.name/tagline | 3건 |

**GOOD 소계: 36**

---

## USABLE 등급 (최소 유효 데이터)

| source_id | artifact_size | 이슈 |
|---|---|---|
| dcinside | 459B JSON (raw_signal) | 3개 갤러리 게시글 제목 + URL. 본문 없음. 충분한 signal. |

**USABLE 소계: 1**

---

## PARTIAL 등급 (연결 성공이나 내용 불완전)

| source_id | artifact_size | 이슈 | 원인 |
|---|---|---|---|
| naver_news_search | 25B JSON | `{"total": 1, "items": []}` — items 빈 배열 | query 파라미터 누락 또는 인코딩 문제 |
| eu_press_corner | 174B JSON | 1건 — 제목 텍스트만, URL 없음 | playwright selector `.ecl-content-item` 1개만 매칭 |
| finnhub | 57B JSON | 모든 필드 0 (c=0, d=null, h=0...) | 유효하지 않은 심볼 파라미터 |
| kofic | 125B JSON | 필수 파라미터(targetDt) 누락 오류 | probe_spec에 targetDt 미포함 |
| kopis | 198B XML | INVALID REQUEST PARAMETER | probe_spec에 날짜 형식 오류 |

**PARTIAL 소계: 5**

---

## BAD 등급 (봇 차단 / 빈 DOM / 에러)

| source_id | artifact_size | 이슈 |
|---|---|---|
| fmkorea | 74KB HTML | 메인 페이지만 로드됨. 스톡 게시판(playwright) → Turnstile BLOCKED |
| x | — | artifact 없음. 로그인 필요 (known_blocker) |
| blind | — | artifact 없음. 로그인 필요 (known_blocker) |
| reuters | — | artifact 없음. 봇 차단 (known_blocker) |
| gdelt | 102B | rate limit 메시지만 (텍스트 오류 응답) |
| alpha_vantage | 65B | "This API function () does not exist." |
| tour | 18B | "Unexpected errors" |
| its | 159B | 잘못된 URL (resultCode=4004) |
| culture_info | 909B | HTML 오류 페이지 (key 미인식 또는 endpoint 오류) |

**BAD 소계: 9**

---

## 요약

| 등급 | 수 |
|---|---|
| GOOD | 36 |
| USABLE | 1 |
| PARTIAL | 5 |
| BAD | 9 |

실제 데이터 수집 가능 (GOOD+USABLE): **37개**  
수정 후 복구 가능 (PARTIAL): **5개**  
MVP 제외 유지 (BAD → BLOCKED/DEFERRED/FAILED): **9개**
