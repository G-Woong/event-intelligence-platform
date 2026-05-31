# 01_PHASE1_NEWS_EXTRACTION_PLAN — 기사형 뉴스 10개

## 대상 소스

| ID | 이름 | 알려진 차단 |
|---|---|---|
| bbc | BBC News | 없음 |
| reuters | Reuters | 없음 |
| apnews | AP News | 없음 |
| bloomberg | Bloomberg | paywall |
| ft | Financial Times | paywall, login_wall |
| wsj | Wall Street Journal | paywall |
| nytimes | New York Times | paywall |
| guardian | The Guardian | 없음 |
| economist | The Economist | paywall |
| aljazeera | Al Jazeera | 없음 |

## 목표 필드

`title`, `body`, `published_at`, `author` (언론사별 가용 여부 상이)

## 전략 순서

1. `httpx_direct` → readability / trafilatura
2. `httpx_mobile_ua` — 모바일 UA로 paywall 우회 시도 (합법적 범위)
3. `playwright_basic` — JS 렌더링 필요 시
4. `playwright_wait_network_idle` — 동적 로딩 기사

paywall 감지 시: `PAYWALL_DETECTED` 기록 후 **즉시 중단**. 우회 시도 없음.

## 품질 기준

- body_length >= 300 (news type)
- title_present = True
- SUCCESS >= 0.70

## Playwright 사용 위치

- bloomberg, nytimes, ft, wsj: JS 렌더링 필요 시 `playwright_basic` 시도
- 모든 playwright 호출: `screenshot_on_failure=True`

## LLM 호출 위치

- `extract_event_candidates`: title + body[:500] → EventCandidate
- `llm_quality_judge`: title + body[:300] → is_valid/confidence/reason

## BLOCKED 예상

bloomberg, ft, wsj, nytimes, economist — paywall 가능성 높음.
운영 범위: 무료 기사 or RSS 전문 링크 한정.

## 다음 라운드 작업

Step C: `sources/bbc.py` ~ `sources/aljazeera.py` 10개 구현
각 SourceCrawler: `build_search_query`, `get_entry_url`, `extract_candidate_urls` 구현.
