# 01. RISK-T04 — Route 1(API) 429 cooldown 기록 gap 수정

> 우선순위: **최상 (다른 모든 live 재검증의 안전망)**. 의존성: 없음. 예상 변경: `api_probe.py` 1곳 + 신규 테스트 1파일.

## 1. 해석 — 무엇이 왜 문제인가

직전 라운드 시뮬레이션(docs/90 §3)에서 규명된 인프라 결함이다. 429(RATE_LIMITED)를 만났을 때의 보호 동작이 경로별로 비대칭이다:

- **Route 2 (Playwright)**: `ingestion/fetch_strategies/cloud_browser_like.py:70-77`에서 `_detect_429(html)` 감지 시 `record_rate_limited(source_id)`를 호출해 rate limit store에 next_retry 시각을 영속 기록한다. → 이후 `gate_check`의 `in_cooldown`이 cooldown_skip을 반환한다. **정상.**
- **Route 1 (API, `run_api_live_probe`)**: `_http_status_to_probe_status(429) → "RATE_LIMITED"`로 status는 만들지만, ① `record_rate_limited`를 **호출하지 않고** ② 반환 `ProbeResult.next_retry_at`도 **설정하지 않는다**.

결과 두 가지 보호가 모두 무력화된다:
1. `collection_probe._update_health()`(`collection_probe.py:161-180`)는 `probe_result.next_retry_at`을 health store에 넘기는데 이 값이 항상 None → health state는 `RATE_LIMITED_COOLDOWN`이 되지만 `source_health.should_skip()`(`source_health.py:183-185`)은 `next_retry_at`이 비어 있으면 **skip하지 않는다**.
2. rate limit store의 `next_retry` 키도 비어 있어 `in_cooldown()`도 False.

즉 API 소스가 429를 맞아도 다음 주기에 즉시 재호출된다. 직전 라운드에서 gdelt가 살아남은 것은 우연히 `cache_ttl 900s`가 대신 막아줬기 때문이다(docs/90 §2-1). Celery 주기 수집(plans/012)에서는 이 gap이 429 폭주로 직결되므로 **그 전에 반드시 닫는다**.

## 2. 설계 결정과 근거

- **기록 위치**: `run_api_live_probe`의 **최종 ProbeResult 생성 직전** 1곳. 이유: 429는 두 경로로 발생한다 — ① HTTP 429 (`_http_status_to_probe_status`, `api_probe.py:374`) ② alpha_vantage가 200 응답 body의 `"Note"/"Information"` 필드로 알려주는 soft rate limit (`api_probe.py:752-754`). 두 경로 모두 최종 `probe_status` 변수에 수렴하므로, return 직전에 `probe_status == "RATE_LIMITED"` 하나만 검사하면 누락이 없다. 중간(상태 매핑 직후)에 넣으면 ②를 놓친다.
- **query 키 정합**: `record_rate_limited(service_id, query or "")` — `cache_key(source_id, query)` 체계와 동일한 키를 쓴다. query별 cooldown(검색 호출)과 소스 전체 보호(health store의 next_retry_at — query 무관)가 이중으로 동작한다. 1차 seed audit은 query=""이므로 기존 gate와 정확히 맞물린다.
- **`Retry-After` 헤더 존중**: 서버가 명시한 대기 시간이 정책값보다 길면 그 값을 쓴다. 짧으면 정책값(보수적) 유지. 이유: 표준 헤더를 무시하면 cooldown 만료 직후 재호출이 또 429를 맞는다.
- **실패 무해성**: 기록 자체가 실패해도(store 오류 등) probe 결과 반환은 막지 않는다 — try/except + warning. 수집 경로에서 인프라 부가 기능이 본 기능을 죽이면 안 된다(기존 `_update_health`와 같은 원칙).

## 3. 구현 diff

### 3-1. `ingestion/probes/api_probe.py`

**(a)** `run_api_live_probe` 끝부분 — 현재 코드(원본 795~814행):

```python
    if extracted:
        try:
            ep = save_extracted_payload(run_id, service_id, uh, extracted)
            artifact_paths["extracted_payload"] = str(ep)
        except Exception as exc:
            logger.warning("extracted_payload save failed for %s: %s", service_id, exc)

    return ProbeResult(
        source_id=service_id,
        method="api",
        query=query,
        status=probe_status,
        http_status=http_status,
        ...
```

이를 다음으로 교체한다 (`return ProbeResult(` 바로 앞에 블록 삽입 + 인자 1개 추가):

```python
    if extracted:
        try:
            ep = save_extracted_payload(run_id, service_id, uh, extracted)
            artifact_paths["extracted_payload"] = str(ep)
        except Exception as exc:
            logger.warning("extracted_payload save failed for %s: %s", service_id, exc)

    # RISK-T04 (docs/90 §3): Route 1 429 → cooldown 영속 기록.
    # HTTP 429와 alpha_vantage soft limit(Note/Information) 둘 다 여기로 수렴한다.
    # Route 2(cloud_browser_like)와 동일한 record_rate_limited 경로 사용.
    next_retry_at: Optional[str] = None
    if probe_status == "RATE_LIMITED":
        try:
            from ingestion.core.rate_limit_policy import (
                load_rate_limit_policy,
                record_rate_limited,
            )
            cooldown = load_rate_limit_policy(service_id).cooldown_on_429_seconds
            retry_after = response.headers.get("Retry-After", "")
            if retry_after.isdigit():
                cooldown = max(cooldown, int(retry_after))
            next_retry_at = record_rate_limited(
                service_id, query or "", cooldown_seconds=cooldown
            )
            logger.info(
                "RATE_LIMITED recorded for %s — next_retry=%s", service_id, next_retry_at
            )
        except Exception as exc:
            logger.warning("record_rate_limited failed for %s: %s", service_id, exc)

    return ProbeResult(
        source_id=service_id,
        method="api",
        query=query,
        status=probe_status,
        http_status=http_status,
        items_found=items_found,
        items_extracted=items_found,
        meaningful_fields=meaningful_found,
        artifact_paths=artifact_paths,
        next_retry_at=next_retry_at,
        error_category=probe_status if probe_status not in ("LIVE_SUCCESS", "LIVE_PARTIAL") else None,
        next_action=_NEXT_ACTION_MAP.get(probe_status, "investigate"),
    )
```

**주의 3건:**
1. `ProbeResult`에 `next_retry_at` 필드가 이미 있는지 `ingestion/probes/models.py`에서 확인하라. `collection_probe.py:169`가 `result.probe_result.next_retry_at`을 읽으므로 존재할 것이다. 만약 없으면 `next_retry_at: Optional[str] = None` 필드를 모델에 추가하라 (기본값 None — 기존 테스트 비파괴).
2. `response` 변수는 HTTP 호출 성공 경로에서만 존재한다. NETWORK_ERROR/TIMEOUT은 그 전에 early return하므로 위 블록에서 `response`는 항상 정의되어 있다. 단, alpha_vantage soft limit 경로도 HTTP 200 응답을 받은 뒤이므로 동일하게 안전하다.
3. `Retry-After`가 HTTP-date 형식(숫자 아님)이면 `isdigit()`이 False → 정책값 사용. 의도된 단순화다 (date 파싱은 과잉).

### 3-2. (수정 불필요 확인) `collection_probe._update_health`

기존 코드가 `probe_result.next_retry_at`을 이미 health store로 전달하므로 **수정하지 않는다**. 이 diff만으로 `should_skip`의 RATE_LIMITED_COOLDOWN 분기가 살아난다.

## 4. 신규 테스트 — `ingestion/tests/unit/test_route1_rate_limit_record.py`

전부 네트워크 없음. httpx를 monkeypatch한 fake client를 쓴다. 기존 api_probe 테스트 파일(있다면 `ingestion/tests/unit/` 내 `test_api_probe*.py`)의 fake 패턴을 먼저 확인하고 동일 스타일을 따르라.

```python
"""RISK-T04: Route 1 429 → record_rate_limited + next_retry_at (docs/90 §3)."""
import os
os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "memory")

import pytest


class _FakeResponse:
    def __init__(self, status_code=429, text="rate limited", headers=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self._json = json_data

    def json(self):
        if self._json is None:
            raise ValueError("not json")
        return self._json


class _FakeClient:
    def __init__(self, response, **kwargs):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, *a, **k):
        return self._response

    def post(self, *a, **k):
        return self._response


@pytest.fixture(autouse=True)
def _fresh_stores(monkeypatch):
    from ingestion.core import rate_limit_store
    from ingestion.core.rate_limit_policy import _call_cache
    rate_limit_store.reset_store_for_tests()
    _call_cache.clear()
    yield
    rate_limit_store.reset_store_for_tests()


def _patch_httpx(monkeypatch, response):
    import httpx
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: _FakeClient(response, **kw)
    )


def test_http_429_records_cooldown_and_next_retry(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429))
    # gdelt: 키 불필요 public API — MISSING_KEY 분기를 타지 않음
    result = run_api_live_probe("gdelt", max_calls=1)
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at, "next_retry_at must be set on 429"
    cooled, at = in_cooldown("gdelt", "")
    assert cooled and at == result.next_retry_at


def test_429_with_query_records_query_scoped_key(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429))
    result = run_api_live_probe("gdelt", max_calls=1, query="global conflict")
    assert result.status == "RATE_LIMITED"
    assert in_cooldown("gdelt", "global conflict")[0]


def test_retry_after_header_extends_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from datetime import datetime, timezone
    _patch_httpx(monkeypatch, _FakeResponse(status_code=429, headers={"Retry-After": "3600"}))
    result = run_api_live_probe("gdelt", max_calls=1)
    deadline = datetime.fromisoformat(result.next_retry_at.replace("Z", "+00:00"))
    # gdelt 정책 cooldown(300s)보다 길어야 한다
    assert (deadline - datetime.now(timezone.utc)).total_seconds() > 3000


def test_alpha_vantage_soft_limit_records_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    # alpha_vantage는 키 필요 — 가짜 키 주입 (값은 테스트 전용 더미)
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-dummy-key-not-real")
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text='{"Note": "limit"}', json_data={"Note": "limit"}
    ))
    result = run_api_live_probe("alpha_vantage", max_calls=1)
    assert result.status == "RATE_LIMITED"
    assert result.next_retry_at
    assert in_cooldown("alpha_vantage", "")[0]


def test_success_does_not_record_cooldown(monkeypatch):
    from ingestion.probes.api_probe import run_api_live_probe
    from ingestion.core.rate_limit_policy import in_cooldown
    _patch_httpx(monkeypatch, _FakeResponse(
        status_code=200, text='{"articles": []}', json_data={"articles": []}
    ))
    result = run_api_live_probe("gdelt", max_calls=1)
    assert result.status in ("LIVE_SUCCESS", "LIVE_PARTIAL")
    assert result.next_retry_at is None
    assert not in_cooldown("gdelt", "")[0]
```

**작성 시 주의**: ① artifact 저장(`save_raw_payload`)이 실제 파일을 쓴다 — tmp 격리가 필요하면 기존 api_probe 테스트가 쓰는 방식(있다면 동일 fixture)을 재사용하고, 없다면 저장은 무해하므로 그대로 둔다. ② alpha_vantage 테스트의 더미 키는 실키 패턴이 아니어야 한다(`test-dummy-` 접두). secret scan에 걸리지 않는다.

## 5. 검증 절차 (루프 STEP D)

```powershell
# 1) 신규 테스트만
.\.venv\Scripts\python.exe -m pytest ingestion\tests\unit\test_route1_rate_limit_record.py -v
# 2) 전체 회귀 (509 + 신규 5 = 514 통과해야 함)
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q
```

live 검증은 별도로 하지 않는다 — 의도적으로 429를 유발하는 행위는 금지. 02(gdelt) 라운드에서 자연 발생하는 429가 있으면 그것이 live 검증이 된다 (cooldown 기록 여부를 `ingestion/outputs/state/rate_limit_cache.json`의 `next_retry` 키로 확인).

## 6. 종결 기준

- [ ] 신규 테스트 5건 전부 통과
- [ ] 전체 pytest 기준선+5 통과, 실패 0
- [ ] `ProbeResult.next_retry_at` 필드 존재 확인 (또는 추가)
- [ ] 체크리스트 #1 → PASS (증거: pytest 출력 수치)
