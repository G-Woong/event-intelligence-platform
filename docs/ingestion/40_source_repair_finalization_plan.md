# 40 — Source Repair Finalization Plan

**날짜**: 2026-06-03  
**목적**: Source Stabilization 단계 종료를 위한 미수리 소스 끝까지 수리

---

## 컨텍스트 요약

이전 라운드(docs 27–39)에서 56개 소스를 재검증했으나, 다음 카테고리가 LIVE_SUCCESS로 확정되지 못함:

| 카테고리 | 소스 | 원인 |
|---|---|---|
| P0 (파라미터 결손) | finnhub, alpha_vantage, kofic, tour, igdb | `_PROBE_SPEC` 부재 — params 0개로 호출 |
| P0 (cx 드롭) | google_programmable_search | 2번째 키(CX)가 주입되지 않음 |
| P0 (오탐) | naver_news_search | `total` 정수를 items 수로 셈 → false LIVE_SUCCESS |
| P1 (문서확인) | kopis, eu_press_corner, loword, gdelt, igdb | 추가 조사 필요 |
| P2 (한국 공공 API) | kma, tour, its, culture_info | endpoint/param/serviceKey 전달방식 불명확 |
| BLOCKED | fmkorea, x, blind, reuters | 약관/로그인/라이선스 |

---

## 구조적 결함 목록

1. **"HTTP 200 = 성공" 오탐**: `{"items":[], "total":5}` → 5 items로 보고됨
2. **`_PROBE_SPEC` 부재**: 7개 소스에 probe spec 없음 → 파라미터 0개 호출
3. **google CSE cx 드롭**: `auth: query_param_key`가 첫 번째 키만 주입, 두 번째(CX) 드롭
4. **igdb OAuth 미구현**: IGDB_CLIENT_ID를 Bearer token으로 직접 사용(오류)
5. **XML 오류페이지 미탐지**: `<errormsg>` 포함 XML을 LIVE_SUCCESS로 분류

---

## 수정 계획

### Step 2: 신규 분류 인프라 (완료)

**`core/error_taxonomy.py`** — 8종 추가 (26→34):
- `PARAMETER_MISSING`, `ENDPOINT_INVALID`, `INVALID_KEY`
- `QUERY_ENCODING_OR_PARAM_ERROR`, `INVALID_SYMBOL_OR_EMPTY_MARKET_DATA`
- `XML_PARAMETER_ERROR`, `API_RETURNED_HTML_ERROR_PAGE`, `DYNAMIC_RENDER_REQUIRED`

**`probes/api_probe.py`** 탐지 로직:
- empty-items + total>0 → `QUERY_ENCODING_OR_PARAM_ERROR`
- all-zero numeric fields → `INVALID_SYMBOL_OR_EMPTY_MARKET_DATA`
- XML errormsg/errorcode → `XML_PARAMETER_ERROR`
- HTML 에러페이지 → `API_RETURNED_HTML_ERROR_PAGE`
- Alpha Vantage "Error Message" → `PARAMETER_MISSING`

**`probes/models.py`** — `PROBE_STATUS` frozenset에 7개 신규 status 추가

**`fetch_strategies/failure_classifier.py`** — 7개 신규 probe→ErrorType 매핑

### Step 3: P0 수리 (완료)

| 소스 | 수정 내용 | 상태 |
|---|---|---|
| google_programmable_search | `_PROBE_SPEC` 추가 + cx 주입 코드 | REPAIRED |
| naver_news_search | `meaningful_fields`: `["items","total"]` → `["items"]` | REPAIRED |
| naver_blog_search | 동일 | REPAIRED |
| finnhub | `_PROBE_SPEC` 신규 (symbol=AAPL) | REPAIRED |
| kofic | `_PROBE_SPEC` 신규 (targetDt=20260602) | REPAIRED |
| alpha_vantage | `_PROBE_SPEC` 신규 (function, symbol, outputsize) | REPAIRED |
| igdb | Twitch OAuth2 구현 + `_PROBE_SPEC` | REPAIRED |
| `core/env_loader.py` | GOOGLE_CUSTOM_SEARCH_API_KEY alias 추가 | REPAIRED |

### Step 4: P1 수리

| 소스 | 수정 내용 | 상태 |
|---|---|---|
| kopis | `_PROBE_SPEC` 존재(stdate/eddate/rows), XML 에러탐지 추가 | REPAIRED |
| eu_press_corner | playwright yaml 셀렉터 보강 + wait_after_ms 4000 | REPAIRED |
| loword | playwright yaml에 신규 spec 추가 (셀렉터 테스트 필요) | SPEC_ADDED |
| gdelt | rate_limit 정책 기존 적용 중, live 1회 시도 필요 | PENDING_LIVE |

### Step 5: P2 한국 공공 API

| 소스 | 분석 결과 | 상태 |
|---|---|---|
| tour | MobileOS/MobileApp/_type=json 필수 params → `_PROBE_SPEC` 추가 | REPAIRED |
| its | endpoint path `/NCMInfra/getLinkTrafficInfo` 추가 | REPAIRED |
| culture_info | 기존 spec 유지, HTML 에러페이지 탐지 추가 | REPAIRED |
| kma | 401 원인: 공공데이터포털 승인 필요 가능성 (INVALID_KEY_REISSUE_REQUIRED) | ANALYSIS_DONE |

---

## 하드 제약 (불변)

- API 키·Authorization·토큰·`.env` 값 출력/로그/artifact 저장 전면 금지
- login/CAPTCHA/paywall/bot-protection 우회 금지
- destructive 명령(rm/Remove-Item/reset --hard/clean/push) 미사용
- HTTP 200만으로 성공 처리 금지 — 실제 값 검증
