# docs/72 — Framework & Strategy Master (수집 프레임워크 + 브라우저 전략)

**생성일**: 2026-06-12
**대체 문서**: docs/63(Agent Fetch Framework deep dive) + docs/64(Browser Strategy 설명) — 두 문서를 통합·갱신하며 폐기
**근거**: 실제 코드(file:line) 기반. 이번 라운드 신규 기능(per-source budget) 반영.

---

## 비개발자를 위한 한 줄 설명

"소스 하나를 수집할 때, 단순 요청(httpx)부터 브라우저 렌더링(Playwright), 그래도 실패하면 다른 브라우저(Selenium)까지 자동으로 시도하고, 차단(CAPTCHA/로그인/페이월)이 감지되면 즉시 멈추는 시스템."

---

## 왜 "브라우저 전략"이 필요한가

현대 웹사이트의 상당수가 JavaScript(JS)로 콘텐츠를 렌더링한다. 단순 HTTP 요청(httpx)으로는 빈 HTML만 받는다. 브라우저가 JS를 실행한 후의 콘텐츠를 추출하려면 실제 브라우저 엔진이 필요하다.

### 수집 방법 4가지 비교

| 방법 | 설명 | 속도 | 성공률 | 봇 감지 위험 |
|------|------|------|--------|-------------|
| **static httpx** | 브라우저 없이 HTTP 요청 | 매우 빠름 | JS 없는 사이트만 | 낮음 |
| **Playwright** | Chromium 자동화 (주력) | 중간 | JS 렌더링 사이트 | 중간 |
| **Selenium** | Chrome 자동화 (fallback) | 느림 | JS 렌더링 사이트 | 중간 |
| **API** | 공식 REST/GraphQL 호출 | 빠름 | API 제공 소스 | 없음 |

---

## 전체 흐름 (10단계)

```
[1] 소스 선택 — source_registry.yaml에서 source_id 로드
[2] run_collection_probe(source_id) 진입 (collection_probe.py:26)
[3] 3-way 라우팅:
    ├─ _PROBE_SPEC에 있음 → [4] API Probe
    ├─ playwright_required → [5] CloudBrowserLikeStrategy
    └─ 그 외 → [6] Strategy Loop
[4] API Probe — run_api_live_probe → _sanitize_response()로 키 redact 후 artifact 저장
[5] CloudBrowserLikeStrategy — Playwright 렌더링 → 봇감지 체크 → markdown → artifact
[6] Strategy Loop — STRATEGY_SEQUENCE[0..9] 순서 시도, 시도마다 classify_failure → select_next_strategy
[7] RATE_LIMITED → cooldown 대기 후 동일 전략 재시도 (rate_limit_policy.yaml)
[8] BLOCKED (CAPTCHA/LOGIN/PAYWALL/ROBOTS) → 즉시 중단 (terminal)
[9] Selenium fallback — SEQUENCE 소진 + ready=True일 때만
[10] Artifact 저장 — artifact_store.py save_* (9종)
```

---

## STRATEGY_SEQUENCE와 budget

```
STRATEGY_SEQUENCE (retry_policy.py):
  [0] httpx_direct          [5] dom_heuristic
  [1] httpx_mobile_ua       [6] playwright_basic
  [2] httpx_random_ua       [7] playwright_scroll
  [3] readability           [8] playwright_wait_network_idle
  [4] trafilatura           [9] playwright_click_more
```

**budget이란**: 한 URL에 대해 몇 개의 전략까지 시도할지의 상한 (`max_strategies_per_url`). 전역 기본값 3 — httpx 계열에서 끝난다.

### ⭐ 신규 (2026-06-12): per-source budget override

직전 라운드까지 "기본 budget=3으로는 playwright(index 6)에 도달 불가"가 운영 함정(RISK-T01)으로 문서에만 기록돼 있었다. 이번 라운드에 코드로 해소했다:

```yaml
# ingestion/configs/retry_policy.yaml
per_source:
  krx_kind:
    max_strategies_per_url: 8   # js_heavy — playwright 필수
  eu_press_corner:
    max_strategies_per_url: 8   # js_heavy — playwright 필수
  dcinside:
    max_strategies_per_url: 6   # anti_bot — EXTRACTION_EMPTY → playwright 점프 대상
  fmkorea:
    max_strategies_per_url: 6   # anti_bot — EXTRACTION_EMPTY → playwright 점프 대상
```

**동작 방식** (우선순위 순):
1. 호출자가 `run_fetch_strategy_loop(..., strategy_budget=N)`을 명시하면 그 값이 최우선
2. 아니면 `RetryPolicy.budget_for(source_id)` — YAML `per_source:`에 있으면 그 값
3. 아니면 전역 기본 3 (기존 동작과 동일 — 테스트 호환)

**구현 위치**: `retry_policy.py`(`per_source_budget` 필드 + `budget_for()`), `strategy_runner.py`(source_id 조회), 테스트 `ingestion/tests/unit/test_per_source_budget.py` (10케이스).

---

## 핵심 함수 상세

### `run_collection_probe` (collection_probe.py:26)
Agent 최상위 진입점. 라우팅 우선순위:
1. `source_id in _PROBE_SPEC` → `run_api_live_probe`
2. `_PLAYWRIGHT_FIRST_SOURCES`(7개: krx_kind, eu_press_corner, signal_bz, loword, google_trending_now, dcinside, fmkorea) 또는 `_is_playwright_required()` → `CloudBrowserLikeStrategy`
3. 그 외 → `run_fetch_strategy_loop`

`playwright_probe_sites.yaml`에 `deferred: false`로 등록된 소스는 코드 수정 없이 자동으로 Playwright 경로로 라우팅된다.

### `run_api_live_probe` (probes/api_probe.py)
REST/GraphQL/XML API 소스 직접 호출. `_PROBE_SPEC`이 소스별 extra_params/meaningful_fields/response_format을 정의.
**보안**: `_sanitize_response()`가 응답에 echo된 키 값을 redact 후 저장. data.go.kr Encoding 키의 이중 인코딩은 `%` 감지 시 1회 unquote로 방지.
**이번 라운드 갱신**: kma(데이터포털 단기예보 JSON), tour(KorService2), its(/trafficInfo + bbox), culture_info(period2) probe spec 동기화 — 4개 모두 LIVE_SUCCESS 실측 검증 완료 (docs/71 Part 1).

### `run_fetch_strategy_loop` (fetch_strategies/strategy_runner.py)
전략 루프. 시도마다 exponential backoff(2s→4s→…max 30s). 흐름:
- 성공(html 있음) → `record_call()` 후 success 반환
- 예외 → `classify_failure()` → BLOCKED면 즉시 종료 / RATE_LIMITED면 cooldown 후 동일 전략 / 그 외 `select_next_strategy()`
- 빈 응답 → EXTRACTION_EMPTY로 기록 후 다음 전략

### `select_next_strategy` (fetch_strategies/strategy_selection.py:24)
```
failure ∈ BLOCKED_ERRORS            → None (즉시 중단)
failure == RATE_LIMITED             → None (caller가 cooldown 처리)
attempts ≥ budget                   → None (budget 소진)
EXTRACTION_EMPTY + httpx 계열       → playwright_basic 점프 (JS 렌더 필요 신호)
SEQUENCE 소진 + Selenium ready      → selenium_rendered_dom
RSS/feed/XML 소스                   → playwright 계열 skip
```

### `classify_failure` (fetch_strategies/failure_classifier.py)
HTTP status + 응답 body 분석 → ErrorType. 401→INVALID_KEY, 429→RATE_LIMITED, 4xx/5xx, 봇 감지 패턴(CAPTCHA/LOGIN_WALL/PAYWALL).

### `CloudBrowserLikeStrategy` (fetch_strategies/cloud_browser_like.py)
Playwright JS 렌더링 + screenshot + markdown 추출 통합. 처리: 렌더 → `classify_content_blocker()` 봇감지 → `extract_markdown()` → artifact 저장.

### `SeleniumRenderStrategy` (fetch_strategies/selenium_strategy.py)
최후 fallback. `selenium_env_status()["ready"]` = selenium 설치 + Chrome 바이너리 발견. Selenium Manager가 chromedriver 자동 조달. 활성화 조건: SEQUENCE 소진 AND (preferred_browser==selenium OR 모든 playwright 실패) AND ready.
06-08 smoke 테스트 LIVE_SUCCESS (selenium==4.26.1).

### `ErrorType` (core/error_taxonomy.py)

| ErrorType | 분류 | 처리 |
|-----------|------|------|
| NETWORK_TIMEOUT, HTTP_5XX, JS_RENDER_FAIL | retryable | 다음 전략 진행 |
| RATE_LIMITED | non-terminal | cooldown 후 동일 전략 |
| CAPTCHA_DETECTED, LOGIN_WALL_DETECTED, PAYWALL_DETECTED, ROBOTS_BLOCKED | **terminal (BLOCKED_ERRORS)** | 즉시 중단 |
| EXTRACTION_EMPTY | 전략 점프 | httpx → playwright_basic |
| INVALID_KEY, API_RETURNED_HTML_ERROR_PAGE | non-retryable | 원인 조사 |

---

## 봇 감지(차단)는 어떻게 작동하나

| 감지 방법 | 설명 | 차단 예시 |
|----------|------|---------|
| User-Agent 분석 | "HeadlessChrome" 등 식별 | httpx, 기본 Playwright |
| JS 핑거프린팅 | navigator.webdriver, WebGL 등 | Playwright 기본 모드 |
| 행동 분석 | 마우스 이동 없음, 즉각 클릭 | 자동화 공통 |
| IP 평판 | 데이터센터 IP, 빈번한 요청 | 모든 자동화 |
| Cloudflare Turnstile | JS 챌린지 + 지문 검사 | FMKorea |

**이 프로젝트의 탐지** (`classify_content_blocker`):
`"__cf_chl_opt"` / `"just a moment..."` → CAPTCHA_DETECTED, `"sign in to continue"` → LOGIN_WALL_DETECTED, `"subscribe to read"` → PAYWALL_DETECTED.
→ 감지 즉시 terminal BLOCKED. **챌린지 우회(challenge solving)는 원칙적으로 시도하지 않는다.**

---

## Rate Limit 정책 (core/rate_limit_policy.py)

```yaml
# rate_limit_policy.yaml 기본값
default:
  min_interval_seconds: 0
  max_calls_per_run: 1
  cooldown_on_429_seconds: 60
  max_retries_on_429: 1
  cache_ttl_seconds: 0

# per_source override 예 (06-12 risk closure 라운드에서 강화)
google_trends_explore:
  min_interval_seconds: 7200    # 120분 간격 (1800s에서도 429 재발 → 상향)
  cooldown_on_429_seconds: 3600
  max_retries_on_429: 0
  cache_ttl_seconds: 7200
```

**캐시 휘발성 (RISK-T02) — 부분 해소 (06-12, docs/75)**:
backing store가 pluggable해졌다 (`core/rate_limit_store.py`):

```
RateLimitStore (ABC)
 ├── InMemoryRateLimitStore        # 기본 — 기존 _call_cache dict 그대로 backing
 ├── LocalPersistentRateLimitStore # outputs/state/rate_limit_cache.json (재기동 생존)
 └── RedisRateLimitStore           # plans/012 §3 키 계약 구현 완료 — 연결만 잔여
```

- backend 선택: env `INGESTION_RATE_LIMIT_BACKEND` > yaml `rate_limit_backend:` > memory.
- 429 시 `record_rate_limited()` → next_retry_at 영속, 재호출 시 `in_cooldown()` gate가
  네트워크 없이 차단 (strategy_runner 진입 전). 재기동 생존 스모크 PASS.
- 공개 시그니처(`cache_key`/`is_cached`/`record_call`) 불변 — 기존 테스트 20개 무수정 통과.

---

## Source Health Gate (06-12 신규 — core/source_health.py, docs/76)

`run_collection_probe` 상단에 health gate가 추가됐다:

```
[2'] health gate (collection_probe._health_gate)
     ├─ BLOCKED_TERMINAL        → 네트워크 없이 BLOCKED 반환 (CAPTCHA/LOGIN/PAYWALL/ROBOTS 이력)
     ├─ RATE_LIMITED_COOLDOWN   → next_retry_at 미래면 RATE_LIMITED 반환
     ├─ QUARANTINED_RETRYABLE   → 재점검 시각 전이면 skip (일시 장애 누적 3회)
     ├─ DEFERRED_SPECIAL_ROUND  → DEFERRED 반환
     └─ HEALTHY/DEGRADED        → 통과
[10'] 모든 return 직전 _update_health(result) → outputs/state/source_health.json 갱신
```

- 전이는 순수 함수 `apply_probe_outcome()` — 성공 시 failure_count 리셋, 일시 장애 누적
  ≥3 → 격리(+6h 재점검), blocker → 즉시 terminal.
- `--force` (CLI) 또는 `force=True` kwarg로 gate 우회 (오분류 복구 절차: docs/76 §5).
- strategy_runner는 health store를 직접 보지 않는다 — 통합 지점은 collection_probe 단일화.

---

## Artifact 저장 (core/artifact_store.py)

| 함수 | 저장 경로 | 내용 |
|------|----------|------|
| `save_raw_html()` | `outputs/raw_html/{source_id}/` | 원본 HTML |
| `save_dom_snapshot()` | `outputs/dom_snapshots/` | DOM 분석 JSON |
| `get_screenshot_path()` | `outputs/screenshots/` | 스크린샷 |
| `save_extracted_text()` | `outputs/extracted_text/` | title+body 텍스트 |
| `save_raw_payload()` | `outputs/raw_payload/` | API 원본 응답 |
| `save_extracted_payload()` | `outputs/extracted_payload/` | 파싱된 구조화 JSON |
| `save_raw_signal()` | `outputs/raw_signal/` | 트렌드 신호 |
| `save_rendered_dom()` | `outputs/rendered_dom/` | 렌더링 HTML |
| `append_result_row()` | `outputs/jsonl/` | 결과 행 누적 |

파일명: `{run_id}_{url_hash}_{strategy}.{ext}`, run_id: `{YYYYMMDD_HHMMSS}_phase{n}_{source_id}`.

---

## Docker/서버 배포 조건

```dockerfile
# Playwright (필수)
RUN playwright install chromium
# Selenium fallback 활성화 시
RUN apt-get install -y google-chrome-stable   # chromedriver는 Selenium Manager 자동 조달
```

| 환경 | 권장 방식 |
|------|----------|
| 저사양 (1-2 vCPU) | static httpx + API 중심 |
| 중간 (4+ vCPU) | Playwright 정상 운영 (워커 2-3) |
| 고사양 (8+ vCPU) | Playwright + Selenium fallback 병렬 |

---

## 현재 구현 상태 요약

| 기능 | 상태 |
|------|------|
| httpx static 수집 | 완전 구현 |
| CloudBrowserLikeStrategy (Playwright) | 완전 구현 + 검증 |
| playwright_probe (YAML selector) | 완전 구현 |
| 봇 감지 분류 / BLOCKED terminal | 완전 구현 |
| Selenium fallback | 완전 구현, smoke LIVE_SUCCESS |
| RATE_LIMITED cooldown | 완전 구현 |
| **per-source budget override** | **완전 구현 (2026-06-12, 테스트 10케이스)** |
| rate_limit 캐시 | **pluggable store (memory/local_file/redis) — 06-12 risk closure** |
| 429 cooldown 영속화 | **완전 구현 (record_rate_limited/in_cooldown) — 06-12** |
| source health gate / quarantine | **완전 구현 (collection_probe 통합) — 06-12** |
| secret scan 자동화 | **완전 구현 (tools/scan_secrets.py) — 06-12** |
| browser runtime check 러너 | **완전 구현 (READY 실측) — 06-12** |
| publication boundary 가드 | **구현 완료 (게시 계층 연결은 미래) — 06-12** |
| Redis 실인스턴스 연동 | 미구현 — plans/012 |
| Celery 주기 수집 | 미구현 — plans/012 |
| **query 주입 (2차 enrichment)** | **완전 구현 — 06-13 (docs/85~89)** |
| **audit runner 3종 + _audit_common** | **완전 구현 — 06-13 (테스트 59케이스)** |

---

## 2026-06-13 추가 — query 주입 + audit runner 아키텍처 (docs/85~93)

### query 주입 경로
`run_collection_probe(source_id, query=...)` → Route 1: `run_api_live_probe(..., query=query)`가 `_apply_query_override(probe_spec, query)`로 **deepcopy된 spec**에 검색어를 주입한다 (`_PROBE_SPEC` 전역 불변 — 불변성 테스트로 고정). Route 3: `run_fetch_strategy_loop(..., query=query or "")`. query 미지정 시 기존 호출 형태/거동 그대로 (하위호환).

- per-source 메타: `query_param`(파라미터명) + `query_in`(`params`|`json_body`) + 선택적 `query_endpoint`(tmdb: /movie/popular → /search/movie 전환).
- query 지원 14종: naver×2, youtube, gdelt, sec_edgar, newsapi, federal_register (params) / serper, tavily, exa (json_body) / **신규 entry** gnews·guardian·nyt·tmdb.
- **부수효과**: gnews/guardian/nyt/tmdb entry 신설로 `run_api_live_probe --all-safe`와 collection_probe Route 1 거동이 변경됨 (이전: default spec 또는 Route 3 fallback).

### audit runner 3종 (`ingestion/runners/`)
| runner | 역할 | 핵심 동작 |
|---|---|---|
| `run_primary_seed_live_audit` | 1차 seed 실측 (소스당 1회) | gate_check → enforce_min_interval → run_collection_probe → record_call → sample ≤3 → seed 필드 평가 |
| `run_enrichment_live_audit` | 2차 query 실측 (소스별 budget) | `--from-primary`로 hot seed 자동 도출(junk 필터), ko/en 언어 라우팅, relevance 집계, query_unsupported 분류 |
| `run_periodic_collection_simulation` | 주기 수집 검증 (≤3 cycle) | local_file backend(process env), cache_skip/cooldown/health/영속/실패기록 5종 검증 |

공통 헬퍼 `_audit_common.py`: `gate_check`(health→cooldown→cache 순), `enforce_min_interval`(**Route 1에 rate limit 게이트가 없는 코드 gap의 runner 레벨 보완**), sample 추출(json `_SAMPLE_PATHS` per-source 매핑 / xml / html / rendered selector), relevance(영문 토큰 + 한글 2-gram), seed 필드 평가(3+ = ready). skip/cached는 record의 `audit_action` 필드로만 기록 — **PROBE_STATUS frozenset 불변**.

## 08/09 라운드 — 상용 기법 흡수 + 프레임워크 결정 (2026-06-13)

### feed_discovery (기법 2·3·6)
`ingestion/tools/feed_discovery.py` 신설:
- `discover_feeds(html, base_url)` — `<link rel=alternate type=application/rss+xml>` + 공통 경로(/rss,/feed) 폴백.
- `validate_feed(url)` — httpx GET → feedparser `bozo==0 and entries>0`.
- `google_news_proxy_url(domain)` — 자체 feed 없는 매체의 Google News RSS 우회(canonical은 url_resolver 기법4로 해석, evidence 1단계 하향). Google 내부 RPC/batchexecute 우회는 하지 않는다.
- `discover_sitemaps(base_url)` — robots.txt Sitemap + 공통 sitemap 경로(기법 6, 깊은 백필 설계 고정).

### 기법 10 — soft-block/429 텍스트 분류 단일 출처
`error_taxonomy.RATE_LIMITED_SIGNALS` + `is_rate_limited_text()`로 승격. `playwright_probe._detect_429`이 이를 import(두 벌 목록 제거). api_probe의 비-JSON rate-limit 재분류와 동일 신호.

### 본문 추출 캐스케이드 (기법 5) — API 소스에도 동일 적용
`article_body_extractor.extract_article_body`(07 신설)를 federal_register/hacker_news 등 URL 보유 API 소스의 본문 추출에 재사용(중복 구현 없음). `run_api_partial_sources_audit`이 `extract_body`(httpx→Playwright fallback→trafilatura)로 연결.

### §3 프레임워크/오케스트레이션 결정
- **LangGraph 채택, 신규 패키지 미설치.** langgraph 0.2.76 기설치 — 탐색-수집-확장-검증 그래프(gate→probe→diagnose→explore→patch→verify)는 00 §3 종결 루프를 코드화한 것으로 LangGraph 노드+체크포인터로 충분. deepagents 등 신규 의존성은 Windows/py3.11 핀 환경의 회귀 표면을 넓혀 보류(도입 시 `uv pip install --dry-run` 충돌 확인 → 핀 변경 금지).
- **MCP는 "개발 중 보조 탐색"으로만.** 수집 경로의 재현성은 repo 내 runner가 보장해야 하므로(headless/cron 운영에서 MCP 의존은 깨짐) `.claude/settings.json` MCP 추가는 별도 사용자 승인 후 범위 외.
- runner/candidate/artifact contract는 이미 LangGraph 노드로 감싸기 쉬운 형태(run_collection_probe=probe 노드, run_structure_explorer=explore 노드, extract_article_body=verify 입력).
- 기법 6(sitemap)·8(self-healing streak)·12(DOM fingerprint)는 explorer 산출물에 토대만 두고 설계 고정. 기법 7(Conditional GET)·11(LLM judge)은 plans/012/이벤트 큐 단계.

## Trends fallback 전략 (2026-06-13)

- **안전 대체 경로 원칙**: provider 429를 강제로 뚫지 않고(우회 금지) 안전·합법 대체 경로로 동일 목적 데이터를 확보한다. Google Trends Explore(related queries)가 막히면 fallback chain으로 대체.
- **fallback chain** = A google_trending_now(Playwright) → B 공개 RSS export(`trends.google.com/trending/rss`) → C 뉴스/검색 enrichment(규칙 기반 related_candidate, `extract_related_candidates`).
- runner: `run_trend_fallback_enrichment_audit.py`(agent_ready). 헬퍼: `_audit_common.extract_related_candidates`(LLM 없이 결정적).
