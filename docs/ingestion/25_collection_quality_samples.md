# 25. 수집 품질 샘플

작성일: 2026-06-03

## 품질 등급 기준

| 등급 | 기준 |
|---|---|
| GOOD | items ≥ 3, meaningful_fields 모두 추출 |
| USABLE | items ≥ 1, 부분 필드 추출 |
| PARTIAL | HTTP 200이지만 items=0 |
| BAD | HTTP 오류 또는 파싱 실패 |

## 소스별 품질 평가

| 소스 | 등급 | items | 비고 |
|---|---|---|---|
| naver_news_search | GOOD | 2,339,934 | 검색 결과 풍부 |
| naver_blog_search | GOOD | 19,209,021 | |
| youtube | GOOD | 3 | snippet+pageInfo 추출 |
| opendart | GOOD | 6,267 | 공시 목록 정상 |
| sec_edgar | GOOD | 100 | hits.hits 정상 |
| eia | GOOD | 14 | routes 추출 |
| hacker_news | GOOD | 500 | |
| serper | GOOD | 3 | organic 추출 |
| tavily | GOOD | 3 | results 추출 |
| dcinside | GOOD | 3 (Playwright) | 제목+URL 추출 |
| signal_bz | GOOD | 5 (Playwright) | rank-tex 선택자 |
| eu_press_corner | USABLE | 1 (Playwright) | ecl-content-item |
| bok_ecos | GOOD | 5 | StatisticTableList.row |
| culture_info | USABLE | 2 | XML 공연 목록 |
| twelve_data | GOOD | 3 | values 추출 |
| yna | GOOD | 120 | RSS news.xml |
| gdelt | PARTIAL | 0 | 429 rate limited |
| fmkorea | BAD | 0 | Cloudflare BLOCKED |
| krx_kind | BAD | 0 | 서버 오류 |

## Playwright 원시 신호 샘플

signal_bz raw_signal 경로: `ingestion/outputs/raw_signal/signal_bz/`
