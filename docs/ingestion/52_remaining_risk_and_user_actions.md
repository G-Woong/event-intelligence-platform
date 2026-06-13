# docs/52 — Remaining Risk and User Actions

**Date**: 2026-06-08  
**대상**: 이번 라운드 이후 남은 리스크 + 사용자 후속조치

---

## 1. 사용자 필수 후속조치

### 1.1 .env 키 이름 정리 (WARNING 수준)

현재 `.env`에 `CLIENT_ID`, `CLIENT_SECRET`이 bare key로 존재함:
- `CLIENT_ID` → `NAVER_CLIENT_ID`로 이름 변경 권고
- `CLIENT_SECRET` → `NAVER_CLIENT_SECRET`으로 이름 변경 권고

기존 alias가 존재하므로 기능은 동작 중. 정리만 필요.

### 1.2 공공 API 키 승인/재발급

| 서비스 | 필요 조치 | 사이트 |
|---|---|---|
| KMA (기상청) | apihub.kma.go.kr 계정 생성 + API 이용 승인 신청 | https://apihub.kma.go.kr |
| TourAPI v4 | 공공데이터포털 → 한국관광공사 TourAPI4.0 서비스 이용 신청. Decoding 키 사용 확인 | https://api.visitkorea.or.kr |
| ITS (국토교통부) | its.go.kr 회원가입 + API 이용 신청 + 현행 endpoint 경로 확인 | https://www.its.go.kr/opendata |
| Culture Info (문화포털) | culture.go.kr 개발자 포털에서 현행 `publicperformancedisplays/period` endpoint 재확인 | https://www.culture.go.kr/openapi |

### 1.3 미설정 키 (P2 소스 활성화용)

| 키 이름 | 서비스 | 발급 사이트 |
|---|---|---|
| KOPIS_API_KEY | 공연예술통합전산망 | https://kopis.or.kr |
| TMDB_API_KEY | TMDB | https://www.themoviedb.org/settings/api |
| ALADIN_TTB_KEY | 알라딘 Open API | https://www.aladin.co.kr/ttb |
| POLYGON_API_KEY | Polygon.io | https://polygon.io |
| SERPER_API_KEY | Serper.dev | https://serper.dev |
| TAVILY_API_KEY | Tavily | https://tavily.com |
| EXA_API_KEY | Exa | https://exa.ai |
| GNEWS_API_KEY | GNews | https://gnews.io |
| PRODUCT_HUNT_ACCESS_TOKEN | Product Hunt | https://api.producthunt.com/v2/docs |
| EIA_API_KEY | EIA (미국에너지) | https://www.eia.gov/opendata |
| BOK_ECOS_API_KEY | 한국은행 ECOS | https://ecos.bok.or.kr/api |

---

## 2. 기술적 리스크

### 2.1 loword CSS 셀렉터 취약성 (LOW)
- `span[style*="line-height: 20px"]` 셀렉터는 styled-components 인라인 스타일 기반
- 사이트 재빌드 또는 스타일 변경 시 셀렉터 무효화 가능
- **권고**: 주기적 모니터링 (월 1회). 실패 시 LIVE_PARTIAL → 셀렉터 재검증 필요
- `LOW_EVIDENCE_EXTERNAL_SIGNAL` 분류 적용 (official=false, evidence_level=low)

### 2.2 krx_kind 서버 오류 (MEDIUM)
- kind.krx.co.kr가 지속적으로 오류 페이지 반환
- 접근 방식 변경 필요: mobile UA, API endpoint, 또는 공식 데이터 포털 연동
- **권고**: KRX 전용 수집 라운드에서 공식 API 또는 다른 UA 시도

### 2.3 Google Trends 429 RATE_LIMITED (LOW)
- 현재 cooldown 1800s/600s 적용 중
- 빈번한 호출은 영구 차단 위험
- **권고**: 수집 주기를 최소 30분으로 유지. `min_interval_minutes: 120` 권고

### 2.4 공공 API serviceKey 인코딩 문제 (MEDIUM)
- tour/kma/its API는 data.go.kr 포털에서 두 가지 키 제공:
  - **Encoding 키**: URL-encoded (`%2B`, `%2F` 포함) — httpx 사용 시 이중인코딩 주의
  - **Decoding 키**: 원문 (`+`, `/` 포함) — httpx에 직접 전달 권장
- `api_probe.py`에 이중인코딩 방지 (`%` 포함 시 `unquote`) 적용 완료
- **권고**: `.env`에 Decoding 키 사용 권장

---

## 3. 다음 라운드 우선순위

### Phase A: 즉시 (공공 API 키 승인 후)
1. culture_info endpoint 재확인 + live 재검증
2. kma live 재검증 (키 승인 후)
3. tour live 재검증 (Decoding 키 + endpoint 재확인)
4. its live 재검증 (키 승인 + endpoint 재확인)

### Phase B: 다음 기능 라운드
5. event_candidate 파이프라인 (LLM/KG/RAG)
6. Celery + Redis 비동기 수집
7. krx_kind KRX 전용 수집 접근법
8. Selenium chromedriver 환경 구성

### Phase C: 장기
9. x/blind 유료 API 또는 대안 소스 검토
10. Reuters 라이선스 협의 또는 AP News로 대체

---

## 4. 보안 모니터링

- `.env` 키 노출: 현재 없음 (PASS)
- outputs 파일 기밀 키 포함: 현재 없음 (PASS)
- 정기 보안 검사: 라운드 시작 시 `check_env_hygiene` 실행
- AMBIGUOUS_ALIAS 해소: `CLIENT_ID`/`CLIENT_SECRET` → canonical name으로 변경 권고
