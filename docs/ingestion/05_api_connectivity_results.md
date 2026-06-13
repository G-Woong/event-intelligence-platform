# API Connectivity Results

> **Dry-run expanded source coverage report** (Round 1.5, 2026-06-03).
> Live HTTP 호출 없음. Key presence dry-run 기준.
> 실제 API 응답 기반 status는 `--live` 실행 후 갱신 예정 (Round 2).

## 실행 명령

```
python -m ingestion.runners.run_api_connectivity_check --dry-run
```

## 요약

| 구분 | 수 |
|---|---|
| 전체 소스 (Phase 1-3 + Phase 4 후보) | ~57개 |
| Phase 1-3 구현 소스 | 31개 |
| Phase 4 확장 후보 | 26개 |
| NO_KEY_REQUIRED (공개 엔드포인트) | ~20개 |
| KEY_PRESENT_DRY_RUN | 키 환경 따라 가변 |
| MISSING_KEY | 키 미설정 시 가변 |
| LOGIN_WALL (BLOCKED) | 2개 (X, Blind) |
| PLAYWRIGHT_REQUIRED (DEFERRED) | 2개 (KRX KIND, EU Press Corner) |
| LICENSE_REQUIRED | 1개 (Reuters) |
| EXTERNAL_SIGNAL_SOURCE | 3개 (google_trending_now, signal_bz, loword) |

## Phase 1-3 구현 소스 상태

| source_id | layer | 예상 status |
|---|---|---|
| bbc, ap_news, techcrunch, the_verge, zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera, cnbc | document_discovery | NO_KEY_REQUIRED |
| reddit, hacker_news, dcinside, fmkorea | community_signal | NO_KEY_REQUIRED |
| gdelt, sec_edgar, federal_register | official_evidence | NO_KEY_REQUIRED |
| product_hunt | community_signal | KEY_PRESENT_DRY_RUN or MISSING_KEY |
| youtube | community_signal | KEY_PRESENT_DRY_RUN or MISSING_KEY |
| naver_blog_search, naver_news_search | search_enrichment | KEY_PRESENT_DRY_RUN or MISSING_KEY |
| opendart, bok_ecos, eia | official_evidence | KEY_PRESENT_DRY_RUN or MISSING_KEY |
| x, blind | community_signal | LOGIN_WALL |
| krx_kind, eu_press_corner | official_evidence | PLAYWRIGHT_REQUIRED |
| reuters | news_verification | LICENSE_REQUIRED |

## Phase 4 확장 소스 상태

| source_id | layer | status |
|---|---|---|
| google_programmable_search, serper, tavily, exa, newsapi, gnews, guardian, nyt | search_enrichment | MISSING_KEY |
| google_trending_now, signal_bz, loword | fast_signal | EXTERNAL_SIGNAL_SOURCE |
| finnhub, twelve_data, alpha_vantage, polygon | market_signal | MISSING_KEY |
| coinbase_market, binance_market | market_signal | NO_KEY_REQUIRED |
| kma, tour, its, kofic, tmdb, kopis, aladin, igdb, culture_info | domain_signal | MISSING_KEY |

## 보안 확인

- 본 보고서에 API 키·토큰·Authorization 헤더가 포함되지 않음
- `_run_dry_check` 반환값에 키 원문·토큰 끝4자리 없음 (`test_dry_run_output_contains_no_secrets` PASS)
- JSONL 결과 파일도 동일 보안 조건 적용

## 다음 액션

1. Phase 4 키 발급 후 `--dry-run` 재실행 → KEY_PRESENT_DRY_RUN 확인
2. Round 2에서 `--live` 실행 (사용자 승인 필요)
3. KRX KIND, EU Press Corner Playwright 구현 후 재테스트
