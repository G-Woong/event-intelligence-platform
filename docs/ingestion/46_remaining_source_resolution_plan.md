# docs/46 — Remaining Source Resolution Plan

**Date**: 2026-06-08  
**Round**: Source Stabilization Round C — "Remaining Source Resolution & Browser Strategy Audit"  
**Context**: docs/45 이후 미해결 C그룹 소스 9종 + MVP 제외 상태 미반영 4종 + Playwright 전략 감사

---

## 대상 소스 분류

### A. MVP 제외 확정 (status 미반영 → 이번 라운드에서 반영)

| 소스 | 이유 | 조치 |
|---|---|---|
| x (Twitter) | API 유료($100+/월), 웹 login wall | source_registry.yaml status: MVP_EXCLUDED 추가 |
| blind | 직장 이메일 인증 login wall | source_registry.yaml status: MVP_EXCLUDED 추가 |
| reuters | Thomson Reuters 라이선스 제한 + bot protection | source_registry.yaml status: MVP_EXCLUDED 추가 |
| fmkorea | Cloudflare Turnstile bot challenge (기존 deferred) | playwright_probe_sites.yaml deferred 유지 |

### B. 비활성화 (코드/스펙 보존)

| 소스 | 이유 | 조치 |
|---|---|---|
| google_programmable_search | 400 응답, CX 미설정, 서비스 불확실 | status: DEPRECATED_OR_EXCLUDED, --all-safe 제외 |

### C. 한국 공공 API 4종 (키 있음, 원인 식별 및 수리 시도)

| 소스 | 예상 원인 | 수정 위치 | 성공기준 |
|---|---|---|---|
| culture_info | 키 이름 불일치(CULTURE_INFO_KEY↔API_KEY) + 잘못된 경로 | env_loader alias + run_api_connectivity_check.py 키명 | HTTP 200 XML, title/place/date |
| kma | response_format=json(실제 CSV) + param 없음 + 401 | api_probe.py spec 수정 + 키 승인 확인 | HTTP 200 text/CSV |
| tour | areaBasedList1/2 endpoint + serviceKey 이중인코딩 | api_probe.py 이중인코딩 방지 | HTTP 200 JSON, items≥1 |
| its | endpoint path 불확실 + 401 | run_api_connectivity_check.py endpoint | HTTP 200, items≥1 |

### D. Playwright 소스 4종

| 소스 | 예상 상태 | 성공기준 |
|---|---|---|
| eu_press_corner | LIVE_SUCCESS 기대 | items≥3 + title+url |
| loword | LIVE_PARTIAL → 셀렉터 수정 후 LIVE_SUCCESS 기대 | keyword≥5 |
| krx_kind | 서버오류 지속 가능성 | corp_name/title/date/url or DEFERRED 확정 |
| fmkorea | BLOCKED (Turnstile 확인) | Turnstile 확인 후 즉시 중단 |

### E. Google Trends Explore

1회만 실행. 429면 RATE_LIMITED + cooldown 확인.

---

## 인프라 변경 예정

| 파일 | 변경 |
|---|---|
| core/error_taxonomy.py | +2 ErrorType: SELECTOR_MATCHED_BUT_URL_EMPTY, LOW_EVIDENCE_EXTERNAL_SIGNAL |
| probes/models.py | PROBE_STATUS +2 |
| fetch_strategies/failure_classifier.py | _PROBE_STATUS_TO_ERROR_TYPE +2 매핑 |
| core/env_loader.py | CULTURE_INFO_API_KEY alias 추가 |
| runners/run_api_connectivity_check.py | culture_info 키명 수정, google CSE status_override |
| probes/api_probe.py | kma spec 수정, serviceKey 이중인코딩 방지 |
| runners/run_api_live_probe.py | --all-safe DEPRECATED_OR_EXCLUDED 필터 |
| configs/source_registry.yaml | x/blind/reuters MVP_EXCLUDED, google CSE DEPRECATED |
| configs/playwright_probe_sites.yaml | eu_press_corner/loword 셀렉터 보강 |

---

## 중단 기준

- Turnstile/Cloudflare 우회 시도 → SECURITY_BLOCKED
- login/paywall 감지 → 즉시 중단
- 반복 실패 API 호출 → 1회 이상 재시도 금지
- .env 키 값 로그 출력 → 즉시 중단
