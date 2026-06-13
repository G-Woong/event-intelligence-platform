# docs/51 — Remaining Source Value Samples

**Date**: 2026-06-08  
**주의**: 본문 전문 미포함. 핵심 필드 샘플만. 키값 미출력.

---

## eu_press_corner (LIVE_SUCCESS, items=10)

| 항목 | 값 |
|---|---|
| source_id | eu_press_corner |
| status | LIVE_SUCCESS |
| items_found | 10 |
| sample_title | "2026 Spring Semester Package presents a roadmap for advancing economic resilience..." |
| sample_url | `https://ec.europa.eu/commission/presscorner/home/detail/en/ip_26_1140` |
| core_fields | keyword, url |
| quality | title 포함 (Press release + date + headline + summary), URL 유효 |
| selector_used | `a[href*="detail/en/"]` |
| artifact_path | `ingestion/outputs/raw_signal/eu_press_corner/20260608_154110_*.json` |
| next_action | keyword 필드에서 title/date/summary 파싱 필요 (정규화 단계) |
| official | true |
| evidence_level | high |

**샘플 (제목만)**:
1. 2026 Spring Semester Package
2. Commission proposes tech sovereignty package to strengthen Europe's digital autonomy
3. Commission presents OceanEye initiative to put EU at the forefront of ocean observation

---

## loword (LIVE_SUCCESS, items=10)

| 항목 | 값 |
|---|---|
| source_id | loword |
| status | LIVE_SUCCESS |
| items_found | 10 |
| sample_keyword | "젠슨 황 서울대 강연" |
| sample_url | (없음 — 트렌드 키워드이므로 링크 없음) |
| core_fields | keyword |
| quality | 실시간 검색어 순위 키워드. URL 없음은 예상된 동작. |
| selector_used | `span[style*="line-height: 20px"]` (styled-components inline style) |
| artifact_path | `ingestion/outputs/raw_signal/loword/20260608_154501_*.json` |
| next_action | inline style 셀렉터 취약성 모니터링 (사이트 재빌드 시 변경 가능) |
| official | false |
| evidence_level | low |
| error_type_when_empty | LOW_EVIDENCE_EXTERNAL_SIGNAL |

**샘플 키워드**:
1. 젠슨 황 서울대 강연
2. 이재명 1주년 기자회견
3. 정규리 박우열 포스터 공개
4. 신입사원 강회장
5. 한화에어로 대표 중처법 혐의

---

## krx_kind (DEFERRED — 서버오류)

| 항목 | 값 |
|---|---|
| source_id | krx_kind |
| status | DEFERRED_SERVER_ERROR |
| items_found | 0 |
| error | kind.krx.co.kr 1.3KB 오류 페이지 반환 (EUC-KR 인코딩 타이틀) |
| deferred_reason | "SERVER_ERROR: confirmed 2026-06-08; retry next round" |
| next_action | mobile UA 시도 또는 kind.krx.co.kr API endpoint 직접 접근 검토 |

---

## fmkorea (BLOCKED — Turnstile)

| 항목 | 값 |
|---|---|
| source_id | fmkorea |
| status | BLOCKED |
| error_type | CAPTCHA_DETECTED (Cloudflare Turnstile) |
| deferred_reason | "BLOCKED: Cloudflare Turnstile bot challenge detected" |
| next_action | 공개 API 또는 RSS 피드 존재 여부 검토 (우회 금지) |

---

## google_trends_explore (RATE_LIMITED)

| 항목 | 값 |
|---|---|
| source_id | google_trends_explore |
| status | RATE_LIMITED |
| http_response | 429 Too Many Requests (1730바이트) |
| cooldown | 1800s (30분) 이미 적용 |
| next_action | cooldown 준수, 1회/30분 미만 호출 빈도 유지 |
