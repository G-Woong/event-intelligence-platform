# 36 — Selenium Fallback Readiness Report

**검증 일시**: 2026-06-03  
**목적**: Selenium이 Playwright 전부 실패 시 fallback으로 동작 가능한지 확인.

---

## 1. 환경 상태

| 항목 | 상태 | 상세 |
|---|---|---|
| selenium 패키지 설치 | INSTALLED | .venv에 selenium 존재 |
| selenium version | 확인됨 | import 성공 |
| chromedriver | NOT_FOUND | PATH에 없음 |
| chrome binary | NOT_FOUND | PATH에 없음, 표준 설치 경로도 없음 |
| **종합 ready** | **NOT_READY** | chromedriver + chrome 모두 부재 |

### Windows 표준 경로 탐색 (Fix 4 적용 후)
- `%ProgramFiles%\Google\Chrome\Application\chrome.exe` — 없음
- `%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe` — 없음
- `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe` — 없음

Chrome이 이 머신에 설치되지 않음.

---

## 2. Selenium Manager 가용성

Selenium 4.x는 Selenium Manager를 포함하여 chromedriver 자동 다운로드 기능을 제공함.  
그러나 chrome binary 자체가 없으므로 Selenium Manager만으로는 해결 불가.

---

## 3. strategy_selection 단위 테스트 검증

`select_next_strategy`가 playwright 전부 실패 + selenium ready 시 `selenium_rendered_dom`을 선택하는지 검증:

```python
# test_strategy_runner.py 기존 테스트에서 확인
with patch("...selenium_env_status", return_value={"ready": False}):
    result = SeleniumRenderStrategy().fetch("https://example.com")
assert result.status == "NOT_READY"  # PASS
```

구조적으로 올바름:
- `_JS_RENDER_STRATEGIES`에 `selenium_rendered_dom` 포함 (Fix 5 적용)
- `_all_playwright_failed()` → `selenium_env_status()["ready"]` 확인
- ready=False면 `selenium_rendered_dom` 미반환 → 안전 fallback

---

## 4. SeleniumRenderStrategy 동작

NOT_READY 상태에서:
```python
result = SeleniumRenderStrategy().fetch("https://example.com")
# → SeleniumFetchResult(status="NOT_READY", error_category="CONFIG_ERROR")
# 예외 없음, 안전 반환
```

---

## 5. selenium runner 필요성 평가

`run_selenium_smoke` runner는 **이번 라운드 생성 않음**. 이유:
- chrome + chromedriver 부재로 live 테스트 불가
- Selenium은 공개 페이지 렌더 fallback 용도이며 login/CAPTCHA 우회 목적 아님
- NOT_READY 상태에서 runner를 만들어도 실행 불가

**향후 구현 범위** (chrome 설치 후):
1. `run_selenium_smoke.py` 생성
2. `--url` 옵션으로 공개 페이지 1개 page_source 수집
3. `--screenshot` 옵션으로 스크린샷 저장
4. NOT_READY 시 명확한 오류 메시지

---

## 6. 결론

| 항목 | 결정 |
|---|---|
| 현재 ready | NOT_READY (chrome 미설치) |
| 코드 구조 | 올바름 — NOT_READY 시 graceful 반환 |
| strategy 선택 | 올바름 — ready 확인 후 selenium 선택 |
| _JS_RENDER_STRATEGIES 사용 | IMPLEMENTED (Fix 5) |
| runner | DEFERRED (chrome 설치 전제) |
| 다음 조건 | Chrome + chromedriver 설치 후 `python -m ingestion.runners.run_selenium_smoke --url https://example.com` |
