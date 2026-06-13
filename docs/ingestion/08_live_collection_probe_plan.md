# 08 Live Collection Probe Plan

## 목적

dry-run(키 존재 확인) 단계를 넘어 **실제 데이터가 들어오는가**를 증명하는 라운드.
pipeline 확장이 아닌 **수집 가능성 실증**이 목표.

---

## 이번 라운드 live 호출 대상 (P0/P1)

### P0 API — 즉시 실호출 (키 보유 또는 키 불필요)

| service_id | auth | layer | 키 보유 여부 |
|---|---|---|---|
| naver_news_search | header_x_naver | search_enrichment | 확인 필요 |
| naver_blog_search | header_x_naver | search_enrichment | 확인 필요 |
| youtube | query_param_key | community_signal | 확인 필요 |
| opendart | query_param_crtfc_key | official_evidence | 확인 필요 |
| eia | query_param_api_key | official_evidence | 확인 필요 |
| product_hunt | bearer_token | community_signal | 확인 필요 |
| gdelt | none | official_evidence | 불필요 |
| sec_edgar | none | official_evidence | 불필요 |
| federal_register | none | official_evidence | 불필요 |
| hacker_news | none | community_signal | 불필요 |
| bok_ecos | query_param_apiKey (path) | official_evidence | 확인 필요 |

### P1 API — --all-safe 실행 (키 없으면 MISSING_KEY 기록)

`--all-safe` 플래그로 전체 registry 스캔. 키 미보유 시 MISSING_KEY로 기록하고 다음 단계 안내.

---

## Playwright 확인 대상

| site_id | 목적 | 예상 난이도 |
|---|---|---|
| signal_bz | 한국 실시간 검색어 (비공식) | 보통 |
| google_trending_now | Google 급상승 검색어 (공식, 비정형) | 높음 |
| google_trends_explore | Google Trends 탐색 (동적 UI) | 높음 |
| dcinside | 커뮤니티 게시글 목록 + 본문 클릭 | 보통 (CF 리스크) |
| fmkorea | 커뮤니티 게시글 목록 + 본문 클릭 | 보통 (CF 리스크) |

---

## fast_signal 후보 실증 (Signal.bz / Google Trends)

- **signal_bz**: `official=false`, `evidence_level=low`. 공개 페이지 1회 렌더링 시도.
  - challenge 감지 시 즉시 BLOCKED 기록. 우회 코드 없음.
- **google_trending_now**: `official=true`, `evidence_level=low_to_medium`. 공식 페이지이나 비정형 HTML.
  - JS 렌더링 필요. region=KR 파라미터 사용.
- **google_trends_explore**: 동적 UI. PARTIAL/DEFERRED 예상.

---

## 커뮤니티 클릭-본문 루프

- **HackerNews**: 공개 Firebase API로 API probe에서 처리
- **Reddit**: 공개 `.json` 엔드포인트로 API probe 처리
- **dcinside / fmkorea**: Playwright probe에서 목록 → 클릭 → 본문 추출

---

## DEFERRED 대상

| source | 이유 |
|---|---|
| krx_kind | spec 등재, JS 렌더링 복잡 → 다음 라운드 |
| eu_press_corner | spec 등재, JS 렌더링 필요 → 다음 라운드 |
| Reddit OAuth | OAuth 필요 endpoint |
| X | LOGIN_WALL |
| Blind | LOGIN_WALL |
| Reuters | LICENSE_REQUIRED |
| Google Trends Explore | 동적 UI 복잡 시 PARTIAL/DEFERRED |
| 키 미발급 P1 소스 | serper/tavily/finnhub/tmdb 등 → MISSING_KEY 기록 |

---

## 보안·쿼터·차단 리스크

| 항목 | 조치 |
|---|---|
| API 키 노출 | 응답 본문만 artifact 저장. 요청 URL/헤더 미저장 |
| Rate limit | max-calls=1 엄수. Playwright 2s 최소 간격 |
| Challenge 감지 | 즉시 중단 → BLOCKED. 우회 코드 없음 |
| X/Blind/Reuters | 시도 안 함 |
| honest UA | event-intelligence/0.7 (+ei) |

---

## 결과 라벨 정의

| 라벨 | 의미 |
|---|---|
| LIVE_SUCCESS | 실제 데이터 수신 + artifact 저장 성공 |
| LIVE_PARTIAL | 응답 받았으나 유의미 필드 추출 부분적 |
| MISSING_KEY | 키 없어서 시도 불가 |
| INVALID_KEY | 키 있으나 인증 실패 |
| PERMISSION_DENIED | 권한 없음 (403) |
| RATE_LIMITED | 쿼터 초과 (429) |
| QUOTA_EXHAUSTED | 일일 한도 소진 |
| PLAN_RESTRICTED | 현재 플랜에서 접근 불가 |
| PARSE_ERROR | 응답 받았으나 파싱 실패 |
| NETWORK_ERROR | 네트워크 오류 |
| TIMEOUT | 응답 시간 초과 |
| BLOCKED | CAPTCHA/login/bot-protection 감지 |
| DEFERRED | 이번 라운드 미실행 (spec만 등재) |
| UNKNOWN | 분류 불가 |

---

## Agent Orchestration 연결 예정

이번 라운드 종료 후 `docs/ingestion/12_agent_orchestration_probe_interface.md`에서
`run_api_live_probe()` / `run_playwright_probe()` 입출력 계약 확정.
