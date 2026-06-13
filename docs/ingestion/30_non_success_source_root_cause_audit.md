# 30 — Non-Success Source Root Cause Audit

**대상**: MISSING_KEY / LIVE_PARTIAL / DEFERRED / BLOCKED / FAILED / UNKNOWN 전체  
**원칙**: 원인 분해까지. 우회 금지. reddit/x/blind/reuters는 MVP 보류 유지.

---

## 1. BLOCKED (4개)

### fmkorea
- **상태**: BLOCKED_BOT_PROTECTION
- **원인**: Cloudflare Turnstile bot challenge. playwright_probe_sites.yaml `deferred: true`.
- **확인**: raw_payload/fmkorea는 메인 페이지(74KB) httpx 수집. 스톡 게시판(`/index.php?mid=stock`)은 playwright 접근 시 Turnstile iframe 삽입.
- **보류 사유**: Turnstile 우회는 서비스 약관 위반, 기술적으로도 현재 스택으로 불가.
- **향후 연결 방식**: 공식 API 또는 Turnstile 제거 시 playwright selector 재시도. MVP 이후 P3.

### x (Twitter)
- **상태**: BLOCKED_LOGIN_WALL
- **원인**: 2023년 이후 로그인 없이 트윗 내용 접근 불가. API v2는 Basic($100/월) 이상 유료.
- **보류 사유**: 로그인 자동화 금지. OAuth 유료 플랜 미계약.
- **향후 연결 방식**: Twitter API v2 Basic 계약 후 Bearer token 인증. MVP 이후 P2.

### blind
- **상태**: BLOCKED_LOGIN_WALL
- **원인**: 직장인 인증 필요. 공개 API 없음.
- **보류 사유**: 로그인 자동화 금지.
- **향후 연결 방식**: Blind 공식 파트너십 협의 필요. MVP 이후 P3.

### reuters
- **상태**: BLOCKED_BOT_PROTECTION
- **원인**: reuters.com은 Cloudflare 봇 보호 + 일부 기사 페이월.
- **보류 사유**: 봇 차단 우회 금지.
- **향후 연결 방식**: Reuters Connect API (유료 라이선스). MVP 이후 P2.

---

## 2. DEFERRED (1개)

### krx_kind
- **상태**: DEFERRED_SERVER_ERROR
- **원인**: `kind.krx.co.kr/disclosure/todaydisclosure.do` 이전 실행 시 서버 오류 반환. JS 렌더링 필요.
- **playwright_probe_sites.yaml**: `deferred: true`, `deferred_reason: SERVER_ERROR`
- **재시도 조건**: 다음 라운드에서 playwright runner로 재접근. 서버 안정 시 `table.list tbody tr td.col-1 a` selector.
- **향후 연결 방식**: playwright 안정화 후 종목별 공시 테이블 수집.

---

## 3. MISSING_KEY (3개)

### google_programmable_search
- **상태**: MISSING_KEY (키 이름 불일치)
- **원인**: `.env`에 `GOOGLE_API_KEY`와 `CSE_CX`가 있으나 connectivity config는 `GOOGLE_CUSTOM_SEARCH_API_KEY`와 `GOOGLE_CUSTOM_SEARCH_CX`를 요구.
- **수정 방향**: env_loader._ALIASES에 `GOOGLE_CUSTOM_SEARCH_API_KEY → GOOGLE_API_KEY`, `GOOGLE_CUSTOM_SEARCH_CX → CSE_CX` 추가, 또는 connectivity config 키 이름 변경. Phase 4 P1.

### kma (기상청)
- **상태**: MISSING_KEY (invalid key → 401)
- **원인**: `KMA_API_KEY` 존재하나 서버 응답 401 "유효한 인증키가 아닙니다". 키 형식/등록 문제.
- **수정 방향**: data.go.kr에서 기상청 API 키 재발급 또는 키 형식 확인 (일부 공공데이터 키는 URL 인코딩 필요).

### igdb
- **상태**: MISSING_KEY (OAuth bearer 미구현)
- **원인**: IGDB는 Twitch OAuth를 통해 bearer token을 먼저 발급받아야 함. `IGDB_CLIENT_ID` + `IGDB_CLIENT_SECRET`은 존재하나 token 발급 흐름 미구현.
- **수정 방향**: `https://id.twitch.tv/oauth2/token`에서 client_credentials grant로 token 발급 후 `Client-ID` + `Authorization: Bearer <token>` 헤더 전송 구현.

---

## 4. LIVE_PARTIAL (5개)

### naver_news_search
- **상태**: LIVE_PARTIAL
- **원인**: 응답 `{"total": 1, "items": []}` — items 빈 배열. query 파라미터가 올바르게 전달되지 않음.
- **수정 방향**: probe_spec extra_params에 `query: "뉴스"` (URL 인코딩된 한글) 추가. NAVER_CLIENT_ID/NAVER_CLIENT_SECRET alias가 CLIENT_ID/CLIENT_SECRET로 올바르게 동작 중.

### eu_press_corner
- **상태**: LIVE_PARTIAL
- **원인**: raw_signal에 1개 항목만 수집됨. 텍스트 콘텐츠는 "Daily news Jun 2, 2026..."로 실제 유용하나, URL 필드 비어있고 selector가 1개만 매칭.
- **수정 방향**: playwright_probe_sites.yaml eu_press_corner selector에 `ecl-content-item` 외 추가 fallback 추가. wait_after_ms 증가.

### finnhub
- **상태**: LIVE_PARTIAL
- **원인**: 응답 `{"c":0,"d":null,...}` — 모든 가격 값 0. Finnhub quote endpoint에 유효한 symbol 없이 빈 요청하거나 잘못된 심볼.
- **수정 방향**: probe_spec에 symbol=AAPL (또는 005930.KS) 추가.

### kofic (영화진흥위원회 KOBIS)
- **상태**: LIVE_PARTIAL
- **원인**: `"parameterName=targetDt,parameterValue=null"` — 필수 날짜 파라미터 누락.
- **수정 방향**: probe_spec에 `targetDt: 20260602` 추가.

### kopis (공연예술통합전산망)
- **상태**: LIVE_PARTIAL
- **원인**: `INVALID REQUEST PARAMETER ERROR` — stdate/eddate 날짜 파라미터 형식 오류 (yyyymmdd → YYYYMMDD).
- **수정 방향**: probe_spec 날짜 형식 수정. 이미 20260529/20260603으로 설정되어 있으나 API가 다른 형식 요구 가능. 공식 문서 재확인.

---

## 5. FAILED (4개)

### alpha_vantage
- **상태**: FAILED
- **원인**: `"Error Message": "This API function () does not exist."` — endpoint URL에 `function` 파라미터 누락.
- **수정 방향**: probe_spec extra_params에 `function: TIME_SERIES_DAILY, symbol: AAPL` 추가.

### tour (한국관광공사 TourAPI)
- **상태**: FAILED
- **원인**: `"Unexpected errors"` 18B — 매우 짧은 응답. serviceKey 인코딩 문제 또는 필수 파라미터 누락 (areaCode, contentTypeId 등).
- **수정 방향**: probe_spec에 필수 파라미터 추가 + serviceKey URL 인코딩 확인.

### its (국토교통부 ITS)
- **상태**: FAILED
- **원인**: `resultCode=4004, resultMsg="잘못된 URL 입니다"` — endpoint path가 올바르지 않음. ITS API는 `openapi.its.go.kr:9443/api/` 뒤에 서비스별 경로 필요.
- **수정 방향**: ITS API 문서에서 올바른 서비스 URL 확인 후 endpoint 수정.

### culture_info (문화포털)
- **상태**: FAILED
- **원인**: HTML 오류 페이지 반환. CULTURE_INFO_KEY는 존재하나 API endpoint 형식이 맞지 않거나 serviceKey 파라미터 전달 방식 문제.
- **수정 방향**: culture.go.kr 공식 API 문서 재확인. 응답이 JSON이 아닌 HTML인 경우 Accept 헤더나 responseType 파라미터 추가.

---

## 6. UNKNOWN (1개)

### loword
- **상태**: UNKNOWN (probe 기록 없음)
- **원인**: playwright_probe_sites.yaml에 미등록. source_registry에는 있으나 probe spec / service config 없음.
- **특성**: Naver+Google 트렌드 키워드 집계 사이트. 공식 API 없음.
- **수정 방향**: playwright_probe_sites.yaml에 loword spec 추가 (`https://loword.co.kr/` + `.keyword_title` 등 selector 탐색 필요).

---

## 종합 수정 우선순위

| 우선순위 | 대상 | 예상 공수 |
|---|---|---|
| P0 (이번 라운드 바로 가능) | naver_news_search query param, kofic targetDt, finnhub symbol, alpha_vantage function param | 각 5분 |
| P1 | google_programmable_search 키 alias, kopis 날짜 형식, igdb OAuth flow | 30분~1시간 |
| P2 | loword playwright spec, eu_press_corner selector 보강, kma 키 재발급 | 1~2시간 |
| P3 | tour/its endpoint 디버그, culture_info endpoint 수정, reuters/x/blind/fmkorea MVP 이후 | 별도 라운드 |
