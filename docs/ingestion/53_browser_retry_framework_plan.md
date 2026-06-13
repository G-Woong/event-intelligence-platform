# 53 — Browser Strategy & Safe Retry Framework: 계획 문서

## 1. 배경

docs 46-52에서 수행한 Source Stabilization 라운드는 "B mostly closed" 선언으로 마무리되었다.
그러나 실제 구현을 재검토한 결과, 다음과 같은 갭이 식별되었다.

- Playwright 호출 경로가 3곳에 분산되어 있으나 retry/fallback 정책이 통합되지 않음
- Selenium 런타임 readiness 판정이 `chromedriver` PATH 의존으로 과도하게 엄격함
- Google Trends rate limit 흐름이 YAML 정책과 probe 응답 포맷 간에 연결되지 않음
- KRX 실패 원인이 인코딩 문제인지 JS 렌더 문제인지 미확인
- FMKorea Turnstile 감지는 taxonomy에 정의되었으나 strategy_runner 연동 검증 미비
- terminal BLOCKED 상태와 안전 재시도 허용 상태의 경계가 명시적으로 문서화되지 않음

이번 라운드(53)는 위 갭을 닫고, 브라우저 전략 레이어와 안전 재시도 프레임워크를 완성한다.

---

## 2. Playwright 호출 위치

현재 Playwright 실행은 세 곳에서 이루어진다.

| 위치 | 역할 |
|------|------|
| `ingestion/tools/playwright_browser_tool.py:open_page()` | 저수준 페이지 오픈 + DOM 반환 |
| `ingestion/probes/playwright_probe.py:_async_probe()` | 단독 probe 실행 (rate limit, blocker 감지 포함) |
| `ingestion/fetch_strategies/cloud_browser_like.py` | `CloudBrowserLikeStrategy` — fetch_strategies 레이어에서 Playwright를 전략으로 호출 |

세 경로 모두 `error_taxonomy.py`의 분류 결과를 공유해야 하며, 재시도 정책은 `strategy_runner.py`에서 단일하게 통제한다.

---

## 3. Selenium 설치 상태

```
selenium==4.26.1  # pip freeze 확인
```

- **Selenium Manager 내장 (4.x)**: `Service()` 기본 호출 시 chromedriver를 자동 조달
- **chromedriver PATH 불필요**: 별도 설치 또는 환경변수 설정 없이 동작
- **Chrome binary**: Windows 표준 경로(ProgramFiles, LocalAppData) 및 PATH 탐색으로 발견됨
- **이번 세션 탐지 결과**: `chrome_binary_found: True`

readiness 판정 기준 변경:

| 조건 | 이전 (chromedriver 요구) | 이후 (Selenium Manager) |
|------|--------------------------|------------------------|
| chromedriver PATH | 필수 | 불필요 |
| Chrome binary | 필요 | 필요 |
| ready 판정 로직 | `chromedriver AND chrome` | `selenium_installed AND chrome` |

---

## 4. requirements 현황

| 상태 | 내용 |
|------|------|
| 이전 | `requirements.txt` 0바이트 (빈 파일) |
| 이번 라운드 | 런타임 핵심 deps 35+ 패키지 고정 |
| 추가 | `requirements.lock.txt` — 전체 재현용 전체 의존성 트리 고정 |

핵심 변경:
- `selenium==4.26.1` 명시
- `playwright` (버전 고정)
- `aiohttp`, `httpx`, `bs4`, `lxml` 포함
- `pyyaml`, `pydantic`, `python-dotenv` 포함

---

## 5. Google Trends Rate Limit 흐름

`ingestion/configs/rate_limit_policy.yaml` 내 `google_trends_explore` 정책:

```yaml
google_trends_explore:
  min_interval: 1800       # 요청 간 최소 간격 (초)
  cooldown_on_429: 600     # 429 수신 시 쿨다운 (초)
  max_retries: 0           # 429 발생 시 즉시 중단
  cache_ttl: 1800          # 캐시 유효 시간 (초)
```

`playwright_probe.py`에서 429 감지 시 응답 구조:

```python
{
    "status": "RATE_LIMITED",
    "cooldown_seconds": 600,
    "next_retry_at": "<ISO8601 타임스탬프>"  # UTC 기준
}
```

흐름 요약:

```
playwright_probe → 429 HTTP 응답 감지
    → rate_limit_policy.yaml 조회 (cooldown_on_429=600)
    → ProbeResult(status=RATE_LIMITED, cooldown_seconds=600, next_retry_at=...)
    → strategy_runner: RATE_LIMITED는 즉시 중단, 재시도 없음
```

---

## 6. KRX 실패 가설

- 대상: `kind.krx.co.kr`
- 관측된 현상: 응답 크기 ~1.3KB (정상 데이터 대비 매우 작음)
- 가설 1: **EUC-KR 인코딩 오류** — UTF-8로 디코딩 시 오류 페이지 반환
- 가설 2: **JS 테이블 미렌더** — 서버 사이드 HTML 없음, JS 실행 후 데이터 로드
- 가설 3: **서버 측 오류 페이지** (5xx) — HTML 구조 자체가 오류 응답

확인 방법:
- Playwright XHR 캡처 (`page.on("request")` / `page.on("response")`) 로 실제 데이터 XHR 엔드포인트 식별
- 응답 헤더 `Content-Type: charset=EUC-KR` 확인
- 정상 브라우저에서 Network 탭으로 실제 API 엔드포인트 수동 확인

---

## 7. FMKorea Turnstile 감지 위치

```
ingestion/core/error_taxonomy.py:classify_content_blocker()
```

감지 시그널:
- DOM 내 `"cf-challenge"` 클래스 존재
- 페이지 타이틀 `"Just a moment..."` 포함

분류 결과:

```python
ErrorType.CAPTCHA_DETECTED → status = "BLOCKED"
```

이 시그널은 `playwright_probe._async_probe()` 내에서 DOM 수신 후 `classify_content_blocker()`를 호출하여 즉시 판정한다.

---

## 8. 현재 Retry 최대 시도

`ingestion/fetch_strategies/strategy_runner.py`:

```python
max_strategies_per_url = 3  # 기본값
```

- 전략 시퀀스(`STRATEGY_SEQUENCE`)에서 최대 3개 전략까지 순차 시도
- `BLOCKED_ERRORS`(CAPTCHA, LOGIN_WALL, PAYWALL, ROBOTS_BLOCKED) 수신 시 **즉시 중단** (나머지 전략 시도 없음)

---

## 9. 안전 재시도 vs 금지 우회 경계

| 구분 | ErrorType | 허용 동작 |
|------|-----------|-----------|
| 전략 전환 허용 | `EXTRACTION_EMPTY` | 다음 전략으로 전환 (최대 3회) |
| 전략 전환 허용 | `JS_RENDER_FAIL` | 다음 전략으로 전환 (최대 3회) |
| terminal BLOCKED | `CAPTCHA_DETECTED` | 즉시 중단, 우회 금지 |
| terminal BLOCKED | `LOGIN_WALL_DETECTED` | 즉시 중단, 우회 금지 |
| terminal BLOCKED | `PAYWALL_DETECTED` | 즉시 중단, 우회 금지 |
| terminal BLOCKED | `ROBOTS_BLOCKED` | 즉시 중단, 우회 금지 |
| 즉시 중단 (재시도 없음) | `RATE_LIMITED` | cooldown 후 외부 스케줄러가 재시도 |

**원칙**: 사이트가 명시적으로 접근을 거부하는 경우(CAPTCHA, robots.txt, login/paywall)는 어떤 전략으로도 우회를 시도하지 않는다. 이는 법적/윤리적 경계선이다.

---

## 10. Taxonomy 매핑표

| 현상 | ErrorType | status |
|------|-----------|--------|
| Cloudflare Turnstile / challenge 페이지 | `CAPTCHA_DETECTED` | `BLOCKED` |
| 로그인 필요 페이지 | `LOGIN_WALL_DETECTED` | `BLOCKED` |
| 유료 구독 필요 페이지 | `PAYWALL_DETECTED` | `BLOCKED` |
| robots.txt 크롤 차단 | `ROBOTS_BLOCKED` | `BLOCKED` |
| HTTP 429 / rate limit 헤더 | `RATE_LIMITED` | `RATE_LIMITED` + `cooldown_seconds` / `next_retry_at` |
| Selenium 설치됨 but Chrome 없음 | `BROWSER_NOT_FOUND` | `NOT_READY` |
| Selenium 미설치 | `CONFIG_ERROR` | `NOT_READY` (deferred) |
| JS 렌더 필요 but 렌더 실패 | `JS_RENDER_FAIL` | 다음 전략으로 전환 |
| HTML 존재 but 항목 없음 | `EXTRACTION_EMPTY` | 다음 전략으로 전환 |

---

## 11. 이번 라운드 구현 계획

### Step 0 — requirements 고정
- `requirements.txt` 핵심 deps 작성 (selenium, playwright, aiohttp, httpx 등)
- `requirements.lock.txt` 전체 의존성 고정

### Step 1 — Selenium readiness 완화
- `chromedriver` PATH 의존성 제거
- `selenium_installed AND chrome_binary_found` 기준으로 readiness 재판정
- `error_category` 세분화: `BROWSER_NOT_FOUND` / `CONFIG_ERROR`

### Step 2 — SeleniumFetchResult 신규 필드
- `screenshot_saved: bool` 필드 추가
- 스크린샷 저장 성공 여부를 결과 객체에 반영

### Step 3 — Google Trends rate limit 연동
- `rate_limit_policy.yaml` google_trends_explore 정책 반영
- `playwright_probe._async_probe()` 에서 429 감지 → RATE_LIMITED 응답 포맷 표준화

### Step 4 — FMKorea Turnstile 감지 연동 검증
- `classify_content_blocker()` 호출 경로 확인
- strategy_runner BLOCKED_ERRORS 목록에 CAPTCHA_DETECTED 포함 확인

### Step 5 — KRX XHR 캡처
- Playwright `page.on("request")` / `page.on("response")` 이벤트 캡처
- EUC-KR 인코딩 처리 추가 또는 JS 테이블 렌더 대기 로직 검토

### Step 6 — Playwright 전략 YAML 라우팅 일반화
- `playwright_probe_sites.yaml` 내 `collection_method: playwright` + `deferred: false` 사이트 자동 라우팅
- `_PLAYWRIGHT_FIRST_SOURCES` frozenset은 legacy fallback으로 유지

### Step 7 — strategy_runner 통합 검증
- `max_strategies_per_url=3` 동작 확인
- BLOCKED_ERRORS 즉시 중단 동작 확인
- RATE_LIMITED 즉시 중단 동작 확인

### Step 8 — 통합 smoke test
- 각 terminal status(BLOCKED, RATE_LIMITED, NOT_READY, LIVE_SUCCESS) 시뮬레이션
- 전략 전환(EXTRACTION_EMPTY → 다음 전략) 동작 확인

---

## 12. 검증 명령

```powershell
# Step 0: requirements 내용 확인
Get-Content C:\Users\computer\Desktop\business\claude\requirements.txt | Measure-Object -Line

# Step 1: Selenium readiness 단위 테스트
.venv\Scripts\python.exe -m pytest ingestion/tests/unit/test_selenium_readiness.py -v

# Step 2: SeleniumFetchResult 필드 확인
.venv\Scripts\python.exe -c "from ingestion.fetch_strategies.selenium_fetch import SeleniumFetchResult; import inspect; print(inspect.signature(SeleniumFetchResult))"

# Step 3: rate_limit_policy 로드 확인
.venv\Scripts\python.exe -c "from ingestion.core.rate_limit_policy import RateLimitPolicy; p = RateLimitPolicy(); print(p.get_policy('google_trends_explore'))"

# Step 4: taxonomy BLOCKED_ERRORS 확인
.venv\Scripts\python.exe -c "from ingestion.fetch_strategies.strategy_runner import BLOCKED_ERRORS; print(BLOCKED_ERRORS)"

# Step 7: strategy_runner import smoke
.venv\Scripts\python.exe -c "from ingestion.fetch_strategies.strategy_runner import StrategyRunner; print('OK')"

# Step 8: 전체 단위 테스트
.venv\Scripts\python.exe -m pytest ingestion/tests/unit/ -v --tb=short
```
