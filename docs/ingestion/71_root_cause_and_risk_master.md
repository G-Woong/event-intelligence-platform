# docs/71 — Root Cause & Risk Master (근본 원인 분석 + 리스크 레지스터)

**생성일**: 2026-06-12
**대체 문서**: docs/62(죽은·불안정 소스 근본 원인) + docs/65(리스크 레지스터) — 두 문서를 통합·갱신하며 폐기
**근거**: 2026-06-12 live 실측 + 코드 수정 결과. RESOLVED 표기는 이번 라운드에서 실측으로 확정·해소된 항목.

---

# Part 1 — 소스별 근본 원인 분석

## ✅ RESOLVED — 이번 라운드에서 원인 확정·해소된 소스

### KMA (기상청) — RESOLVED

**직전 기록**: HTTP 401, "키 미설정 또는 승인 미완료"로 추정 (오분류)
**실측으로 확정된 진짜 원인**: **키와 엔드포인트의 발급처 불일치.**

쉽게 설명하면: 기상청 데이터는 두 개의 서로 다른 "창구"에서 제공된다.
1. **기상청 API허브** (apihub.kma.go.kr) — 자체 회원가입으로 발급하는 `authKey` 파라미터 전용
2. **공공데이터포털** (data.go.kr) — 포털 공통 `serviceKey` 파라미터 전용

기존 코드는 ①번 창구 주소에 ②번 창구 키를 (그것도 `serviceKey` 파라미터 이름으로) 보내고 있었다. 사용자 키는 data.go.kr 발급 키였으므로 어떤 파라미터 이름을 써도 ①번 창구에서는 401("유효한 인증키가 아닙니다")이 날 수밖에 없었다. 실측 중 `authKey` 파라미터로도 401임을 확인해 키 발급처가 apihub가 아님을 확정했다.

**수정**: 엔드포인트를 data.go.kr 단기예보 초단기실황(`apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst`)으로 전환, 파라미터(base_date/base_time/nx/ny/dataType) 동기화.
**결과**: **LIVE_SUCCESS** (items 8). 키는 처음부터 유효했다.
**선택 사항**: apihub 전용 데이터(지상관측 일자료 등)가 필요해지면 apihub.kma.go.kr 회원가입 후 별도 authKey 발급 (docs/73 사용자 액션 참조).

### TourAPI (한국관광공사) — RESOLVED

**직전 기록**: HTTP 500, "키 미설정 또는 Encoding 키 사용" 추정 (오분류)
**실측으로 확정된 진짜 원인**: **구버전 엔드포인트.** `KorService1`은 폐기됐고 현행은 `KorService2`. 구버전 호출 시 서버가 500 "Unexpected errors"를 반환한다 (키 검증 단계까지 가지도 못함).
**수정**: `B551011/KorService2/areaBasedList2`로 전환 (파라미터 계약은 동일).
**결과**: **LIVE_SUCCESS** (items 3). 키 유효.

### ITS (국가교통정보센터) — RESOLVED

**직전 기록**: HTTP 401, "키 미설정 또는 포트 제한" 추정 (오분류)
**실측으로 확정된 진짜 원인**: **엔드포인트 경로 자체가 무효.** 응답 본문에 `resultCode 4004 "잘못된 URL입니다"`가 명시돼 있었다 — 401은 껍데기고 실제 메시지는 "그런 API가 없다"였다. 코드 주석에도 "endpoint path needs verification"이라고 적혀 있던 항목.
**수정**: 현행 REST 경로 `openapi.its.go.kr:9443/trafficInfo` + 필수 파라미터(type, minX/maxX/minY/maxY bbox, getType=json)로 전환.
**결과**: **LIVE_SUCCESS** (서울 도심 bbox에서 링크 교통정보 31,578건). 키 유효.

### Culture Info (문화포털) — RESOLVED

**직전 기록**: HTTP 200 + HTML 에러페이지, "키 미승인 또는 endpoint 변경" 추정
**실측으로 확정된 진짜 원인**: **구 REST 경로 폐기.** `www.culture.go.kr/openapi/rest/publicperformancedisplays/period`는 "페이지가 없거나 잘못된 경로입니다" HTML 에러페이지를 반환한다. 서비스는 한국문화정보원의 data.go.kr 게이트웨이로 이관됐다.
**수정**: `apis.data.go.kr/B553457/cultureinfo/period2`로 전환 (한눈에보는문화정보조회서비스).
**결과**: **LIVE_SUCCESS** (공연·전시 10건, XML). 키 유효.
**부속 확인**: dry-run에서 MISSING_KEY로 나오던 alias(`CULTURE_INFO_KEY`→`CULTURE_INFO_API_KEY`) 문제는 현행 `env_status()`가 alias를 정상 해석함을 확인 — **과거 artifact가 alias 추가 이전 기록**이었던 것. 현재 dry-run은 KEY_PRESENT_DRY_RUN.

### serper / tavily / exa — RESOLVED (키 충돌 해소)

**직전 기록**: 06-03 KEY_PRESENT vs 06-08 MISSING_KEY 문서 간 충돌 → UNKNOWN
**실측 결과**: 3개 모두 http 200 + 결과 3건씩 **LIVE_SUCCESS**. `.env`에 키가 정확한 이름으로 존재하며 유효하다. 06-08 MISSING_KEY 기록은 registry의 정적 `status` 필드가 낡았던 것(stale)이지 실제 키 부재가 아니었다.

### 키 미검증 12개 (newsapi, gnews, guardian, nyt, finnhub, twelve_data, alpha_vantage, polygon, kopis, tmdb, aladin, igdb) — RESOLVED

전부 실측 LIVE_SUCCESS. registry의 MISSING_KEY는 모두 stale 필드였다. igdb는 Twitch OAuth client_credentials 흐름까지 정상 동작 확인.

---

## ⛔ 여전히 차단·보류 상태인 소스 (변동 없음)

### FMKorea — MVP_EXCLUDED (우회 금지)
Cloudflare Turnstile(2세대 봇 챌린지)이 자동화 브라우저를 정확히 탐지. httpx/Playwright/Selenium 전부 차단. **본 시스템 원칙상 challenge solving(CAPTCHA 우회)을 시도하지 않는다.** 대체 소스: dcinside, naver_news_search, signal_bz.

### X (Twitter) — MVP_EXCLUDED
2023년 이후 API 전면 유료화(읽기는 Basic $100+/월), 웹은 로그인 필수. 유료 구독 결정은 사용자 몫 (docs/73).

### Blind — MVP_EXCLUDED
직장 이메일 인증 로그인 필수. 공식 API 없음. 인증 우회 금지.

### Reuters — MVP_EXCLUDED
봇 차단 + Thomson Reuters 재배포 라이선스 제약. AP News(CORE_READY)가 동급 대안.

### KRX KIND — DEFERRED_SPECIAL_ROUND
kind.krx.co.kr가 자동화 접근에 1.3KB 서버 오류 페이지만 반환(XHR 0건). 브라우저 전략 변경으로 해결 불가 — 웹 인터페이스가 아닌 `open.krx.co.kr` 공식 OpenAPI로 전환해야 한다. **키 발급은 사용자 액션** (docs/73).

### Google Programmable Search — MVP_EXCLUDED (코드 보존)
`GOOGLE_CUSTOM_SEARCH_CX`(검색 엔진 ID) 미설정으로 400. CX는 Google 콘솔에서 Custom Search Engine을 만들어야 발급된다. serper/tavily/exa가 정상 동작하므로 우선순위 낮음.

### Reddit — MVP_DEFERRED (이번 라운드 사용자 확정)
public `.json`은 동작하지만 비로그인 rate_limit 변동성이 커서 MVP 수집 셋에서 보류. 코드는 보존, 재평가 시 OAuth 전환 검토.

### Google Trends Explore — READY_WITH_CAUTION (실패 아님)
429 RATE_LIMITED는 쿨다운 대기 신호일 뿐. `min_interval 1800s` + `cooldown 600s` 정책으로 운영. 멀티워커 보호는 RISK-T02(Redis 캐시)에 달려 있음 — plans/012로 이관.

---

# Part 2 — 리스크 레지스터 (2026-06-12 갱신)

| severity | 정의 |
|----------|------|
| **HIGH** | 운영 시 데이터 손실·보안 사고·법무 이슈 발생 가능 |
| **MEDIUM** | 수집 품질 저하 또는 특정 기능 비활성화 |
| **LOW** | 모니터링 필요, 즉각 조치 불필요 |

## ✅ 이번 라운드에 해소된 리스크

### RISK-T01: 기본 budget=3으로 Playwright 미도달 — **RESOLVED**
- **해소 방법**: `retry_policy.yaml`에 `per_source:` 섹션 신설 + `RetryPolicy.budget_for(source_id)` + `strategy_runner`가 source_id로 budget 조회.
- 적용값: krx_kind/eu_press_corner = 8, dcinside/fmkorea = 6, 전역 기본 3 유지(기존 테스트 호환).
- 검증: 신규 단위 테스트 10개 (`ingestion/tests/unit/test_per_source_budget.py`) 포함 359개 전체 통과.

### RISK-A01: serper/tavily/exa 키 상태 충돌 — **RESOLVED**
- 실측 LIVE_SUCCESS 3/3. registry status 갱신 완료.

### RISK-Q02: 공공데이터 API 오류 — **RESOLVED (원인 재분류)**
- 원인은 "Encoding/Decoding 키 문제"가 아니라 **전부 엔드포인트·파라미터 불일치**였다 (Part 1 참조). 4개 소스 코드 수정 후 LIVE_SUCCESS.
- 이중 인코딩 방지 로직(`api_probe.py`의 `%` 감지 unquote)은 그대로 유효한 방어선으로 유지.

### RISK-X01: requirements.txt / lock 불일치 — **RESOLVED**
- 검증 결과 불일치 없음 (lock이 상위집합, 핵심 패키지 버전 일치).

## ➡ plans/012로 이관된 리스크 (설계 완료, 구현 대기)

### RISK-T02: rate_limit 캐시 프로세스 로컬 (워커 간 미공유) — **부분 해소 (06-12 risk closure 라운드)**
- ✅ store pluggable화 완료: `RateLimitStore` ABC + InMemory/LocalPersistent/Redis 3종
  (`ingestion/core/rate_limit_store.py`, docs/75). 429 cooldown deadline 영속화
  (`record_rate_limited`/`in_cooldown`) + 재기동 생존 스모크 PASS.
- 잔여(plans/012): Redis 실인스턴스 연동·멀티워커 동시성 검증. `RedisRateLimitStore`는
  plans/012 §3 키 계약(`rate_limit:{source_id}:{query_hash}`)으로 이미 구현돼 있어 연결만 남음.

### RISK-O01: Celery+Redis 주기 수집 미도입 — **이관**
- plans/012 §2 (소스 계층별 beat schedule 설계).

### RISK-F01: 장애 소스 자동 격리 없음 — **해소 (06-12 risk closure 라운드)**
- ✅ `SourceHealthState` 6상태 전이 모델 + quarantine(누적 3회) + BLOCKED_TERMINAL 즉시 격리
  + collection_probe health gate (`ingestion/core/source_health.py`, docs/76).
- 잔여(plans/012): `list_due_for_retry()` 소비자(Celery 재점검 스케줄)만 남음.

## 유지되는 리스크 (변동 없음 또는 부분 갱신)

### RISK-A02: .env 키 이름 불일치 (legacy alias) — LOW (탐지 일반화 완료)
- hygiene 도구가 `_ALIASES` 전체로 일반화됨 (06-12, docs/82). 실측 AMBIGUOUS_ALIAS 6건
  (CLIENT_ID/CLIENT_SECRET/ECOS_API_KEY/GOOGLE_API_KEY/CSE_CX/CULTURE_INFO_KEY) —
  **기능에는 영향 없음** (alias 자동 해석). ALIAS_VALUE_MISMATCH 0건.
  **사용자 액션** (docs/82 §4 마이그레이션 가이드): canonical 키로 개명 (선택).

### RISK-R01: Google Trends IP 차단 위험 — **해소 (06-12 risk closure 라운드)**
- ✅ min_interval 7200s(120분) + cooldown 3600s 상향, 429 deadline 영속화, Route 2 429
  감지 추가 (docs/79). 1회 검증: RATE_LIMITED + next_retry_at 디스크 영속 확인 (docs/83 §4).
- 멀티워커 보호는 RISK-T02 잔여(plans/012 Redis 연동)와 함께 완성.

### RISK-R02: NewsAPI 일 100건 무료 상한 — LOW
- 일일 누적 카운터 없음. plans/012 스케줄러 설계에서 daily quota guard로 흡수.

### RISK-R03: NYT 상업 라이선스 — HIGH (상업 서비스 시)
- 출시 전 법무 검토 필요. 실측 성공과 무관하게 약관 리스크 유지.

### RISK-P01 / RISK-D01: Docker에 Chrome/Chromium 미설치 — HIGH (배포 시)
- Playwright 소스(eu_press_corner, signal_bz, loword, dcinside) 컨테이너 수집 불가. 배포용 이미지에 `playwright install chromium` 또는 Chrome 설치 필요. plans/012 §7 전제조건에 포함.

### RISK-P02: Playwright 지문 감지 — MEDIUM
- dcinside 등 차단 강화 가능성. 차단 발생 시 stealth 계열 도구 검토 (현재는 미적용).

### RISK-L01: 뉴스 콘텐츠 저작권 — HIGH (상업 서비스 시) → **운영 정책화 완료**
- publication boundary 정책 수립 (06-12, docs/80): 전문 게시 금지·프리뷰 200자·출처/원문
  링크 필수·raw artifact internal_only (`publication_policy.yaml` + 코드 가드).
- 잔여: 게시 계층 구현 시 가드 연결 + 출시 전 법무 검토 (약관 정밀 확인).

### RISK-L02: Aladin 비상업 제한 — MEDIUM
- 이번 실측으로 키는 동작 확인. 상업 서비스 전 알라딘 계약 검토 필요.

### RISK-C01: 유료 API 예산 — MEDIUM
- X($100+/월), NYT, Guardian 과금 구간. 무료 티어 우선 정책 유지.

### RISK-S01: outputs/ 실키 유출 가능성 — **해소 (06-12 risk closure 라운드)**
- ✅ scan 자동화 구현: `ingestion/tools/scan_secrets.py` 2계층 탐지 (패턴 WARNING /
  .env 실값 일치 BLOCKED, 키 NAME만 리포트), exit code 게이트 (docs/81).
- baseline + 라운드 종료 스캔 PASS (710 files, 실키 0건). `_sanitize_response` 회귀 테스트
  3종 추가. pre-commit/CI 등록 방법 docs/81 §4 — 실제 hook 등록은 사용자 결정.

### RISK-S02: outputs/ 외부 노출 — MEDIUM
- 배포 시 outputs/ 경로 웹 접근 차단 확인 필요.

### RISK-Q01: Loword 셀렉터 취약성 — LOW
- styled-components 인라인 스타일 셀렉터. 월 1회 probe 검증.

### RISK-Q03: google_trends_explore registry 미등록 — LOW
- playwright_probe_sites.yaml에만 존재. 다음 registry 정비 시 항목 추가.

### RISK-T03: jsonl 스테일 데이터 — LOW
- 이번 라운드 결과는 `api_live_probe_round_a.jsonl` / `round_b.jsonl`로 분리 저장해 라운드 구분 명확화. 과거 파일 혼재는 여전 — 라운드별 서브디렉터리 분리 검토.

### RISK-X02: _PLAYWRIGHT_FIRST_SOURCES 수동 관리 — LOW
- YAML(deferred:false) 등록 우선 원칙 주석 보강 권장.

---

## 리스크 우선순위 요약 (갱신)

| 우선순위 | risk_id | 내용 | 상태/해결 경로 |
|---------|---------|------|---------------|
| ~~P0~~ | ~~RISK-T01~~ | ~~budget=3 playwright 미도달~~ | **RESOLVED (per-source budget 구현)** |
| ~~P1~~ | ~~RISK-A01~~ | ~~serper/tavily/exa 키 불명~~ | **RESOLVED (실측 LIVE_SUCCESS)** |
| ~~P1~~ | ~~RISK-Q02~~ | ~~공공 API 4개 실패~~ | **RESOLVED (엔드포인트 수정)** |
| ~~P2~~ | ~~RISK-X01~~ | ~~requirements 불일치~~ | **RESOLVED (불일치 없음 확인)** |
| ~~P0~~ | ~~RISK-T02~~ | ~~rate_limit 캐시 휘발~~ | **부분 해소** (store pluggable+local persistent, docs/75) — Redis 연동만 plans/012 |
| P0 | RISK-O01 | 주기 수집 없음 | plans/012 §2 (Celery beat 설계 완료) |
| P0 | RISK-D01/P01 | Docker Chrome 없음 | runtime check 러너 + Docker 전제 문서화 완료 (docs/77) — 실제 이미지 빌드는 plans/012 §7 |
| ~~P1~~ | ~~RISK-F01~~ | ~~장애 소스 자동 격리 없음~~ | **해소** (health/quarantine, docs/76) |
| P2 | RISK-L01 | 뉴스 저작권 | **운영 정책화 완료** (docs/80) — 출시 전 법무 검토 잔여 |
| ~~P2~~ | ~~RISK-R01~~ | ~~Google Trends IP 차단~~ | **해소** (120분 간격+영속 cooldown, docs/79) |
| ~~P1~~ | ~~RISK-S01~~ | ~~outputs/ 실키 유출~~ | **해소** (scan 자동화, docs/81) |
| P3 | RISK-A02 | .env 키 이름 | 탐지 일반화 완료 (docs/82) — 개명은 사용자 액션 |
| P3 | RISK-Q01/Q03/T03/X02 | 모니터링성 항목 | 정기 점검 |

---

## 2026-06-13 추가 — Live Collection Audit 라운드 신규 리스크 (docs/85~93)

| 우선순위 | ID | 리스크 | 상태/조치 |
|------|------|--------|----------|
| **P1** | RISK-T04 | **Route 1(API) 429 시 cooldown 미기록** — health에 RATE_LIMITED_COOLDOWN이 남지만 next_retry_at이 비어 should_skip 미작동, rate_limit store `record_rate_limited`도 미호출 (playwright 경로만 기록). 이번엔 gdelt cache ttl(900s)이 대신 차단 (docs/90 §3 실측) | 미해소 — plans/012 전 수정 권장 |
| P1 | RISK-S02 | gdelt 불안정 — 단일 호출에서도 429(1차), query 호출에서 비-JSON PARSE_ERROR + 429(2차). 실측 3호출 중 3실패 | 운영 주기 15분+ 고정 + 오류 내성 후 투입 (docs/92) |
| P2 | RISK-S03 | ap_news RSS endpoint가 HTML 에러 페이지 반환 (1차 실측) | endpoint 점검/교체 필요 |
| P2 | RISK-S04 | newsapi top-headlines+q는 0건 (2/2 실측) | `/v2/everything` 전환 (probe spec 변경) |
| P2 | RISK-S05 | fast_signal selector 취약 — loword/google_trending_now는 page title만 추출, dcinside/eu_press_corner 동일 | update_selector (signal_bz만 keyword 추출 성공) |
| P3 | RISK-Q04 | relevance 스코어러 cross-language 한계 — tmdb "군체"→"Colony" 정타 매칭을 low로 측정 | 정규화 단계 entity 매칭으로 대체 |
| P3 | RISK-Q05 | 장문 seed query(공시명 그대로) 검색 0건 | hot seed 도출 시 핵심 키워드 절단 (docs/89 §5) |

## 08/09 라운드 — 리스크 종결 (2026-06-13)

| 리스크 | 직전 상태 | 종결 |
|---|---|---|
| federal_register url/date 부재 | partial | **CLOSED** — fields[] 5필드 list |
| igdb timestamp/url 부재 | partial | **CLOSED** — apicalypse url + $root/epoch 매핑 |
| culture_info 날짜 부재 | partial | **CLOSED** — _XML_FIELD_NAMES 매핑 (구 Service Error는 과거 param, 현 endpoint LIVE_SUCCESS) |
| hacker_news detail 미설계 | no | **CLOSED** — /v0/item/{id}.json 2차 호출 |
| bok_ecos/eia/its sample 매핑 부재 | 평가 불가 | **CLOSED** — _SAMPLE_PATHS 추가 |
| 시장 수치 seed_ready=no(분류 오류) | no | **CLOSED** — numeric_signal 평가 경로(signal_ready) |
| RATE_LIMITED 신호 목록 2벌(playwright/api) | 잠재 불일치 | **CLOSED** — error_taxonomy 단일 출처(기법10) |

신규 발견: finnhub flat quote는 list 추출 0건이라 seed evaluator가 probe items_found를 무시하면 signal_ready 오판(no) → `_evaluate_seed`가 probe items_found 사용하도록 수정(이번 턴 종결, 잔존 리스크 아님).

## Trends fallback 턴 갱신 (2026-06-13)

- **google_trends_explore 429 = 외부 provider 리스크(코드 결함 아님)**: Google 공식 quota 부재. 잔존 리스크는 optional_enrichment로 한정되고 **fallback chain**(google_trending_now + 공개 RSS export + 뉴스/검색 related expansion)으로 event queue 비차단 → 리스크 등급 하향(NOT_READY → CONFIRMED_EXTERNAL, 비차단).
- 신규 리스크 없음. 수정 가능한 코드/selector/mapping 결함 0건 유지.
