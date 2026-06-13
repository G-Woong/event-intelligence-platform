# 18 — Agent Orchestration Collection Contract

> doc 12 (`12_agent_orchestration_probe_interface.md`) 확장.  
> 5개 계약 함수의 입출력 명세. Agent가 `from ingestion.fetch_strategies import *` 로 사용.

---

## 패키지 진입점

```python
from ingestion.fetch_strategies import (
    run_collection_probe,       # 최상위 Agent 진입점
    run_fetch_strategy_loop,    # 전략 순환 루프
    classify_failure,           # 단일 오류 분류기
    select_next_strategy,       # 소스 인지 전략 선택
    write_collection_artifacts, # artifact 1회 영속화
)
```

---

## 1. `run_collection_probe`

```python
def run_collection_probe(
    source_id: str,
    query: Optional[str] = None,
    max_items: int = 5,
) -> CollectionProbeResult:
```

**목적**: Agent 최상위 진입점. source_id에 따라 API probe / Playwright / strategy loop 중 하나로 자동 라우팅.

**라우팅 우선순위**:
1. `_PROBE_SPEC`에 등록된 소스 → `run_api_live_probe`
2. `_PLAYWRIGHT_FIRST_SOURCES` 또는 `status_override=PLAYWRIGHT_REQUIRED` → `CloudBrowserLikeStrategy.fetch`
3. 그 외 → `run_fetch_strategy_loop`

**반환**: `CollectionProbeResult`
```
.source_id       str           소스 ID
.status          str           PROBE_STATUS 값 (LIVE_SUCCESS / BLOCKED / MISSING_KEY 등)
.strategy_used   str           사용된 전략 (예: "api", "playwright_basic")
.items_found     int           발견된 항목 수
.probe_result    ProbeResult?  API probe 결과 (API 라우팅 시)
.extraction      ExtractionBundle?  추출 번들 (Playwright 라우팅 시)
.artifact_paths  ArtifactPaths  저장된 파일 경로
.error_category  str?          오류 분류 (실패 시)
.next_action     str           권장 다음 조치
.attempts        list[FetchAttempt]  strategy loop 시도 기록
```

**사용 예**:
```python
result = run_collection_probe("federal_register")
assert result.status == "LIVE_SUCCESS"
assert result.items_found >= 1

result = run_collection_probe("x")
assert result.status == "BLOCKED"  # login_required
```

---

## 2. `run_fetch_strategy_loop`

```python
def run_fetch_strategy_loop(
    source_id: str,
    url: str,
    source_spec: Optional[dict] = None,
    strategy_budget: Optional[int] = None,
) -> StrategyLoopResult:
```

**목적**: STRATEGY_SEQUENCE(10단계)를 순회하며 HTTP/Playwright 페칭. 각 실패마다 `classify_failure` → `select_next_strategy` → backoff.

**동작**:
- `strategy_budget`으로 최대 전략 수 제한 (기본: `RetryPolicy.max_strategies_per_url=3`)
- BLOCKED_ERRORS(CAPTCHA/LOGIN/PAYWALL/ROBOTS) 감지 즉시 중단
- 성공 시 첫 번째 성공 HTML 반환

**반환**: `StrategyLoopResult`
```
.source_id       str
.url             str
.status          "success" | "exhausted" | "blocked"
.attempts        list[FetchAttempt]   각 전략 시도 기록
.final_html      Optional[str]        성공 시 HTML
.final_error_type Optional[ErrorType] 마지막 오류 타입
```

---

## 3. `classify_failure`

```python
def classify_failure(
    result_or_exception: Union[FetchResult, ProbeResult, Exception, ErrorType]
) -> ErrorType:
```

**목적**: 어떤 형태의 실패도 단일 `ErrorType`으로 통합. 기존 `classify_http_error`와 `classify_content_blocker`에 위임.

**입력 → 출력 예**:
```
FetchResult(success=False, status_code=403)  → ErrorType.HTTP_4XX
ProbeResult(status="BLOCKED")                → ErrorType.LOGIN_WALL_DETECTED
TimeoutError("timeout")                      → ErrorType.NETWORK_TIMEOUT
ErrorType.CAPTCHA_DETECTED                   → ErrorType.CAPTCHA_DETECTED  # passthrough
```

---

## 4. `select_next_strategy`

```python
def select_next_strategy(
    source_spec: dict,
    previous_attempts: list[FetchAttempt],
    failure_category: ErrorType,
    policy: Optional[RetryPolicy] = None,
) -> Optional[str]:
```

**목적**: `RetryPolicy.next_strategy` 기반 + 소스 특성 반영.

**반환 None 조건** (중단 신호):
- `failure_category in BLOCKED_ERRORS`
- `len(previous_attempts) >= policy.max_strategies_per_url`
- STRATEGY_SEQUENCE 소진

**소스 특성**:
- RSS/Feed/XML 소스(`response_format=="xml"` 또는 URL에 `rss`/`feed` 포함) → playwright 전략 건너뜀

---

## 5. `write_collection_artifacts`

```python
def write_collection_artifacts(result: CollectionProbeResult) -> ArtifactPaths:
```

**목적**: `CollectionProbeResult` 안의 html/markdown/screenshot/signal을 기존 `artifact_store.save_*` 함수로 1회 영속화. 중복 저장 방지.

**반환**: `ArtifactPaths`
```
.raw_html        Optional[str]  ingestion/outputs/raw_html/{source_id}/...html
.raw_payload     Optional[str]  ingestion/outputs/raw_payload/{source_id}/...json
.extracted_payload Optional[str]  ingestion/outputs/extracted_payload/{source_id}/...json
.screenshot      Optional[str]  ingestion/outputs/screenshots/{source_id}/...png
.rendered_dom    Optional[str]  ingestion/outputs/rendered_dom/{source_id}/...html
.raw_signal      Optional[str]  ingestion/outputs/raw_signal/{source_id}/...json
```

---

## 보안 제약 (모든 함수 공통)

- API 키 / Authorization 헤더 값을 로그·artifact에 출력 금지
- `classify_failure` 결과가 CAPTCHA_DETECTED / LOGIN_WALL_DETECTED / PAYWALL_DETECTED / ROBOTS_BLOCKED인 경우 반드시 중단 — 우회 코드 추가 금지
- honest UA `event-intelligence/0.7 (+ei)` — httpx 요청에만 적용
- Playwright rate limit: 요청 간 최소 2초

---

## 관련 문서

- doc 12: `12_agent_orchestration_probe_interface.md` — 이전 인터페이스 설계
- doc 14: `14_adaptive_fetch_strategy_design.md` — 전략 전환 흐름 상세
- `ingestion/fetch_strategies/__init__.py` — 실제 re-export 코드
