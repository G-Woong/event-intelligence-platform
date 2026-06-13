# 13 — Browser Strategy Environment

## 환경 요약 (2026-06-03)

| 항목 | 상태 | 버전/경로 |
|---|---|---|
| Python | ✅ 설치됨 | 3.11.9 |
| Playwright | ✅ 설치됨 | `playwright` package present |
| Playwright Chromium | ✅ 설치됨 | `python -m playwright install chromium` 완료 |
| trafilatura | ✅ 설치됨 | 1.12.2 |
| selenium | ✅ 설치됨 (패키지) | 4.26.1 |
| chromedriver | ❌ 미설치 | PATH에 없음 |
| Chrome/Chromium binary | ❌ 미확인 | system Chrome 없음 |

## Playwright (Primary Browser Engine)

**위치**: `ingestion/tools/playwright_browser_tool.py`

**지원 전략**:
| 전략 | 용도 |
|---|---|
| `playwright_basic` | 기본 JS 렌더링 (domcontentloaded) |
| `playwright_scroll` | 무한 스크롤 페이지 (3회 스크롤) |
| `playwright_wait_network_idle` | XHR/fetch 완료 대기 |
| `playwright_click_more` | "더 보기" 버튼 클릭 후 추출 |

**설정**:
- rate limit: 2초 최소 간격 (`_MIN_DELAY_SEC = 2.0`)
- viewport: 1280×720, headless=True
- User-Agent: Chrome 120 (Windows) — honest UA `event-intelligence/0.7 (+ei)` 는 httpx에만 사용

**설치 명령**:
```bash
python -m playwright install chromium
```

## CloudBrowserLikeStrategy (내부 통합 래퍼)

**위치**: `ingestion/fetch_strategies/cloud_browser_like.py`

Playwright + trafilatura markdown + artifact_store를 하나의 표준화된 결과(`RenderedPageFetchResult`)로 묶는다. Scrapfly 등 외부 클라우드 브라우저 서비스의 기능을 내부적으로 대체:

| Scrapfly 기능 | 내부 대체 |
|---|---|
| JS 렌더링 | `playwright_browser_tool.fetch_with_playwright_sync` |
| 스크린샷 | `artifact_store.get_screenshot_path` + Playwright |
| Markdown 추출 | `tools/markdown_extractor.extract_markdown` (trafilatura) |
| Rendered DOM 저장 | `artifact_store.save_rendered_dom` |
| 봇 탐지 (Cloudflare 등) | `error_taxonomy.classify_content_blocker` |

## Selenium (Scaffold Only)

**위치**: `ingestion/fetch_strategies/selenium_strategy.py`

현재 상태: **NOT_IMPLEMENTED** (scaffold 뼈대만 존재)

Playwright Chromium이 현재 소스 집합의 JS 렌더링을 완전히 커버하므로 Selenium live 구현은 이번 라운드에서 불필요하다고 판단.

**필요성 판단**:
- Playwright fingerprint를 타겟팅하는 봇 차단이 감지될 경우에만 필요
- 현재까지 해당 케이스 없음 → DEFERRED

**활성화 방법** (필요 시):
```bash
pip install selenium
# Chrome 버전 확인
google-chrome --version
# 매칭 chromedriver 다운로드: https://chromedriver.chromium.org/
# chromedriver를 PATH에 추가
```

**환경 점검 함수**:
```python
from ingestion.fetch_strategies.selenium_strategy import selenium_env_status
print(selenium_env_status())
# {'selenium_installed': True, 'selenium_version': '4.26.1', 
#  'chromedriver_found': False, 'chrome_binary_found': False, 'ready': False}
```

## 한계 및 주의사항

- headless Chrome은 일부 사이트의 anti-bot 탐지에 걸릴 수 있음 → CAPTCHA_DETECTED로 기록하고 BLOCKED
- IP rotation / proxy 미구현 — 이번 라운드 DEFERRED
- Playwright 동시 실행 미지원 (Celery worker에서 asyncio event loop 충돌 가능) → 별도 프로세스 격리 필요
- Windows에서 asyncio.run() 중첩 제한 → `fetch_with_playwright_sync`가 이미 `asyncio.run()`으로 동기화
