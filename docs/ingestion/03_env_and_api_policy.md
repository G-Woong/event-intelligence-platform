# 03 — Env & API Policy

> 보안 원칙: 이 문서에 키 값·토큰·실제 자격증명을 절대 기재하지 않는다.
> 발급 URL, 플랜 요약, 쿼터, 인증 방식, 대표 에러코드, 최소 테스트 엔드포인트만 기재.
> 불확실한 항목은 `UNKNOWN`으로 표시.

---

## 1. env 키 카테고리 분류

### 1-A. 기존 플랫폼 키 (STEP 001-011, 변경 없음)
```
LANGSMITH_TRACING / LANGSMITH_ENDPOINT / LANGSMITH_API_KEY / LANGSMITH_PROJECT
OPENAI_API_KEY
MILVUS_HOST / MILVUS_PORT / MILVUS_COLLECTION
REDIS_URL
DATABASE_URL
LLM_PROVIDER / LLM_MODEL / LLM_TIMEOUT_SEC / LLM_MAX_TOKENS / LLM_TEMPERATURE
EMBEDDING_PROVIDER / EMBEDDING_MODEL / EMBEDDING_DIM / EMBEDDING_TIMEOUT_SEC
RSS_COLLECTOR_FETCH_TIMEOUT_SEC / RSS_SOURCES_CONFIG_PATH / RSS_COLLECTOR_USER_AGENT / RUN_RSS_LIVE_SMOKE
RUN_LANGSMITH_SMOKE / ADMIN_API_TOKEN / BACKEND_INTERNAL_URL / ...
```

### 1-B. Ingestion 소스 API 키 (신규)

| 환경변수 | 소스 | 필수 여부 |
|---|---|---|
| `NAVER_CLIENT_ID` | NaverBlogSearch, NaverNewsSearch | 필수 (alias: `CLIENT_ID`) |
| `NAVER_CLIENT_SECRET` | NaverBlogSearch, NaverNewsSearch | 필수 (alias: `CLIENT_SECRET`) |
| `YOUTUBE_API_KEY` | YouTube | 필수 |
| `PRODUCT_HUNT_API_KEY` | ProductHunt | 필수 |
| `OPENDART_API_KEY` | OpenDart | 필수 |
| `BOK_ECOS_API_KEY` | BOK ECOS | 필수 (alias: `ECOS_API_KEY`) |
| `EIA_API_KEY` | EIA | 필수 |
| `GOOGLE_APPLICATION_CREDENTIALS` | GCP 서비스 (선택적) | 선택 — 경로만 검사 |

### 1-C. 인증 불필요 소스 (키 없음)
BBC, AP News, TechCrunch, The Verge, ZDNet Korea, ETNews, YNA, Hankyung, Maekyung,
AlJazeera, CNBC, Reddit (public .json), HackerNews, DCInside, FMKorea, GDELT, SEC EDGAR,
Federal Register, EU Press Corner

### 1-D. 후순위 제외 소스 (Round 1 미구현)

| 소스 | 제외 사유 |
|---|---|
| X (Twitter) | 공개 타임라인 접근 불가; bearer token or login 필요 |
| Blind | 로그인 필수; 공개 읽기 불가 |
| Reuters | 라이선싱 검토 필요; 무단 크롤링 ToS 위반 위험 |
| KRX KIND | JavaScript 렌더링 필요 → Round 2 Playwright 구현 |

---

## 2. Alias 규칙

Naver 개발자 센터는 앱당 `CLIENT_ID` / `CLIENT_SECRET`을 발급한다.
다른 서비스와 구분을 위해 본 프로젝트에서는 `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET`을 정식 키명으로 사용하고,
`CLIENT_ID` / `CLIENT_SECRET`을 alias로 허용한다 (env_loader.py).

| 정식 키 | 허용 alias |
|---|---|
| `NAVER_CLIENT_ID` | `CLIENT_ID` |
| `NAVER_CLIENT_SECRET` | `CLIENT_SECRET` |
| `BOK_ECOS_API_KEY` | `ECOS_API_KEY` |

> `.env`에 `CLIENT_ID = value` 형태(등호 주변 공백)로 작성하면 `check_env_hygiene.py`가
> `SPACE_AROUND_EQUALS` + `AMBIGUOUS_ALIAS` 두 가지 경고를 발생시킨다.

---

## 3. API별 공식 정책

### Naver Search API
- **발급 URL**: https://developers.naver.com/apps/#/register
- **인증 방식**: HTTP 헤더 `X-Naver-Client-Id` + `X-Naver-Client-Secret`
- **무료 플랜**: 일 25,000 호출 (blog 검색 + news 검색 각각 별도 카운트)
- **대표 에러**: HTTP 401 인증 실패, HTTP 429 쿼터 초과
- **최소 테스트 엔드포인트**: `GET https://openapi.naver.com/v1/search/blog.json?query=test&display=1`
- **비고**: 앱 1개로 blog/news 모두 사용 가능; 동일 CLIENT_ID/SECRET

### YouTube Data API v3
- **발급 URL**: https://console.cloud.google.com/ (YouTube Data API v3 활성화)
- **인증 방식**: query param `key=YOUTUBE_API_KEY`
- **무료 플랜**: 10,000 quota units/day (검색 1회 = 100 units)
- **대표 에러**: HTTP 403 `quotaExceeded` / `keyInvalid`
- **최소 테스트 엔드포인트**: `GET https://www.googleapis.com/youtube/v3/search?key=KEY&q=test&part=snippet&maxResults=1`
- **비고**: 쿼터 모니터링은 Google Cloud Console에서

### Product Hunt API v2
- **발급 URL**: https://www.producthunt.com/v2/oauth/applications
- **인증 방식**: Bearer token (`Authorization: Bearer TOKEN`)
- **무료 플랜**: developer token 약 1,000 req/day (UNKNOWN — 공식 명시 없음)
- **대표 에러**: HTTP 401 on invalid token
- **최소 테스트 엔드포인트**: GraphQL `POST https://api.producthunt.com/v2/api/graphql` query `{ posts(first:1){edges{node{name}}} }`
- **비고**: Developer token과 OAuth2 token 구분; developer token 권장

### OpenDart (금융감독원 전자공시)
- **발급 URL**: https://opendart.fss.or.kr/uat/uia/egovLoginUsr.do (회원가입 후 API 신청)
- **인증 방식**: query param `crtfc_key=KEY`
- **무료 플랜**: ~10,000 req/day (출처마다 상이; UNKNOWN 정확값)
- **대표 에러**: status `010` 인증키 없음, `020` 인증키 유효하지 않음, `100` 쿼터 초과
- **최소 테스트 엔드포인트**: `GET https://opendart.fss.or.kr/api/list.json?crtfc_key=KEY&bgn_de=20260101&end_de=20260101&page_no=1&page_count=1`
- **비고**: 공시 목록 API는 별도 인증 없이 기본 제공

### BOK ECOS (한국은행 경제통계)
- **발급 URL**: https://ecos.bok.or.kr/api/#/AuthKeyApply
- **인증 방식**: query param `apiKey=KEY` (또는 URL 경로에 삽입)
- **무료 플랜**: UNKNOWN (공식 문서에 명시 없음; 개인 비상업적 사용 무료로 추정)
- **대표 에러**: UNKNOWN — HTTP 400 응답 추정
- **최소 테스트 엔드포인트**: `GET https://ecos.bok.or.kr/api/StatisticTableList/KEY/json/1/5/`
- **비고**: API키 발급은 이메일 인증 후 즉시; R 패키지 `ecos` 참고 가능

### EIA (미국 에너지정보청)
- **발급 URL**: https://www.eia.gov/opendata/register.php
- **인증 방식**: query param `api_key=KEY`
- **무료 플랜**: 5,000 requests/day
- **대표 에러**: HTTP 403 on invalid key
- **최소 테스트 엔드포인트**: `GET https://api.eia.gov/v2/?api_key=KEY`
- **비고**: API key 즉시 발급; 에너지·연료 데이터 특화

### HackerNews Firebase API
- **발급**: 불필요 (public)
- **인증 방식**: none
- **쿼터**: UNKNOWN (공식 rate limit 없음; 합리적 사용 권장)
- **최소 테스트 엔드포인트**: `GET https://hacker-news.firebaseio.com/v0/topstories.json?limitToFirst=5&orderBy="$key"`

### GDELT v2
- **발급**: 불필요 (public)
- **인증 방식**: none
- **쿼터**: UNKNOWN (공식 rate limit 없음; 과도한 요청 자제)
- **최소 테스트 엔드포인트**: `GET https://api.gdeltproject.org/api/v2/doc/doc?query=test&mode=artlist&maxrecords=1&format=json`

### SEC EDGAR
- **발급**: 불필요 (public)
- **인증 방식**: none; `User-Agent` 헤더 필수 (SEC 정책)
- **쿼터**: 10 req/s (초과시 HTTP 429)
- **최소 테스트 엔드포인트**: `GET https://efts.sec.gov/LATEST/search-index?q=%228-K%22&forms=8-K&dateRange=custom&startdt=2026-01-01&enddt=2026-01-01`
- **비고**: `User-Agent: YourApp/1.0 (contact@email.com)` 형식 권장

### Federal Register API
- **발급**: 불필요 (public)
- **인증 방식**: none
- **쿼터**: UNKNOWN (공식 rate limit 없음)
- **최소 테스트 엔드포인트**: `GET https://www.federalregister.gov/api/v1/articles.json?per_page=1&order=newest`

### Reddit Public JSON
- **발급**: 불필요 (public read-only .json endpoint)
- **인증 방식**: none for read; `User-Agent` 필수 (Reddit 정책)
- **쿼터**: 비인증 60 req/min (IP 기준)
- **최소 테스트 엔드포인트**: `GET https://www.reddit.com/r/worldnews.json?limit=1`
- **비고**: 인증 API (OAuth2) 불필요한 읽기 전용 사용; POST/vote 등은 OAuth2 필요

### EU Press Corner
- **발급**: 불필요 (public HTML)
- **인증 방식**: none
- **최소 테스트 엔드포인트**: `GET https://ec.europa.eu/commission/presscorner/home/en`
- **비고**: JavaScript 의존성 있어 Playwright 고려 가능 (Round 2)

### KRX KIND
- **발급**: UNKNOWN (공개 포털; 회원가입 필요 여부 UNKNOWN)
- **인증 방식**: JavaScript 렌더링 필요
- **최소 테스트 엔드포인트**: `https://kind.krx.co.kr/disclosure/todaydisclosure.do` (Playwright 필요)
- **비고**: Round 2로 이연; 현재 `NEEDS_PLAYWRIGHT_SEARCH` 상태로 precheck 반환

---

## 4. Hygiene 발견사항 (Round 1 조사)

| 발견사항 | 파일 | 처리 |
|---|---|---|
| `gcp-service-account-key.json` 0바이트 파일이 repo에 미ignore 상태 | `.gitignore` | .gitignore에 `gcp-service-account-key.json`, `*service-account*.json`, `*-key.json` 추가 완료 |
| `CLIENT_ID` / `CLIENT_SECRET` bare alias가 .env에 있을 경우 다른 서비스 키와 충돌 가능 | check_env_hygiene | `AMBIGUOUS_ALIAS` 경고 추가 |
| .env.example에 ingestion 소스 키 섹션 부재 | `.env.example` | Round 1에서 ingestion 섹션 추가 |

---

## 5. GOOGLE_APPLICATION_CREDENTIALS 처리 정책

- `env_loader.py`의 `check_gcp_credentials()`는 **경로 존재 여부만 확인** (`Path.exists()`)
- 파일 내용 읽기·파싱·로깅 금지
- 반환값: `"path_exists"` / `"path_not_found"` / `"missing"`
- 보안: GCP 서비스 계정 JSON은 `.gitignore`에 추가됨; 절대 커밋 금지
