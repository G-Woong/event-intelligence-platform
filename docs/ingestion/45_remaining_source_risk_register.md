# 45 — Remaining Source Risk Register

**날짜**: 2026-06-03  
**목적**: 남은 리스크·다음 라운드 이슈 추적

---

## 오픈 리스크

| ID | 소스 | 리스크 | 심각도 | 다음 조치 |
|---|---|---|---|---|
| R01 | kma | 공공데이터포털 서비스 승인 대기 — 키가 있어도 401 반환 | Medium | 포털 재승인 신청 |
| R02 | its | ITS API 키 만료 또는 미발급 | Medium | its.go.kr 재발급 |
| R03 | tour | TourAPI 500 — 키 문제 또는 서버 일시 오류 | Medium | 키 재발급 + 재시도 |
| R04 | culture_info | culture.go.kr HTML 오류 페이지 — 키 미승인 | Medium | 키 재발급 |
| R05 | google_programmable_search | CX(검색엔진 ID) 미확인 — 400 Bad Request | Low | Google Cloud Console CX 확인 |
| R06 | eu_press_corner | Playwright 셀렉터 보강 완료, live DOM 테스트 미완 | Low | run_playwright_probe 실행 |
| R07 | loword | Playwright spec 추가됨, CSS 셀렉터 추정값 — DOM 검증 필요 | Low | run_playwright_probe + DOM 확인 |
| R08 | krx_kind | KRX 서버 오류 재현 가능성 — 재시도 필요 | Low | run_playwright_probe 재시도 |
| R09 | google_trends_explore | Playwright live 테스트 미완 | Low | run_playwright_probe (저빈도 1회) |
| R10 | tour | `_type=json` URL 더블인코딩 가능성 — httpx가 파라미터 재인코딩 | Low | serviceKey 디코딩 상태 확인 |

---

## 이연 항목 (DEFERRED)

| 항목 | 이유 | 재검토 시점 |
|---|---|---|
| Selenium live (selenium_strategy.py) | Chrome/chromedriver 미설치 (NOT_READY) | Chrome 환경 설치 후 |
| kma 키 재발급 | 공공데이터포털 처리 시간 필요 | 승인 후 즉시 |
| Celery+Redis 비동기 수집 | 별도 라운드 | Source Stabilization 종료 후 |
| KRX KIND 실시간 공시 | 서버 오류 재현 시 | 다음 평일 재시도 |

---

## 신규 분류 인프라 한계

| 항목 | 현재 상태 | 개선 필요사항 |
|---|---|---|
| HTTP 400 분류 | `UNKNOWN`으로 처리됨 | `PARAMETER_MISSING`/`ENDPOINT_INVALID`로 세분화 검토 |
| tour 더블인코딩 | serviceKey URL 인코딩 상태 미확인 | httpx params encoding 동작 확인 |
| kofic targetDt | 2026-06-02로 하드코딩 | 동적 계산 함수 도입 검토 |
| igdb 토큰 만료 | 메모리 캐시 (프로세스 재시작 시 재발급) | Redis 캐시 도입 시 영속성 고려 |

---

## 다음 라운드 준비사항

### 필수 (C 그룹 소스 수리)
1. `.env`에서 재발급된 키 업데이트
2. `python -m ingestion.runners.run_api_live_probe --service tour kma its culture_info`
3. `python -m ingestion.runners.run_playwright_probe --site eu_press_corner loword krx_kind`
4. google_trends_explore 저빈도 1회 테스트

### 선택 (코드 품질)
1. `_http_status_to_probe_status`에 400 → `PARAMETER_MISSING` 매핑 추가 검토
2. kofic `targetDt` 동적 계산 함수 추가
3. Playwright site_specs 테스트에서 loword 신규 spec 검증

---

## 완료 기준 (100% closed 선언을 위해)

- [ ] C 그룹 소스 9개 모두 LIVE_SUCCESS 또는 BLOCKED/DEFERRED 확정
- [ ] Playwright live 테스트 4개 완료 (eu_press_corner, loword, krx_kind, google_trends_explore)
- [ ] Google CSE CX 확인 후 LIVE_SUCCESS 확정
- [ ] 한국 공공 API 4개 키 재발급 후 LIVE_SUCCESS 또는 DEFERRED 확정
