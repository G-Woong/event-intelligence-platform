# docs/48 — Remaining Source Resolution Report

**Date**: 2026-06-08  
**Round**: Remaining Source Resolution & Browser Strategy Audit  
**Status**: PARTIAL — 코드 수리 완료, 4종 API 원인 식별, Playwright 2종 LIVE_SUCCESS

---

## 1. MVP 제외 확정 결과

### source_registry.yaml 변경 (status 필드 신규 추가)

| 소스 | status | exclusion_reason |
|---|---|---|
| x | MVP_EXCLUDED | X API v2 Basic 유료($100+/월), 웹 login wall |
| blind | MVP_EXCLUDED | 직장 이메일 인증 login wall, 우회 불가 |
| reuters | MVP_EXCLUDED | Thomson Reuters 라이선스 제한, bot protection |
| fmkorea | deferred:true 유지 | Cloudflare Turnstile (2026-06-03 확인, 재확인 2026-06-08) |
| google_programmable_search | DEPRECATED_OR_EXCLUDED | 400 응답, CX 미설정; 코드/spec/alias 보존 |

---

## 2. 신규 ErrorType 2종

| ErrorType | 의미 | retryable | blocker |
|---|---|---|---|
| SELECTOR_MATCHED_BUT_URL_EMPTY | Playwright selector 매칭됐으나 href/url 비어 있음 | false | false |
| LOW_EVIDENCE_EXTERNAL_SIGNAL | official=false, evidence_level=low 비공식 외부 시그널 | false | false |

기존 enum 매핑표 (중복 회피):

| 의미 | 기존 enum | 별도 추가 불필요 이유 |
|---|---|---|
| PUBLIC_API_SERVER_500 | HTTP_5XX | 동일 의미 |
| SERVICE_KEY_ENCODING | QUERY_ENCODING_OR_PARAM_ERROR | 포함 |
| SERVICE_NOT_APPROVED / INVALID_KEY | INVALID_KEY | 동일 |
| ENDPOINT_MISMATCH | ENDPOINT_INVALID | 동일 |
| REQUIRED_PARAM_MISSING | PARAMETER_MISSING | 동일 |
| HTML_ERROR_PAGE | API_RETURNED_HTML_ERROR_PAGE | 동일 |
| TURNSTILE | CAPTCHA_DETECTED | 포함 |
| DYNAMIC_TABLE_RENDER | DYNAMIC_RENDER_REQUIRED | 포함 |

---

## 3. 한국 공공 API 4종 원인 식별 + 수리 결과

### 3.1 culture_info

- **원인**: 두 가지 — (1) `_SERVICE_CONFIGS` 키명 `CULTURE_INFO_KEY` vs registry `CULTURE_INFO_API_KEY` 불일치, (2) API 호출 시 "잘못된 경로" HTML 오류 페이지 반환
- **수리**: 키명 `CULTURE_INFO_API_KEY`로 통일, `env_loader._ALIASES`에 `CULTURE_INFO_API_KEY→["CULTURE_INFO_KEY"]` 추가
- **live 결과**: `API_RETURNED_HTML_ERROR_PAGE` (HTTP 200) — "문화포털 페이지가 없거나 잘못된 경로"
- **남은 문제**: culture.go.kr OpenAPI endpoint 경로 불일치 (현행 endpoint 재확인 필요)
- **분류**: `REPAIRABLE_NEXT`
- **사용자 후속조치**: culture.go.kr 개발자 포털에서 현행 API 명세 확인 후 endpoint 경로 업데이트

### 3.2 kma (기상청)

- **원인**: (1) `response_format="json"` → 실제 반환은 text/CSV, (2) 필수 param `tm`/`stn` 누락, (3) 401 INVALID_KEY
- **수리**: `api_probe.py` kma spec → `response_format="text"`, `extra_params={"tm":"202606080000","stn":"108","help":"1"}`
- **live 결과**: `INVALID_KEY` (HTTP 401) — 키 미승인 또는 Decoding 키 필요
- **분류**: `REPAIRABLE_NEXT` (코드 수리 완료, 키 승인 선결)
- **사용자 후속조치**: 공공데이터포털(data.go.kr) → 기상청 기후통계분석/시간자료 API 승인 신청. apihub.kma.go.kr 계정 필요 가능성

### 3.3 tour (한국관광공사 TourAPI)

- **원인**: (1) serviceKey 이중인코딩 가능성, (2) `areaBasedList1` 현행 여부 불확실
- **수리**: `api_probe.py` `query_param_serviceKey` auth에 이중인코딩 방지 (`%` 포함 시 `unquote` 후 전달)
- **live 결과**: `NETWORK_ERROR` (HTTP 500) — "Unexpected errors" (이중인코딩 방지 후에도 동일)
- **분류**: `REPAIRABLE_NEXT` (이중인코딩 수리 완료, endpoint 재확인 필요)
- **사용자 후속조치**: `.env`에 Decoding 키 사용 확인. TourAPI v4 포털에서 `areaBasedList2` 현행 여부 확인. 공공데이터포털 API 승인 상태 확인

### 3.4 its (국토교통부 ITS)

- **원인**: endpoint path "needs verification" + 401 INVALID_KEY
- **수리**: 코드 수리 없음 (endpoint 재확인 필요)
- **live 결과**: `INVALID_KEY` (HTTP 401) — 키 미승인
- **분류**: `REPAIRABLE_NEXT` (키 승인 + endpoint 재확인 선결)
- **사용자 후속조치**: its.go.kr 포털에서 API 이용신청. 현행 endpoint path 확인 (NCMInfra/getLinkTrafficInfo 또는 다른 리소스)

---

## 4. Playwright 소스 4종 검증 결과

| 소스 | 이전 상태 | 이번 결과 | items | 비고 |
|---|---|---|---|---|
| eu_press_corner | LIVE_SUCCESS(items=1, url 비어) | **LIVE_SUCCESS** | **10** | `a[href*="detail/en/"]` 셀렉터 추가로 수정 |
| loword | LIVE_PARTIAL(items=0) | **LIVE_SUCCESS** | **10** | `span[style*="line-height: 20px"]` 셀렉터 추가 |
| krx_kind | DEFERRED_SERVER_ERROR | DEFERRED 유지 | 0 | 1.3KB 오류 페이지 재확인 (2026-06-08) |
| fmkorea | DEFERRED(Turnstile) | DEFERRED 유지 | 0 | `deferred: true` 유지 |

---

## 5. Google Trends Explore

- **live 결과**: `LIVE_PARTIAL` (items=0, 1730바이트 응답)
- **원인**: HTTP 429 Too Many Requests — "Error 429 (Too Many Requests)!!1"
- **분류**: RATE_LIMITED
- **cooldown**: 기존 정책(1800s/600s) 이미 적용 확인. 재시도 금지.

---

## 6. Google Programmable Search 재활성화 조건

- **현재 상태**: `DEPRECATED_OR_EXCLUDED` (--all-safe 제외)
- **코드/spec/alias/cx 보존 여부**: ✓ (삭제 안 함)
- **재활성화 조건**:
  1. Google Cloud Console에서 Custom Search JSON API 활성화
  2. Search Engine ID (CX) 신규 생성 또는 기존 CX 유효성 확인
  3. `.env`에 `GOOGLE_CUSTOM_SEARCH_API_KEY` 및 `GOOGLE_CUSTOM_SEARCH_CX` 설정
  4. `source_registry.yaml` status `DEPRECATED_OR_EXCLUDED` → `MISSING_KEY` 변경
  5. `_SERVICE_CONFIGS["google_programmable_search"]`에서 `status_override` 제거
  6. `run_api_live_probe --service google_programmable_search` 1회 테스트
- **Custom Search JSON API 현황**: API 자체는 운영 중 (2024년 기준). 400 오류는 서비스 종료가 아니라 CX 미설정/만료로 판단.
