# 11 Collection Probe 종합 보고서

> 비개발자도 이해할 수 있게 작성된 수집 가능성 검증 결과입니다.

실행일: 2026-06-03

---

## 한 줄 결론

**56개 소스 중 30개에서 실제 데이터를 수신했고, 5개는 응답은 받았지만 데이터 구조 파악이 필요하며, 5개 Playwright 사이트 중 2개(Google Trending Now, DCInside)에서 실제 콘텐츠 수집에 성공했습니다.**

---

## API 실호출 결과 (요약)

### 성공한 소스 (실제 데이터가 들어온 것들)

이 소스들은 API를 통해 실제 기사·게시글·시장 데이터가 수신된 것입니다:

- **네이버 뉴스/블로그 검색**: 키워드 "테스트"로 뉴스 3건, 블로그 3건 수신
- **유튜브**: 동영상 검색 결과 3건 수신 (youtube quota 100 units 소진)
- **연방관보 (Federal Register)**: 미국 정부 공고 3건 수신
- **해커뉴스**: 상위 500개 글 ID 수신 (공개 API)
- **The Guardian / NYT / GNews**: 영문 뉴스 기사 3건씩 수신
- **Finnhub / Alpha Vantage / Polygon**: 주식·금융 시세 데이터 수신
- **Coinbase / Binance**: 암호화폐 시세 데이터 (각 922개, 3593개 종목)
- **BBC / TechCrunch / Al Jazeera 등 RSS**: 공개 뉴스 피드 정상 수신
- **TMDB**: 영화 인기 목록 4건 수신

### 응답은 받았지만 데이터 꺼내기가 필요한 소스 (LIVE_PARTIAL)

200 응답을 받았지만 JSON 구조가 예상보다 깊게 중첩되어 있어 설정 조정이 필요합니다:

- **SEC EDGAR** (미국 증권거래위원회 공시): 응답 받음, `hits.hits[]` 중첩 구조
- **OpenDART** (한국 금융감독원 전자공시): 응답 받음, 검색 날짜 범위 조정 필요 (3영업일 이내)
- **EIA** (미국 에너지정보청): 응답 받음, `response.routes` 중첩 구조
- **Product Hunt**: GraphQL 응답 받음, `data.posts.edges` 중첩 구조
- **BOK ECOS** (한국은행 경제통계): 응답 받음, URL 키 치환 및 응답 구조 확인 필요

### 키가 없어서 시도 못 한 소스 (MISSING_KEY)

- **Google 맞춤 검색**: API 키 + 검색엔진 ID(CX) 두 가지 모두 필요
- **KOBIS (영화진흥위원회)**: API 키 미등록
- **문화포털**: API 키 미등록

### 정책상 시도 안 한 소스 (BLOCKED/DEFERRED)

- **X(트위터) / Blind**: 로그인 필요 → 이번 라운드 제외
- **Reuters**: 라이선스 검토 필요 → 이번 라운드 제외
- **KRX KIND / EU Press Corner**: 동적 JS 렌더링 복잡 → 다음 라운드

### 조치 필요 소스

- **AP News**: rsshub.app 엔드포인트가 막힘 → 공식 RSS 직접 사용 검토
- **연합뉴스(YNA)**: RSS URL 변경됨 → 갱신 필요
- **Reddit**: 공개 `.json` 엔드포인트 폐지 됨 → OAuth 필요
- **GDELT**: 속도 제한(429) → 재시도 간격 늘리기
- **Kopis / Aladin**: XML 응답 → JSON이 아닌 XML 파서 사용 필요

---

## Playwright 수집 결과 (요약)

Playwright는 일반 웹 브라우저처럼 페이지를 열어 내용을 가져오는 방식입니다.

### 성공

- **Google 급상승 검색어 (KR)**: 한국 트렌딩 키워드 10개 실제 수집
  - 수집 예시: 배우, 투표, 젠슨 황, mc몽, 이재명 등 (실시간 2026-06-03 기준)
  - screenshot/DOM/raw_signal 저장 완료

- **DCInside 주식갤러리**: 게시글 목록 3개 수집
  - 단, 게시글 본문 클릭은 JavaScript 링크 방식으로 실패 → URL 구성 방식으로 수정 필요

### 부분 성공 (페이지는 열렸지만 내용 추출 실패)

- **Signal.bz**: 페이지 열림 확인, 트렌딩 키워드는 JavaScript 비동기 로드 → 대기 방식 조정 필요
- **Google Trends Explore**: 페이지 열림 확인, 관련 검색어는 동적 UI → 설정 조정 필요
- **FM코리아**: 페이지 열림 확인, CSS 셀렉터 변경 → 갱신 필요

### 컴플라이언스

모든 사이트에서 CAPTCHA/로그인/봇 차단 우회를 시도하지 않았습니다.
Challenge가 감지되면 즉시 중단하고 BLOCKED로 기록하는 방식을 사용합니다.

---

## Agent Orchestration 연결 준비

수집 함수들이 표준 입출력을 갖춘 형태로 구현되었습니다:
- `run_api_live_probe(service_id, ...)` → `ProbeResult` 반환
- `run_playwright_probe(site_id, ...)` → `ProbeResult` 반환
- 상세 인터페이스: `docs/ingestion/12_agent_orchestration_probe_interface.md` 참조

---

## 다음 우선순위

### P0 (즉시)
1. LIVE_PARTIAL 소스 probe_spec 업데이트 (sec_edgar, eia, product_hunt 등 중첩 구조 반영)
2. EIA 기존 raw_payload 파일 삭제 (API 키 포함됨 - 사용자 직접 삭제 필요)
3. ap_news/yna 엔드포인트 갱신

### P1 (다음 라운드)
1. Reddit OAuth 인증 엔드포인트 구현
2. Signal.bz / Google Trends Explore 셀렉터 개선 (wait_for_selector)
3. kopis/aladin XML 파서 추가
4. DCInside 본문 클릭 URL 구성 방식 수정

### P2 (이후)
1. KRX KIND / EU Press Corner Playwright 구현
2. GDELT 속도 제한 재시도 로직
3. FM코리아 CSS 셀렉터 갱신
