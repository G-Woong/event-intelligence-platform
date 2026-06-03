# 05_LOGGING_AND_ERROR_TAXONOMY — 로깅 설계 + 오류 분류

## 로그 종류

| 파일 | 위치 | 내용 |
|---|---|---|
| `{source_id}_runs.jsonl` | `logs/runs/` | source 전체 실행 요약 |
| `{source_id}_attempts.jsonl` | `logs/attempts/` | 시도별 strategy/결과 |
| `{source_id}_errors.jsonl` | `logs/errors/` | ErrorRecord 전체 |

### stdout 포맷

```
[PHASE1][bbc][attempt=2][readability] SUCCESS score=0.82
[PHASE2][reddit][attempt=1][playwright_basic] BLOCKED (LOGIN_WALL_DETECTED)
```

구현: `crawling/core/logging_setup.py`
- `SecretMaskingFilter` — OPENAI_API_KEY / LANGSMITH_API_KEY → `***`
- `JsonlHandler` — 4종 JSONL 파일 핸들러
- `configure_crawling_logging(log_dir, source_id)` — 최초 1회만 실행

---

## 25종 ErrorType

| # | ErrorType | 재시도 | 블로커 |
|---|---|---|---|
| 1 | NETWORK_TIMEOUT | ✓ | |
| 2 | NETWORK_DNS_FAIL | | |
| 3 | NETWORK_CONNECTION_RESET | ✓ | |
| 4 | HTTP_4XX | | |
| 5 | HTTP_5XX | ✓ | |
| 6 | HTTP_REDIRECT_LOOP | | |
| 7 | CAPTCHA_DETECTED | | ✓ |
| 8 | LOGIN_WALL_DETECTED | | ✓ |
| 9 | PAYWALL_DETECTED | | ✓ |
| 10 | ROBOTS_BLOCKED | | ✓ |
| 11 | JS_RENDER_FAIL | ✓ | |
| 12 | DOM_PARSE_ERROR | | |
| 13 | EXTRACTION_EMPTY | | |
| 14 | EXTRACTION_TOO_SHORT | | |
| 15 | EXTRACTION_BOILERPLATE_ONLY | | |
| 16 | EXTRACTION_ENCODING_ERROR | | |
| 17 | QUALITY_BELOW_THRESHOLD | | |
| 18 | QUALITY_PARTIAL | | |
| 19 | LLM_PARSE_ERROR | | |
| 20 | LLM_TIMEOUT | ✓ | |
| 21 | LLM_RATE_LIMIT | ✓ | |
| 22 | SCREENSHOT_FAIL | | |
| 23 | DOM_SNAPSHOT_FAIL | | |
| 24 | CONFIG_ERROR | | |
| 25 | UNKNOWN_ERROR | | |

블로커(BLOCKED_ERRORS) 감지 시: `quality_status = "BLOCKED"`, `should_retry = False`, 즉시 `strategy_reflection` 진입.

---

## Screenshot / DOM Snapshot 정책

- 실패 시 자동 저장 (`screenshot_on_failure: true`)
- 경로: `outputs/screenshots/{source_id}/attempt{n}_{strategy}.png`
- DOM: `outputs/dom_snapshots/{source_id}/attempt{n}_{strategy}.html` (최대 50,000자)
- 성공한 추출에도 저장 가능 (디버깅 목적)

---

## BLOCKED 처리 정책

- CAPTCHA/로그인/paywall/robots → 우회 시도 없이 BLOCKED 상태로 즉시 기록
- `ErrorRecord.is_blocker = True`
- `source_report.known_blockers_hit` 에 기록
- `recommended_action`: "API 전환 검토" 또는 "운영 범위 제외"
