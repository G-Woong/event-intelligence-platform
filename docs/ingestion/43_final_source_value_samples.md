# 43 — Final Source Value Samples

**날짜**: 2026-06-03  
**주의**: 본문 전문 복사 금지. 키 미출력. 샘플은 구조/품질 확인용.

---

## CORE_READY 소스 샘플 요약

### naver_news_search
- **status**: LIVE_SUCCESS
- **items_found**: 3
- **core_fields**: title, link, description, pubDate, originallink
- **quality**: 한국어 뉴스, structured JSON
- **probe_params**: query="테스트", display=3

### finnhub
- **status**: LIVE_SUCCESS  
- **items_found**: 1 (quote presence signal)
- **core_fields**: c(현재가), h(고가), l(저가), o(시가), pc(전일종가)
- **quality**: 실시간 미국 주식 시세, float 값
- **probe_params**: symbol=AAPL

### kofic (KOBIS 박스오피스)
- **status**: LIVE_SUCCESS
- **items_found**: 10
- **core_fields**: boxOfficeResult.dailyBoxOfficeList[].movieNm, rank, salesAmt, audiCnt
- **quality**: 일별 박스오피스 순위 10위까지, 한국영화진흥위원회 공식 데이터
- **probe_params**: targetDt=20260602

### alpha_vantage
- **status**: LIVE_SUCCESS
- **items_found**: 100 (daily entries)
- **core_fields**: Time Series (Daily) → date → open/high/low/close/volume
- **quality**: 미국 주식 일별 시계열, 최근 100일 compact
- **probe_params**: function=TIME_SERIES_DAILY, symbol=AAPL, outputsize=compact

### kopis (공연예술통합전산망)
- **status**: LIVE_SUCCESS
- **items_found**: 3
- **core_fields**: XML `<db>` entries → prfnm(공연명), fcltynm(공연장), prfpdfrom/prfpdto, genrenm
- **quality**: 공연 정보 공식 데이터
- **probe_params**: stdate=20260529, eddate=20260603, cpage=1, rows=3

### igdb (Twitch OAuth2)
- **status**: LIVE_SUCCESS
- **items_found**: 3
- **core_fields**: id, name, first_release_date, rating
- **quality**: 게임 데이터, Twitch OAuth2 client_credentials 플로우 정상 동작
- **probe_params**: Apicalypse body (POST text/plain)

### gdelt
- **status**: LIVE_SUCCESS
- **items_found**: 3
- **core_fields**: articles[].url, title, domain, seendate
- **quality**: 전세계 뉴스 아카이브, 공식 API (rate limit 5s 간격 준수)
- **probe_params**: query="samsung", mode=artlist, format=json, maxrecords=3

---

## REPAIRABLE_NEXT 소스 원인 기록

### google_programmable_search
- **status**: UNKNOWN (http=400)
- **원인**: Bad Request — CX(Search Engine ID)가 유효하지 않거나 검색엔진 미활성화
- **수정방법**: Google Cloud Console에서 Custom Search Engine 생성 후 GOOGLE_CUSTOM_SEARCH_CX 값 확인
- **코드 수정**: 완료 (cx 주입 코드, PROBE_SPEC 추가)

### kma
- **status**: INVALID_KEY (http=401)
- **원인**: 공공데이터포털(data.go.kr)에서 기상청 API 서비스 승인 필요
- **수정방법**: data.go.kr 접속 → 기상청 단기예보 서비스 신청 → 승인 후 KMA_API_KEY 갱신

### its
- **status**: INVALID_KEY (http=401)
- **원인**: ITS 국가교통정보센터 API 키 미승인 또는 만료
- **수정방법**: its.go.kr 접속 → API 키 재발급

### culture_info
- **status**: API_RETURNED_HTML_ERROR_PAGE (http=200)
- **원인**: culture.go.kr가 HTML 에러 페이지 반환 — 키 미승인 또는 만료
- **수정방법**: culture.go.kr에서 CULTURE_INFO_KEY 재발급

### tour
- **status**: NETWORK_ERROR (http=500)
- **원인**: TourAPI 서버 500 오류 — 키 문제이거나 일시적 서버 오류
- **수정방법**: data.go.kr에서 TOUR_API_KEY 재발급 및 재시도

---

## D. MVP_EXCLUDED 사유 기록

| 소스 | 사유 | 기술적 상태 |
|---|---|---|
| fmkorea | Cloudflare Turnstile bot-challenge | 기술적 우회 가능하나 ToS 위반 금지 |
| x (Twitter) | Bearer token 유료 + login_required | 운영 결정으로 제외 |
| blind | 직장인 실명 인증 필요 | 로그인 없이 접근 불가능 |
| reuters | 라이선스 검토 필요 | 운영/법적 결정 후 재검토 |

> **중요**: 위 소스들은 "기술 실패"가 아니라 운영/약관/라이선스 제약으로 MVP 제외.
> 기술적 역량이 확보되더라도 약관 위반 없이 사용할 수 없음.
