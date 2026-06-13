# 15 — Scrapfly Feature Gap Analysis

이 문서는 Scrapfly(클라우드 브라우저 서비스)의 공식 기능을 우리 내부 스택과 비교하여, 즉시 구현 / 부분 구현 / 보류로 분류한다.

## Scrapfly 주요 기능 목록

| Scrapfly 기능 | 설명 | 우리 내부 대체 | 상태 |
|---|---|---|---|
| JS 렌더링 (headless Chrome) | SPA, Vue, React 페이지 렌더링 | `playwright_browser_tool.fetch_with_playwright_sync` | ✅ 즉시 구현 |
| 스크린샷 | 렌더 후 PNG 캡처 | `artifact_store.get_screenshot_path` + Playwright screenshot | ✅ 즉시 구현 |
| Markdown 추출 | HTML→Markdown 변환 | `tools/markdown_extractor.extract_markdown` (trafilatura) | ✅ 즉시 구현 |
| Rendered DOM 저장 | 렌더된 HTML 파일 저장 | `artifact_store.save_rendered_dom` | ✅ 즉시 구현 |
| 봇 차단 감지 | Cloudflare, hCaptcha 등 탐지 | `error_taxonomy.classify_content_blocker` | ✅ 즉시 구현 |
| 전략 fallback | 실패 시 다음 전략 시도 | `fetch_strategies.strategy_runner.run_fetch_strategy_loop` | ✅ 즉시 구현 |
| 통합 결과 모델 | render+extract+artifact 단일 결과 | `CloudBrowserLikeStrategy` → `RenderedPageFetchResult` | ✅ 즉시 구현 |
| Extraction (readability) | 본문 추출 | `readability_extractor`, `trafilatura_extractor`, `dom_heuristic` | ✅ 즉시 구현 |
| Anti-scraping bypass (회전 UA) | User-Agent 순환 | `httpx_mobile_ua`, `httpx_random_ua` 전략 | ✅ 즉시 구현 |
| 요청 재시도/backoff | 지수 backoff 재시도 | `RetryPolicy.delay_for_attempt`, `strategy_runner` | ✅ 즉시 구현 |
| IP rotation / Proxy | 다른 IP로 재요청 | ❌ 미구현 | 🔄 DEFERRED |
| CAPTCHA solver | hCaptcha/reCAPTCHA 자동 해결 | ❌ 미구현 — 윤리/법적 이슈 | 🚫 BLOCKED (컴플라이언스) |
| Geolocation (국가 선택) | 특정 국가 IP로 요청 | ❌ 미구현 | 🔄 DEFERRED |
| Session/Cookie 관리 | 로그인 세션 유지 | ❌ 미구현 — login wall 정책 | 🚫 BLOCKED (컴플라이언스) |
| ASP (Anti-Scraping Protection) bypass | Cloudflare Enterprise 등 우회 | ❌ 미구현 | 🔄 DEFERRED |
| 분산 실행 / 큐 | 대규모 병렬 크롤링 | Celery+Redis (기반 구조 있음, 미연결) | 🔄 DEFERRED |

## 내부 대체 구현 요약

```
Scrapfly ScrapeApiResponse
    ├─ result.html          → RenderedPageFetchResult.html
    ├─ result.markdown      → RenderedPageFetchResult.markdown
    ├─ result.screenshot    → RenderedPageFetchResult.screenshot_path
    ├─ result.dom           → RenderedPageFetchResult.rendered_dom_path
    ├─ result.text          → RenderedPageFetchResult.extracted_text
    └─ result.status_code   → RenderedPageFetchResult.status
```

## 차이점 및 제약

1. **IP rotation 없음**: 단일 IP에서 요청 → 429 RATE_LIMITED 시 단순 backoff만 가능
2. **CAPTCHA 해결 없음**: CAPTCHA_DETECTED 시 즉시 BLOCKED 기록, 우회 코드 금지
3. **Geolocation 없음**: 한국 IP에서만 요청 (일부 해외 콘텐츠 접근 제한 가능)
4. **Selenium 대비**: Playwright fingerprint 감지 시 Selenium 전환 가능 (현재 scaffold)
5. **비용**: 내부 구현은 Scrapfly API 요금 없음; 단 서버 리소스 직접 사용

## 결론

Scrapfly 핵심 기능(JS render, screenshot, markdown, bot detection, fallback)은 **100% 내부 구현으로 대체**되었다. IP rotation, CAPTCHA bypass, geolocation은 컴플라이언스 경계(`COMPLIANCE_BOUNDARY.md`) 준수로 인해 BLOCKED 또는 DEFERRED.
