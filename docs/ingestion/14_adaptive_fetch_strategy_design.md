# 14 — Adaptive Fetch Strategy Design

## 목적

단일 소스에서 데이터 수집 실패 시, 원인을 분류하고 다음 전략으로 자동 전환하는 통합 진입점(facade)을 제공한다. 기존 자산을 재사용하며 부족한 "접착제"(단일 분류기, 소스별 전략 선택, 통합 결과 모델)만 추가한다.

## 기존 자산 재사용 맵

| 기능 | 기존 자산 | 위치 |
|---|---|---|
| 전략 사다리 (10단계) | `STRATEGY_SEQUENCE`, `RetryPolicy` | `ingestion/core/retry_policy.py` |
| 오류 분류 (24종) | `ErrorType`, `classify_http_error`, `classify_content_blocker` | `ingestion/core/error_taxonomy.py` |
| HTTP 페칭 | `fetch_html` (httpx) | `ingestion/tools/html_fetch_tool.py` |
| Playwright 렌더링 | `fetch_with_playwright_sync`, `open_page` | `ingestion/tools/playwright_browser_tool.py` |
| 전략 전환 dispatch | `_fetch_with_strategy` | `ingestion/agents/graph.py` |
| artifact 저장 | `save_raw_html`, `save_rendered_dom`, `save_raw_signal` 등 | `ingestion/core/artifact_store.py` |
| API probe | `run_api_live_probe`, `_PROBE_SPEC` | `ingestion/probes/api_probe.py` |
| Playwright probe | `run_playwright_probe` | `ingestion/probes/playwright_probe.py` |

## 신규 추가된 "접착제" 레이어

패키지: `ingestion/fetch_strategies/`

```
fetch_strategies/
├── __init__.py            ← 5개 계약 함수 re-export
├── models.py              ← 집계 dataclass (CollectionProbeResult, StrategyLoopResult 등)
├── failure_classifier.py  ← classify_failure(any) → ErrorType  [단일 진입 분류기]
├── strategy_selection.py  ← select_next_strategy(source, attempts, error) → Optional[str]
├── strategy_runner.py     ← run_fetch_strategy_loop(source_id, url) → StrategyLoopResult
├── cloud_browser_like.py  ← CloudBrowserLikeStrategy.fetch() → RenderedPageFetchResult
├── collection_probe.py    ← run_collection_probe(source_id) → CollectionProbeResult [최상위]
├── artifact_writer.py     ← write_collection_artifacts(result) → ArtifactPaths
└── selenium_strategy.py   ← SeleniumRenderStrategy (scaffold only)
```

## 전략 전환 흐름

```
run_collection_probe(source_id)
    │
    ├─ API spec 존재? → run_api_live_probe()
    │       └─ ProbeResult → CollectionProbeResult
    │
    ├─ Playwright-first 소스? → CloudBrowserLikeStrategy.fetch()
    │       └─ RenderedPageFetchResult → CollectionProbeResult
    │
    └─ fallback → run_fetch_strategy_loop(url)
            │
            ├─ strategy: httpx_direct
            │   └─ 실패? → classify_failure() → ErrorType
            │              └─ BLOCKED? → stop
            │              └─ select_next_strategy() → next_strategy
            ├─ strategy: httpx_mobile_ua
            ├─ strategy: httpx_random_ua
            ├─ strategy: readability / trafilatura / dom_heuristic
            ├─ strategy: playwright_basic
            ├─ strategy: playwright_scroll
            ├─ strategy: playwright_wait_network_idle
            └─ strategy: playwright_click_more (max budget 소진)
                    └─ StrategyLoopResult{status: exhausted}
```

## classify_failure — 단일 진입 분류기

기존에는 `FetchResult`, `ProbeResult`, `Exception`이 각각 다른 경로로 오류를 분류했다. `classify_failure()`는 이를 단일 `ErrorType`으로 통합:

```python
classify_failure(FetchResult(success=False, status_code=403))  → ErrorType.HTTP_4XX
classify_failure(ProbeResult(status="BLOCKED"))                 → ErrorType.LOGIN_WALL_DETECTED
classify_failure(TimeoutError("timeout"))                       → ErrorType.NETWORK_TIMEOUT
classify_failure(ErrorType.CAPTCHA_DETECTED)                    → ErrorType.CAPTCHA_DETECTED  # passthrough
```

## select_next_strategy — 소스 인지 전략 선택

기존 `STRATEGY_SEQUENCE`(평면 리스트)를 소스 특성에 맞게 제한:
- RSS/Feed/XML 소스: playwright 전략 제외 (JS 불필요)
- BLOCKED_ERRORS: 즉시 `None` 반환 (재시도 금지)
- `max_strategies_per_url` 예산 소진: `None` 반환

## RenderedPageFetchResult 표준 필드

| 필드 | 의미 | 타입 |
|---|---|---|
| `url` | 대상 URL | str |
| `strategy_used` | 사용된 전략 | str |
| `html` | 렌더된 HTML 원본 | Optional[str] |
| `markdown` | trafilatura markdown 추출 결과 | Optional[str] |
| `screenshot_path` | 스크린샷 파일 경로 | Optional[str] |
| `rendered_dom_path` | 렌더된 DOM 저장 경로 | Optional[str] |
| `extracted_text` | 추출된 텍스트 (=markdown) | Optional[str] |
| `status` | PROBE_STATUS 값 | str |
| `error_category` | ErrorType | Optional[ErrorType] |
| `timing` | 총 소요 시간(초) | float |
