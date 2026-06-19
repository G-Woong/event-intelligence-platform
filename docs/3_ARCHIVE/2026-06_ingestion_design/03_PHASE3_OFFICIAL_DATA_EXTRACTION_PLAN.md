# 03_PHASE3_OFFICIAL_DATA_EXTRACTION_PLAN — 공식 데이터 소스 10개

## 대상 소스

| ID | 이름 | API 우선 | 알려진 차단 |
|---|---|---|---|
| gdelt | GDELT Project | ✓ | 없음 |
| sec_edgar | SEC EDGAR | ✓ | 없음 |
| bok_ecos | 한국은행 ECOS | ✓ | 없음 |
| eia | EIA | ✓ | 없음 |
| worldbank | World Bank | ✓ | 없음 |
| imf | IMF | | 없음 |
| un_news | UN News | | 없음 |
| cboe | CBOE | | 없음 |
| finviz | Finviz | | 없음 |
| reuters_data | Reuters Markets | | 없음 |

## API vs Crawling

API가 있는 소스(gdelt, sec_edgar, bok_ecos, eia, worldbank):
- 이번 Phase에서는 **crawling route** 검증만 수행
- report에 "API 전환 권장" 여부 기록
- 실제 API 연동은 Step E+ 별도 작업

## 특수 처리

- **gdelt**: REST API `/api/v2/doc/doc` — JSON 직접 파싱
- **sec_edgar**: EDGAR full-text search API
- **finviz**: 정적 HTML 기사 목록 — readability 추출 가능

## 목표 필드

`title`, `body`, `published_at` 기본. 소스별로 `filing_type`, `tone`, `actors` 등 추가.

## 다음 라운드 작업

Step E: API 라우팅 결정 + SourceCrawler 구현.
UNKNOWN: gdelt/sec_edgar/bok_ecos API 키 필요 여부 → 사용자 확인 후 진행.
