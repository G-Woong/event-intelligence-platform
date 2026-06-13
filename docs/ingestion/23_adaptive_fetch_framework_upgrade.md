# 23. Adaptive Fetch Framework 업그레이드

작성일: 2026-06-03

## 추가된 규칙

| 규칙 | 구현 위치 | 설명 |
|---|---|---|
| EXTRACTION_EMPTY→playwright jump | strategy_selection.py | httpx에서 빈 DOM → playwright_basic으로 직행 |
| RATE_LIMITED→no advance | strategy_selection.py | 429 시 전략 advance 금지, cooldown 후 동일 전략 재시도 |
| RATE_LIMITED cooldown | strategy_runner.py | load_rate_limit_policy()의 cooldown 적용 후 재시도 |
| Selenium fallback | strategy_selection.py | 모든 playwright 실패 후 selenium_env_status().ready=True 시 선택 |

## rate_limit_policy

- 파일: `ingestion/configs/rate_limit_policy.yaml`
- default: cooldown 60s, max_retries 1
- gdelt: cooldown 300s, min_interval 5s, cache_ttl 900s

## 기존 규칙 (유지)

| 규칙 | 위치 |
|---|---|
| RSS/feed → playwright 제외 | strategy_selection.py `_is_rss_or_feed` |
| BLOCKED_ERRORS → 즉시 중단 | strategy_selection.py |
| 공식 API 우선 라우팅 | collection_probe.py |
| dotted path count | api_probe.py `_count_items` |
| XML ElementTree count | api_probe.py (RSS: item/entry 카운트) |

## Selenium 상태

- 이 머신: chromedriver 부재 → NOT_READY
- `SeleniumRenderStrategy.fetch()`: NOT_READY 시 크래시 없이 SeleniumFetchResult(status="NOT_READY") 반환
- graph.py dispatch: selenium_rendered_dom 전략 분기 추가
