# 54 — Selenium 설치 상태 및 런타임 체크

## 1. 설치 확인

```
selenium==4.26.1
```

`pip freeze` 출력으로 확인. 본 프로젝트 `.venv` 환경에 고정.

---

## 2. Selenium Manager 내장 (4.x)

Selenium 4.x부터 **Selenium Manager**가 내장되어, `Service()` 기본 호출 시 chromedriver를 자동 조달한다.

```python
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

# chromedriver PATH 없이 동작
driver = webdriver.Chrome(service=Service())
```

- chromedriver를 별도로 다운로드하거나 PATH에 등록할 필요 없음
- Selenium Manager가 Chrome 버전을 감지하고 호환 chromedriver를 자동 설치

---

## 3. webdriver-manager 별도 패키지 불필요

`webdriver-manager` (PyPI 패키지)는 과거 Selenium 3.x 시절 chromedriver 자동 관리를 위해 사용하던 서드파티 패키지다.

Selenium 4.x에서는 **Selenium Manager가 동일 기능을 내장**하므로:
- `webdriver-manager` 의존성 추가 불필요
- `requirements.txt`에 포함하지 않음
- 기존 코드에 `webdriver_manager` import가 있다면 제거 대상

---

## 4. Chrome Binary 탐지 결과

탐지 경로 순서:

1. `C:\Program Files\Google\Chrome\Application\chrome.exe`
2. `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
3. `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`
4. `PATH` 환경변수 탐색

**이번 세션 탐지 결과**:

```
chrome_binary_found: True
```

---

## 5. Readiness 판정 기준 변경

### 변경 전/후 비교

| 조건 | 이전 (chromedriver 요구) | 이후 (Selenium Manager) |
|------|--------------------------|------------------------|
| chromedriver PATH | 필수 | 불필요 |
| Chrome binary | 필요 | 필요 |
| ready 판정 로직 | `chromedriver AND chrome` | `selenium_installed AND chrome` |
| NOT_READY 사유 | chromedriver 미설치 | Chrome binary 없음 |

### 완화 후 readiness 코드 흐름

```python
def check_selenium_readiness() -> SeleniumReadinessResult:
    selenium_installed = _check_selenium_import()
    if not selenium_installed:
        return SeleniumReadinessResult(
            ready=False,
            status="NOT_READY",
            error_category="CONFIG_ERROR",
            detail="selenium package not installed"
        )

    chrome_found = _find_chrome_binary()
    if not chrome_found:
        return SeleniumReadinessResult(
            ready=False,
            status="NOT_READY",
            error_category="BROWSER_NOT_FOUND",
            detail="Chrome/Chromium binary not found"
        )

    return SeleniumReadinessResult(ready=True, status="READY")
```

---

## 6. SeleniumFetchResult 신규 필드

```python
@dataclass
class SeleniumFetchResult:
    url: str
    status: str                  # LIVE_SUCCESS / NETWORK_ERROR / NOT_READY 등
    html: str | None
    error_category: str | None
    screenshot_saved: bool        # 신규 필드
    screenshot_path: str | None   # 저장 경로 (screenshot_saved=True 일 때)
```

`screenshot_saved: bool` 필드는 스크린샷 저장 시도 결과를 명시적으로 반영한다.
저장 실패(디스크 오류, 경로 없음 등)는 `screenshot_saved=False`로 표현하며, 예외를 상위로 전파하지 않는다.

---

## 7. error_category 세분화

| 상황 | error_category | status |
|------|----------------|--------|
| selenium 미설치 (`import selenium` 실패) | `CONFIG_ERROR` | `NOT_READY` |
| selenium 설치됨 but Chrome/Chromium binary 없음 | `BROWSER_NOT_FOUND` | `NOT_READY` |
| Chrome 있음, 드라이버 자동 조달 실패 | `DRIVER_INIT_ERROR` | `NOT_READY` |
| 정상 준비 완료 | `None` | `READY` |

---

## 8. Smoke Test 결과

```
status         : LIVE_SUCCESS
html_length    : 513
screenshot_saved: True
error_category : None
```

테스트 대상 URL: `https://example.com` (공개 테스트용)
실행 환경: Windows 11, Chrome (ProgramFiles 경로), selenium 4.26.1

---

## 9. Docker / 배포 요구사항

컨테이너 환경에서는 Chrome binary가 없으므로 반드시 별도 설치가 필요하다.

```dockerfile
# Debian/Ubuntu 계열
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# 또는 Google Chrome 공식 패키지
RUN apt-get install -y google-chrome-stable
```

환경 변수 설정 (헤드리스 모드):

```bash
CHROME_BIN=/usr/bin/chromium
DISPLAY=:99  # Xvfb 사용 시
```

---

## 10. NOT_READY 유지 조건

Chrome/Chromium binary가 없는 서버에서는:

- `SeleniumFetchResult(status="NOT_READY", error_category="BROWSER_NOT_FOUND")` 반환
- 예외(Exception) 발생 없음 — 안전하게 NOT_READY 응답
- 상위 `strategy_runner`는 NOT_READY를 수신하면 해당 전략을 건너뜀
- 운영자가 Chrome 설치 후 재시도 가능 (deferred 패턴)
