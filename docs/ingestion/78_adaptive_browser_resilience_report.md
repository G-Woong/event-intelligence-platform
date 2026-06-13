# 78. Adaptive Browser Resilience 보고서 (RISK 12-5)

날짜: 2026-06-12

## 1. 결론

전략 복원력(예산·점프·selenium gate·terminal blocker)은 **이미 구현되어 있었고**, 이번
라운드는 **동작 변경 없이** 회귀 테스트 14개로 고정했다. 코드 diff 없음 — 향후 리팩토링이
복원력 계약을 깨면 테스트가 잡는다.

## 2. 테스트로 고정된 계약 (`test_strategy_resilience.py` — 14 passed)

| 계약 | 테스트 |
|------|--------|
| CAPTCHA 감지 → terminal blocked, **추가 시도 없음** (attempts=1) | `test_captcha_terminates_loop_with_no_further_attempts` |
| login wall → BLOCKED 종료 | `test_login_wall_terminates_loop` |
| CAPTCHA/LOGIN/PAYWALL/ROBOTS 4종 모두 select_next_strategy=None | `test_all_blockers_stop_strategy_selection` |
| Turnstile/cf-challenge 페이지 → CAPTCHA_DETECTED 분류 | `test_turnstile_page_classified_as_captcha` |
| attempt history에 전략명이 STRATEGY_SEQUENCE 순서로 기록 | `test_attempt_history_records_strategy_names` |
| 기본 소스 budget=3 attempts 후 exhausted | `test_default_budget_is_3_attempts` |
| krx_kind=8 / dcinside=6 / 기본 3 (retry_policy.yaml per_source) | `test_per_source_budget_*`, `test_krx_kind_loop_reaches_8_attempts` |
| EXTRACTION_EMPTY(httpx) → playwright_basic 직접 점프 | `test_extraction_empty_on_httpx_jumps_to_playwright_basic` |
| selenium은 `selenium_env_status()["ready"]`일 때만 선택 | `test_selenium_only_selected_when_env_ready` |
| RSS/feed/xml 소스는 playwright 전략 미진입 | `test_rss_source_never_enters_playwright` |

## 3. 허용/금지 전략 구분 (운영 원칙)

### 허용 (자동 복원 시도)
- httpx UA 변형 (direct/mobile/random) — 공개 페이지 일반 접근
- 추출기 교체 (readability/trafilatura/dom_heuristic)
- JS 렌더 (playwright 4변형, selenium fallback)
- EXTRACTION_EMPTY 시 브라우저 점프 (낭비 시도 생략)
- 429 → 정책 cooldown 후 재시도 (max_retries_on_429 한도 내)

### 금지 (감지 즉시 terminal BLOCKED — 우회 시도 없음)
- CAPTCHA / Cloudflare Turnstile / challenge solving
- 로그인 월 우회 (계정/세션 위조)
- 페이월 우회
- robots.txt 무시

challenge solving 미구현이 12-5의 핵심 준수 사항이며, blocker 4종 → None 테스트가 이를
가드한다.

## 4. 아키텍처 결정 — health store 통합 지점

`strategy_runner`는 health store를 직접 보지 않는다. health gate/갱신의 통합 지점은
**`collection_probe` 단일화**다 (docs/76 §4). 이유:
- strategy_runner는 "한 URL에 대한 전략 루프"라는 단일 책임을 유지 (rate limit cooldown만 관여)
- health는 소스 단위 개념 — 소스 단위 진입점(collection_probe)에서만 판단
- Celery task(plans/012)도 collection_probe를 호출하므로 gate가 자동 적용됨

## 5. CLI에서 attempts 확인

신규 `run_collection_probe` CLI(12-10)의 `--json` 출력에 attempts(전략명/성공여부/에러)가
포함된다 — 별도 artifact writer는 만들지 않았다 (요구 범위 준수).
