# 55 — Playwright 범용 전략 감사

## 1. 개요

Playwright는 특정 사이트를 위한 땜질 도구가 아니라, `fetch_strategies` 레이어의 **공식 전략 중 하나**다.
이 문서는 Playwright가 전략으로서 어떻게 편입되어 있는지 코드 근거와 함께 기록한다.

---

## 2. 경로 A vs 경로 B

Playwright 실행 경로는 두 가지가 존재한다.

### 경로 A — `run_playwright_probe` 단독 실행

```
ingestion/runners/run_playwright_probe.py
    → ingestion/probes/playwright_probe.py
    → ingestion/configs/playwright_probe_sites.yaml  (대상 사이트 목록)
```

- YAML에 명시된 사이트를 직접 probe
- 독립 실행형. 스케줄러나 collection pipeline 없이 단독으로 동작
- 주로 디버깅, 수동 점검, rate limit 상태 확인에 사용

### 경로 B — `run_collection_probe` → `CloudBrowserLikeStrategy`

```
ingestion/runners/run_collection_probe.py
    → ingestion/pipeline/collection_probe.py
    → ingestion/fetch_strategies/strategy_runner.py
    → ingestion/fetch_strategies/cloud_browser_like.py (CloudBrowserLikeStrategy)
    → ingestion/tools/playwright_browser_tool.py:open_page()
```

- `source_registry.yaml` 기반으로 모든 source를 순회
- `strategy_runner`가 전략 시퀀스를 관리하고 Playwright를 그 일부로 호출
- 표준 수집 파이프라인의 일환 — 운영 환경에서의 주 경로

---

## 3. Playwright가 전략 레이어임을 보여주는 코드 근거

### 3.1 `strategy_selection.py:8-13` — `_PLAYWRIGHT_STRATEGIES` frozenset

```python
_PLAYWRIGHT_STRATEGIES: frozenset[str] = frozenset({
    "cloud_browser_like",
    "playwright_direct",
    "playwright_stealth",
})
```

Playwright 기반 전략들이 명시적으로 집합으로 선언되어 있다.
이는 "Playwright = 특수 예외"가 아니라 "Playwright = 전략 집합의 구성원"임을 의미한다.

### 3.2 `strategy_runner.py:65-138` — `STRATEGY_SEQUENCE`의 일부

```python
STRATEGY_SEQUENCE = [
    "lightweight_http",         # 1순위: 경량 HTTP
    "rss_feed",                 # 2순위: RSS
    "cloud_browser_like",       # 3순위: Playwright (CloudBrowserLikeStrategy)
]
```

전략 시퀀스 내에 `cloud_browser_like`가 포함되어, HTTP 실패 시 자동으로 Playwright로 전환된다.
`max_strategies_per_url=3` 기본값과 결합하여 최대 3회 전략 전환이 가능하다.

### 3.3 `cloud_browser_like.py` — `CloudBrowserLikeStrategy`

```python
class CloudBrowserLikeStrategy(BaseFetchStrategy):
    strategy_id = "cloud_browser_like"

    async def fetch(self, url: str, **kwargs) -> FetchResult:
        result = await open_page(url, ...)
        # DOM 파싱 → 항목 추출 → ProbeResult 반환
```

`BaseFetchStrategy`를 상속하여 다른 전략(HTTP, RSS)과 동일한 인터페이스를 가진다.
`strategy_runner`는 전략 종류에 관계없이 동일한 방식으로 호출한다.

---

## 4. Playwright 라우팅 방식: frozenset vs YAML 일반화

### 현재 (frozenset 하드코딩)

`collection_probe.py`의 `_PLAYWRIGHT_FIRST_SOURCES`:

```python
_PLAYWRIGHT_FIRST_SOURCES: frozenset[str] = frozenset({
    "fmkorea",
    "dcinside",
    "theqoo",
    # ...
})

def _should_use_playwright_first(source_id: str) -> bool:
    return source_id in _PLAYWRIGHT_FIRST_SOURCES
```

- 사이트가 추가될 때마다 코드를 수정해야 함
- YAML과 코드가 분리되어 관리 포인트 이원화

### 이번 라운드 목표: YAML 기반 일반화

`playwright_probe_sites.yaml` 또는 `source_registry.yaml`에 다음 필드 추가:

```yaml
sources:
  - id: fmkorea
    collection_method: playwright
    deferred: false

  - id: krx_kind
    collection_method: playwright
    deferred: true   # Chrome 없는 환경에서 건너뜀
```

`_is_playwright_required()` 함수로 YAML 기반 판정:

```python
def _is_playwright_required(source_id: str, service_config: dict) -> bool:
    return (
        service_config.get("collection_method") == "playwright"
        and not service_config.get("deferred", False)
    )
```

- `collection_method: playwright` + `deferred: false` → 자동으로 Playwright 라우팅
- `deferred: true` → NOT_READY 반환, 건너뜀
- `_PLAYWRIGHT_FIRST_SOURCES` frozenset은 **legacy fallback**으로 유지 (하위 호환)

---

## 5. Terminal Status 매핑

| Playwright 결과 | `ProbeResult.status` | 추가 필드 |
|----------------|---------------------|-----------|
| 항목 추출 성공 | `LIVE_SUCCESS` | `items_count`, `rendered_dom` |
| HTML >500B but 항목 없음 | `LIVE_PARTIAL` | `rendered_dom`, `reason` |
| HTML 빈 / 네트워크 오류 | `NETWORK_ERROR` | `error_detail` |
| HTTP 429 감지 | `RATE_LIMITED` | `cooldown_seconds`, `next_retry_at` |
| Turnstile / cf-challenge 감지 | `BLOCKED` | `error_category=CAPTCHA_DETECTED` |
| 로그인 필요 페이지 | `BLOCKED` | `error_category=LOGIN_WALL_DETECTED` |
| `deferred: true` 설정 | `DEFERRED` | `reason=deferred_in_config` |
| Chrome binary 없음 | `NOT_READY` | `error_category=BROWSER_NOT_FOUND` |

**BLOCKED 상태는 모두 terminal**: `strategy_runner`가 BLOCKED_ERRORS로 판정하여 나머지 전략 시도 없이 즉시 중단.

---

## 6. 표준 출력 필드 일관성

`CloudBrowserLikeStrategy` 및 `playwright_probe`가 반환하는 `ProbeResult`의 표준 필드:

| 필드 | 타입 | 설명 |
|------|------|------|
| `rendered_dom` | `str \| None` | Playwright가 렌더한 최종 HTML |
| `screenshot` | `bytes \| None` | 스크린샷 바이너리 (있을 경우) |
| `raw_signal` | `dict \| None` | 원시 신호 데이터 (파싱 전) |
| `network_log` | `list[dict] \| None` | **(신규)** XHR/Fetch 요청 로그 |

`network_log` 신규 필드:
- `page.on("request")` / `page.on("response")` 이벤트로 캡처
- KRX 등 XHR 기반 사이트의 실제 API 엔드포인트 식별에 활용
- 기본적으로 `None` (캡처 미활성화), 설정으로 활성화

---

## 7. 감사 결론

| 항목 | 판정 |
|------|------|
| Playwright가 전략 레이어에 편입되어 있는가 | 확인됨 (strategy_runner, STRATEGY_SEQUENCE) |
| frozenset 하드코딩 제거 계획 존재하는가 | 이번 라운드에서 YAML 일반화로 교체 |
| terminal BLOCKED 즉시 중단 동작하는가 | 확인됨 (BLOCKED_ERRORS 목록) |
| RATE_LIMITED cooldown 응답 포맷 표준화 | 이번 라운드에서 완성 |
| network_log 캡처 필드 | 신규 추가 예정 |
