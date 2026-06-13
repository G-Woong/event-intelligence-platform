# 59 — Browser Strategy & Safe Retry Framework: 최종 보고

> 대상 독자: 비개발자 포함 전체 이해관계자

---

## ① 한 줄 결론

Selenium 활성화(LIVE_SUCCESS), Playwright 전략 레이어 감사 완료, 3회 안전 재시도 검증, Google Trends RATE_LIMITED 정확 분류, KRX DEFERRED(서버오류 근거), FMKorea BLOCKED(Turnstile 우회 금지) — **테스트 349개 전체 통과**.

---

## ② Selenium 상태

- `selenium==4.26.1` 설치 완료
- Chrome binary 자동 감지
- Selenium Manager를 통한 `chromedriver` 자동 조달 (별도 설치 불필요)
- `run_selenium_smoke` 실행 결과: `LIVE_SUCCESS` (html=513B, screenshot 저장)
- **readiness 조건 완화 적용**: Chrome binary 존재 여부만 확인 (chromedriver 별도 확인 불필요)

---

## ③ Playwright 구조

- 두 가지 경로:
  1. `CloudBrowserLikeStrategy` — 복잡한 봇 방어 대응
  2. `playwright_probe` — 직접 렌더링 probe
- `_PLAYWRIGHT_FIRST_SOURCES` frozenset + YAML 기반 자동 라우팅으로 일반화
- 표준 출력 필드: `rendered_dom` / `screenshot` / `raw_signal` / `network_log`

---

## ④ 3회 재시도 구조

`strategy_runner.py:max_strategies_per_url=3`

| 조건 | 동작 |
|------|------|
| `EXTRACTION_EMPTY` | 다음 전략으로 전환 허용 |
| `JS_RENDER_FAIL` | 다음 전략으로 전환 허용 |
| `CAPTCHA` / `LOGIN` / `PAYWALL` / `ROBOTS_BLOCKED` | 즉시 terminal BLOCKED (우회 없음) |

---

## ⑤ Google Trends RATE_LIMITED 처리

- `_detect_429()` 헬퍼가 렌더된 HTML에서 429 신호 감지
- 감지 시 `status=RATE_LIMITED` + `cooldown_seconds=600` + `next_retry_at` (ISO 8601) 자동 부착
- `LIVE_PARTIAL` degrade 방지 완료
- **ProbeResult 신규 5개 메타 필드**: `cooldown_seconds`, `next_retry_at`, `retry_after_reason`, `cache_hit`, `network_log`

---

## ⑥ KRX 결과

- networkidle 대기 + XHR 캡처 구현 완료
- `kind.krx.co.kr` → 서버오류 페이지(약 1.3KB) 지속 반환
- 상태: `DEFERRED_SERVER_ERROR` 유지
- **다음 단계**: 공식 데이터포털 API(`open.krx.co.kr`) 또는 모바일 UA 재시도

---

## ⑦ FMKorea 결과

- Cloudflare Turnstile 확정 (2026-06-03 이후 지속)
- 상태: `BLOCKED + CAPTCHA_DETECTED`
- **우회 금지** — 본 시스템 운영 원칙에 따라 challenge solving 시도 없음
- **대체 소스**: dcinside(이미 활성), naver_news_search, signal_bz 등

---

## ⑧ 보안

- `outputs/` 디렉토리 스캔 결과: 실제 키 값 미발견 (오류 메시지만 존재)
- `.env` WARNING: `CLIENT_ID` / `CLIENT_SECRET` → `NAVER_` prefix 사용 권장 (실키 유출 아님)
- 하드코딩된 API 키 없음
- 모든 키는 `os.getenv` 또는 `pydantic-settings` 경유

---

## ⑨ 테스트 결과

| 항목 | 수 |
|------|----|
| 전체 통과 | **349 passed** |
| 실패 | **0 failed** |

신규 테스트 항목:

| 테스트 분류 | 케이스 수 |
|-------------|-----------|
| bot 감지 | 5 |
| Selenium readiness | 4 |
| ProbeResult 신규 필드 | 7 |
| 429 감지 | 4 |
| network_log | 2 |

---

## ⑩ 남은 리스크 및 사용자 조치 필요 사항

| 리스크 | 설명 | 권장 조치 |
|--------|------|-----------|
| in-process rate limit cache 휘발 | 프로세스 재시작 시 캐시 초기화 | Redis persistent cache 도입 |
| `.env` 키 이름 불일치 | `CLIENT_ID` → `NAVER_CLIENT_ID` 권장 | `.env` 키 이름 변경 |
| Docker 배포 시 binary 누락 | Chrome/Chromium 미설치 시 Selenium 미작동 | Dockerfile에 Chrome 설치 추가 |
| KRX API 키 미발급 | 공식 데이터포털 API 사용 불가 | `open.krx.co.kr` OpenAPI 키 발급 |

---

## ⑪ 다음 단계

- **A**: KRX 공식 데이터포털 API 라운드 — `open.krx.co.kr` OpenAPI 키 발급 후 REST 직접 호출
- **B**: Redis persistent rate limit cache + Celery 비동기 수집 연동
- **C**: `event_candidate` / LLM inference / Knowledge Graph 구축 (main pipeline phase)

---

다음 권장 단계는 **A — KRX 공식 데이터포털 API 라운드**입니다.
