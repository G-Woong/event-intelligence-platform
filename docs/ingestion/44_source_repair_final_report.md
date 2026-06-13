# 44 — Source Repair Final Report (비개발자용)

**날짜**: 2026-06-03  
**대상 독자**: 비개발자, 프로젝트 관리자, 의사결정자

---

## 1. 이번 라운드 목적

56개 데이터 소스 중 아직 "정상 작동 확인"이 되지 않은 소스들을 끝까지 수리하고,  
수리가 불가능한 소스는 이유를 명확히 기록하여 **Source Stabilization 단계를 공식 종료**하는 것.

---

## 2. 출발점: 무엇이 문제였나

이전 검증에서 발견된 핵심 결함 5가지:

1. **"HTTP 200 응답 = 성공"의 함정**: API가 성공 코드(200)를 보내도 실제 데이터가 없는 경우를 감지하지 못함
2. **파라미터 누락**: 7개 소스에서 필수 API 파라미터 없이 호출하고 있었음
3. **구글 검색 키 2개 중 1개 누락**: Google CSE는 API 키와 검색엔진 ID 2개가 모두 필요한데 1개만 전달됨
4. **IGDB 게임 DB 인증 미구현**: 단순 키가 아니라 Twitch OAuth2 토큰 교환이 필요한데 코드 없음
5. **XML 오류 페이지 미탐지**: 한국 공공 API들이 XML 형식으로 오류를 보내도 성공으로 오판

---

## 3. 이번 라운드에서 한 일

### 3.1 오류 분류 체계 강화

8가지 새 오류 유형 추가 (26→34개):
- `PARAMETER_MISSING`: 필수 파라미터 누락
- `QUERY_ENCODING_OR_PARAM_ERROR`: 검색어 인코딩 또는 파라미터 문제 (나버 빈 results 탐지)
- `INVALID_SYMBOL_OR_EMPTY_MARKET_DATA`: 잘못된 주식 심볼 또는 시세 데이터 없음
- `XML_PARAMETER_ERROR`: XML API의 오류 응답 탐지
- `API_RETURNED_HTML_ERROR_PAGE`: JSON/XML 요청인데 HTML 오류 페이지 반환
- `INVALID_KEY`: 401 인증 실패 (키 무효/만료)
- `ENDPOINT_INVALID`: 잘못된 API 주소
- `DYNAMIC_RENDER_REQUIRED`: 자바스크립트 렌더링 필요

### 3.2 P0 소스 수리 완료 (5개)

| 소스 | 문제 | 결과 |
|---|---|---|
| 네이버 뉴스 검색 | "total=5이면 5개 있다"는 오탐 | **LIVE_SUCCESS** (items=3) |
| Finnhub (미국 주가) | 파라미터 누락 + float 처리 오류 | **LIVE_SUCCESS** (items=1) |
| KOBIS 박스오피스 | 날짜 파라미터 누락 | **LIVE_SUCCESS** (items=10) |
| Alpha Vantage | function 파라미터 누락 | **LIVE_SUCCESS** (items=100) |
| IGDB (게임 데이터) | Twitch OAuth2 미구현 | **LIVE_SUCCESS** (items=3) |

### 3.3 P1 소스 수리

| 소스 | 조치 | 결과 |
|---|---|---|
| KOPIS (공연정보) | cpage 파라미터 추가 + XML 오류 탐지 | **LIVE_SUCCESS** (items=3) |
| Google CSE | CX(검색엔진ID) 주입 코드 추가 | 400 Bad Request — CX 값 확인 필요 |
| EU Press Corner | Playwright 셀렉터 5개 추가, 대기시간 증가 | 셀렉터 보강 완료, live 테스트 필요 |
| loword | Playwright 스펙 신규 작성 | 스펙 추가, DOM 검증 필요 |
| GDELT | 기존 rate-limit 정책 적용 확인 | **LIVE_SUCCESS** (items=3) |

### 3.4 P2 한국 공공 API 원인 분석

| 소스 | HTTP 응답 | 원인 | 조치 필요 |
|---|---|---|---|
| 기상청 KMA | 401 | 공공데이터포털 서비스 승인 대기 | 포털에서 승인 신청 |
| ITS 교통정보 | 401 | 키 재발급 필요 | its.go.kr 재발급 |
| 한국관광공사 TourAPI | 500 | 서버 오류 또는 키 문제 | 키 재발급 후 재시도 |
| 문화포털 | HTML 200 | 키 미승인 또는 만료 | culture.go.kr 재발급 |

---

## 4. "수리 불가" 소스 확정 (MVP 제외)

다음 4개 소스는 **기술 실패가 아니라 운영/약관/라이선스 제약**으로 이번 MVP에서 제외합니다:

| 소스 | 제외 이유 |
|---|---|
| FM코리아 | Cloudflare 봇 방어 (법적으로 우회 불가) |
| X (구 Twitter) | 유료 API + 계정 인증 필요 |
| 블라인드 | 직장인 실명 인증 없이 접근 불가 |
| 로이터 | 라이선스 검토 필요 |

---

## 5. 최종 소스 분류 현황

| 분류 | 소스 수 | 의미 |
|---|---|---|
| 즉시 사용 가능 (CORE_READY) | **34개** | 파이프라인 연결 준비 완료 |
| 주의 조건부 사용 (READY_WITH_CAUTION) | **10개** | 약관/쿼터 검토 후 사용 |
| 다음 라운드 수리 (REPAIRABLE_NEXT) | **9개** | 키 재발급/서버 재시도 필요 |
| MVP 제외 확정 (MVP_EXCLUDED) | **4개** | 운영/법적 이유로 제외 |

---

## 6. 코드 품질

- 기존 테스트 319개 전부 통과 (회귀 없음)
- 신규 테스트 9개 추가
- 보안 검사: 실키 미노출 확인

---

## 7. 다음 단계 권장사항

1. **키 재발급** (C 그룹): 공공데이터포털, its.go.kr, culture.go.kr에서 키 갱신
2. **Google CSE 검색엔진 활성화**: Google Cloud Console에서 CX 값 확인
3. **Playwright live 테스트**: eu_press_corner, loword, krx_kind, google_trends_explore
4. **Pipeline 연결**: A 그룹 34개 소스부터 event_candidate 추출 단계로 진행

---

## 종료 선언

**Source Stabilization 단계 종료 상태**: **B — mostly closed**

- A: CORE_READY 34개 확정, 기반 코드 완성 → **closed**
- B: C 그룹 9개 키 재발급 + Playwright live 테스트 → mostly closed
- C: 완전한 종료를 위해 C 그룹 수리 후 재선언 권장

다음 주 작업: event_candidate/LLM/KG/GraphRAG/Celery 단계로 진행 가능.  
C 그룹 소스들은 병렬로 키 재발급 진행하면서 파이프라인 개발 시작 가능.
