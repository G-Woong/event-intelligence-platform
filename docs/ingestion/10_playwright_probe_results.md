# 10 Playwright Probe Results

실행일: 2026-06-03  
총 사이트: 5개 실행 (krx_kind/eu_press_corner는 DEFERRED)

---

## 사이트별 결과

### signal_bz

- **status**: LIVE_PARTIAL
- **URL**: https://www.signal.bz/
- **페이지 열림**: YES (screenshot, rendered_dom 저장)
- **목록 추출**: NO (0 items)
- **클릭-본문**: N/A
- **challenge 감지**: 없음
- **원인**: Vue.js SPA — 콘텐츠가 JavaScript 비동기 로드. `wait_until="networkidle"` 이후에도 DOM에 키워드가 없음.
- **selector 리스크**: `.rank-list li a`, `ol li a` 모두 미매치 (Vue 컴포넌트 렌더링 전)
- **next_action**: wait_for_selector 또는 API 엔드포인트 탐색

### google_trending_now

- **status**: LIVE_SUCCESS
- **URL**: https://trends.google.com/trending?geo=KR
- **페이지 열림**: YES
- **목록 추출**: YES (10 items)
- **클릭-본문**: N/A (click_target 없음)
- **challenge 감지**: 없음
- **수집 키워드**: 배우, 투표, 젠슨 황, mc몽, 이재명, 김희철, 멋진 신세계, 박민식, 임태희, 기부
- **artifact**: screenshot + rendered_dom + raw_signal
- **selector**: `td.col-1` 성공
- **next_action**: integrate_into_pipeline

### google_trends_explore

- **status**: LIVE_PARTIAL
- **URL**: https://trends.google.com/trends/explore?q=삼성전자&geo=KR
- **페이지 열림**: YES (screenshot, rendered_dom 저장)
- **목록 추출**: NO (0 items)
- **challenge 감지**: 없음
- **원인**: 동적 UI — related queries 영역이 JavaScript로 비동기 로드
- **selector 리스크**: `.fe-related-queries-item` 미매치
- **next_action**: DEFERRED — 동적 UI 복잡성으로 이번 라운드 PARTIAL

### dcinside

- **status**: LIVE_SUCCESS
- **URL**: https://gall.dcinside.com/board/lists/?id=stock_new1
- **페이지 열림**: YES
- **목록 추출**: YES (3 items)
- **클릭-본문**: FAILED — 링크가 `href="javascript:;"` 형태 (SPA 네비게이션)
- **challenge 감지**: 없음
- **artifact**: screenshot + rendered_dom + raw_signal (게시글 목록 3개)
- **next_action**: 클릭-본문은 Playwright 네비게이션 대신 직접 URL 구성 방식으로 수정 필요

### fmkorea

- **status**: LIVE_PARTIAL
- **URL**: https://www.fmkorea.com/index.php?mid=stock
- **페이지 열림**: YES (screenshot, rendered_dom 저장)
- **목록 추출**: NO (0 items)
- **challenge 감지**: 없음
- **원인**: `mid=stock` 페이지 구조 변경 — `.li_best .title a` 셀렉터 미매치
- **selector 리스크**: CSS 클래스명 변경됨
- **next_action**: DOM 검사 후 셀렉터 갱신 필요

---

## 요약

| site_id | 열림 | 목록 | 클릭 | 본문 | screenshot | DOM | raw_signal |
|---|---|---|---|---|---|---|---|
| signal_bz | YES | NO | N/A | N/A | YES | YES | NO |
| google_trending_now | YES | YES(10) | N/A | N/A | YES | YES | YES |
| google_trends_explore | YES | NO | N/A | N/A | YES | YES | NO |
| dcinside | YES | YES(3) | FAIL | NO | YES | YES | YES |
| fmkorea | YES | NO | N/A | N/A | YES | YES | NO |
| krx_kind | — | — | — | — | — | — | — | DEFERRED |
| eu_press_corner | — | — | — | — | — | — | — | DEFERRED |

---

## 컴플라이언스

- login/CAPTCHA/paywall/bot-protection 우회 시도 없음
- 모든 challenge-free 페이지만 수집
- honest UA: `event-intelligence/0.7 (+ei)`
- Playwright rate limit: 2초 최소 간격 (`_MIN_DELAY_SEC = 2.0`)
