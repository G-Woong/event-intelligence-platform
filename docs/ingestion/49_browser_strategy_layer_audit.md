# docs/49 — Browser Strategy Layer Audit

**Date**: 2026-06-08  
**Scope**: Playwright / Selenium 브라우저 전략 구조 코드 감사

---

## 1. 구조 개요

두 개의 독립된 경로가 존재한다.

### 경로 A — Standalone Playwright probe (단독 경로)
```
run_playwright_probe runner
  → playwright_probe.run_playwright_probe()
      → playwright_probe_sites.yaml spec 로드
      → 사이트별 YAML 셀렉터 기반 범용 루프
      → 결과: raw_signal JSON + screenshot + rendered_dom
```
- 파일: `ingestion/probes/playwright_probe.py`
- 라우팅: YAML의 `site_id`로 직접 지정. 하드코딩 없음.
- fallback: 없음. 단독 경로.

### 경로 B — Adaptive fetch strategy (폴백 루프)
```
run_collection_probe / agent 호출
  → collection_probe.run_collection_probe()
      → Route 1: _PROBE_SPEC에 있으면 run_api_live_probe
      → Route 2: _PLAYWRIGHT_FIRST_SOURCES 또는 _is_playwright_required
            → CloudBrowserLikeStrategy (httpx→playwright→selenium 폴백)
      → Route 3: fallback strategy loop (base_url 기반)
```
- 파일: `ingestion/fetch_strategies/collection_probe.py`
- 라우팅: `_PLAYWRIGHT_FIRST_SOURCES` frozenset (하드코딩)

---

## 2. 라우팅 하드코딩 현황

### `collection_probe.py:18-21` — `_PLAYWRIGHT_FIRST_SOURCES`

```python
_PLAYWRIGHT_FIRST_SOURCES = frozenset({
    "krx_kind", "eu_press_corner", "signal_bz", "loword",
    "google_trending_now", "dcinside", "fmkorea",
})
```

**문제**: 사이트 추가 시 코드 수정 필요. YAML spec과 불일치 가능성.

**권고**: `playwright_probe_sites.yaml`에 `playwright_required: true` 또는 status_override 기반 범용 라우팅으로 전환. 예:
```python
# collection_probe.py (권고)
def _is_playwright_required(source_id: str) -> bool:
    spec = _load_playwright_spec(source_id)
    return spec is not None and not spec.deferred
```

이렇게 하면 agent가 `run_collection_probe("eu_press_corner")` 호출 시 자동으로 Playwright 경로로 진입.

---

## 3. Selector 범용성 (경로 A)

`playwright_probe.py:202-225` (`_extract_list_items`):
- CSS selector는 **YAML spec 기반 범용 루프** — 하드코딩 없음.
- 각 site의 `selectors.list[]` 배열을 순서대로 시도, 첫 번째 결과 반환.
- 비앵커 셀렉터 (`.ecl-content-item` 등) 매칭 시 `href` 비어 있음 → SELECTOR_MATCHED_BUT_URL_EMPTY 조건.
- `urljoin(base_url, href)` 로 상대경로 자동 resolve.

---

## 4. 이원화 정리

| 항목 | 경로 A (playwright_probe) | 경로 B (collection_probe) |
|---|---|---|
| 진입점 | `run_playwright_probe` runner | `run_collection_probe()` |
| 셀렉터 | YAML spec 범용 루프 | CloudBrowserLikeStrategy (별도 구현) |
| fallback | 없음 | httpx → playwright → selenium |
| 라우팅 | YAML site_id | `_PLAYWRIGHT_FIRST_SOURCES` 하드코딩 |
| 아티팩트 | screenshot, rendered_dom, raw_signal | ExtractionBundle |
| agent 진입 | `run_collection_probe` 호출로 경로 B 진입 | ✓ — `_PLAYWRIGHT_FIRST_SOURCES`에 있으면 Playwright |

**agent가 `run_collection_probe("eu_press_corner")` 호출 시**:
→ `eu_press_corner`가 `_PLAYWRIGHT_FIRST_SOURCES`에 있으므로 Route 2 (CloudBrowserLikeStrategy) 진입.
→ `playwright_probe_sites.yaml` spec을 참조하지 않음 — 경로 A와 독립적으로 동작.

---

## 5. Selenium 역할 확인

`ingestion/fetch_strategies/selenium_strategy.py`:
- **구현됨**: `SeleniumStrategy.fetch()` 완전 구현.
- **NOT_READY 게이트**: `chromedriver` 부재 시 `DEFERRED` 반환.
- **역할**: 경로 B의 최종 폴백 (httpx → playwright → **selenium**).
- **live 상태**: NOT_READY (chromedriver 미설치).
- **권고**: chromedriver 설치 또는 WebDriver Manager 연동 후 활성화. 현재는 DEFERRED 유지 적절.

---

## 6. BLOCKED 감지 (공통)

`error_taxonomy.classify_content_blocker()`:
- Cloudflare challenge, hCaptcha, login wall, paywall 패턴 감지.
- 경로 A/B 모두 참조 가능 (playwright_probe.py에서 직접 호출 가능).
- fmkorea Turnstile: `"just a moment..."` 패턴 → `CAPTCHA_DETECTED`.

---

## 7. 권고 사항

### 단기 (이번 라운드에서 적용 가능)
- `_PLAYWRIGHT_FIRST_SOURCES` 대신 `playwright_probe_sites.yaml`의 `deferred: false` 여부로 동적 라우팅 (구현 비용 낮음).

### 중기 (다음 라운드)
- 경로 A/B 통합 또는 명확한 역할 분리 문서화.
- Selenium chromedriver 환경 구성 (Windows: `webdriver-manager` 패키지).
- `playwright_probe_sites.yaml`에 `playwright_required: true/false` 필드 추가.
