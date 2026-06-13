# docs/73 — Final Handoff Master (최종 인수인계)

**생성일**: 2026-06-12
**대체 문서**: docs/66(Final Handoff) — 갱신·폐기. docs/60~66 7편은 70~73 4편으로 통폐합됨 (사용자 승인).
**이 문서가 단일 진실 소스(single source of truth)**. 충돌 시 docs/70~73이 이전 모든 문서보다 우선.

---

## 1. 현재 결론 (한 문장)

**44개 소스가 live 실측으로 CORE_READY 확정** (38 + Phase 1 뉴스 6개 재프로브 편입, 06-12 risk closure 라운드), 6개 READY_WITH_CAUTION. Pre-orchestration 리스크(12-1·12-3~12-10)가 닫혔다: rate limit store pluggable+영속화, source health/quarantine gate, secret scan 자동화, browser runtime check, publication boundary, env alias 위생. 테스트 450개 전체 통과. 다음 단계는 plans/012의 에이전트 오케스트레이션(Celery+Redis, 12-2) 구현이다.

---

## 2. 소스 상태 요약 (상세: docs/70)

| 분류 | 수 | 의미 |
|------|----|----|
| CORE_READY | **44** | 즉시 파이프라인 연결 가능 (06-12 실측 + 뉴스 6개 재프로브) |
| READY_WITH_CAUTION | 6 | 수집 가능, quota/약관/봇감지 모니터링 |
| DEFERRED_SPECIAL_ROUND | 1 | krx_kind — open.krx.co.kr 공식 API 전환 |
| MVP_DEFERRED | 1 | reddit — MVP 보류 (사용자 확정) |
| MVP_EXCLUDED | 5 | x, blind, reuters, fmkorea, google_programmable_search |
| 합계 | 58 | registry 57 + YAML 미등록 google_trends_explore |

### CORE_READY 44개

```
문서/뉴스:    bbc, ap_news, techcrunch, the_verge,
              zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera  ← 06-12 재프로브 편입 (docs/83)
커뮤니티:    hacker_news, youtube, product_hunt
검색:        naver_news_search, naver_blog_search, serper, tavily, exa, gnews
공식 데이터: gdelt, sec_edgar, federal_register, opendart, bok_ecos, eia, eu_press_corner
트렌드:      signal_bz, google_trending_now, loword
시장:        finnhub, twelve_data, alpha_vantage, polygon, coinbase_market, binance_market
도메인:      kofic, igdb, tmdb, kopis, aladin, kma, tour, its, culture_info
```

### READY_WITH_CAUTION 6개

```
cnbc, guardian, nyt, newsapi, dcinside, google_trends_explore
```

---

## 3. 이번 라운드(2026-06-12)에 달라진 것

### 3-1. 소스 확정 라운드 (전반)

| 항목 | 내용 |
|------|------|
| live 실측 | 라운드 A 22회 + 라운드 B 5회 (소스당 1회 원칙) — 22개 소스 전부 최종 LIVE_SUCCESS |
| 코드 수정 | kma/tour/its/culture_info 엔드포인트·파라미터 원인 수정 (`run_api_connectivity_check.py`, `api_probe.py`) |
| 신규 기능 | per-source 전략 budget (`retry_policy.yaml` `per_source:` + `budget_for()`) — RISK-T01 해소 |
| registry 갱신 | stale `MISSING_KEY` 20건 → 실측 status로 교체, kofic env_keys 교정(KOFIC_API_KEY), reddit MVP_DEFERRED |
| 테스트 | 349 → 359 passed (신규 10: per-source budget) |
| 문서 | docs/60~66 → 70~73 통폐합, plans/012 작성 |
| 보안 | secret scan 2회 PASS (실키 0건), env hygiene 키 NAME만 |

### 3-2. Pre-orchestration risk closure 라운드 (후반, docs/74~84)

| RISK | 내용 | 문서 |
|------|------|------|
| 12-1 | RateLimitStore pluggable (memory/local_file/redis) + 429 cooldown 영속화 | docs/75 |
| 12-3 | SourceHealthState 6상태 + quarantine + collection_probe health gate | docs/76 |
| 12-4 | browser runtime check 러너 (실측 READY) + Docker 배포 전제 | docs/77 |
| 12-5 | 전략 복원력 회귀 테스트 14개 고정 (동작 변경 없음) | docs/78 |
| 12-6 | trends 정책 120분 강화 + 429 영속화 + Route 2 429 감지 | docs/79 |
| 12-7 | publication boundary 정책 (수집 경로 미연결, 게시 계층용) | docs/80 |
| 12-8 | secret scan 도구 (2계층, exit code 게이트) — baseline PASS | docs/81 |
| 12-9 | env hygiene _ALIASES 일반화 + MISMATCH/EMPTY 탐지 | docs/82 |
| 12-10 | CLI 러너 신규 + Phase 1 뉴스 6개 재프로브 6/6 LIVE_SUCCESS | docs/83 |
| — | 테스트 359 → **450 passed** (신규 91) | docs/84 |
| 12-2 | **미구현 (의도)** — Celery+Redis는 plans/012 | — |

---

## 4. Agent 수집 호출 함수 (상세: docs/72)

| 함수 | 파일 | 용도 |
|------|------|------|
| `run_collection_probe(source_id, force=False)` | `ingestion/fetch_strategies/collection_probe.py` | **최상위 진입점** — 자동 라우팅 + health gate (06-12) |
| `run_api_live_probe(source_id)` | `ingestion/probes/api_probe.py` | API 소스 직접 호출 |
| `run_fetch_strategy_loop(source_id, url)` | `ingestion/fetch_strategies/strategy_runner.py` | 전략 루프 (per-source budget 적용) |
| `CloudBrowserLikeStrategy().fetch(url, source_id)` | `ingestion/fetch_strategies/cloud_browser_like.py` | Playwright 렌더링 |
| `SeleniumRenderStrategy().fetch(url)` | `ingestion/fetch_strategies/selenium_strategy.py` | Selenium fallback |
| `run_playwright_probe(site_id)` | `ingestion/runners/run_playwright_probe.py` | YAML selector probe |
| CLI `run_collection_probe --source <id> [--json] [--force]` | `ingestion/runners/run_collection_probe.py` | **신규(06-12)** — 단일 소스 probe + 보강 리포트 |
| CLI `run_browser_runtime_check [--launch] [--strict]` | `ingestion/runners/run_browser_runtime_check.py` | **신규(06-12)** — 브라우저 런타임 점검 |
| CLI `scan_secrets --paths <...>` | `ingestion/tools/scan_secrets.py` | **신규(06-12)** — secret 유출 스캔 (exit 0/1/2) |

```python
from ingestion.fetch_strategies.collection_probe import run_collection_probe
result = run_collection_probe("gdelt", max_items=5)
print(result.status, result.items_found)   # LIVE_SUCCESS 3
```

---

## 5. 사용자 액션 요청 리스트

이번 실측으로 "시스템이 스스로 해결할 수 없음"이 확정된 항목만 남았다. **필수 항목은 없고**, 모두 선택적 개선이다.

### A-1. `.env` 키 이름 개명 (권장 — 위생 경고 해소) — 06-12 갱신: 대상 6건으로 확대

- **문제**: hygiene 도구가 `_ALIASES` 전체로 일반화되면서(docs/82) legacy alias **6건**이 확인됐다: `CLIENT_ID`, `CLIENT_SECRET`, `ECOS_API_KEY`, `GOOGLE_API_KEY`, `CSE_CX`, `CULTURE_INFO_KEY`. **기능에는 영향 없음** (alias 자동 해석, 값 충돌 0건).
- **왜 내가 못 하는가**: `.env` 직접 수정은 하드 제약(키 파일 비수정)에 묶여 있다.
- **사용자가 할 일**: `.env`에서 키 이름만 canonical로 변경 (값은 그대로):
  - `CLIENT_ID=...` → `NAVER_CLIENT_ID=...` / `CLIENT_SECRET=...` → `NAVER_CLIENT_SECRET=...`
  - `ECOS_API_KEY=...` → `BOK_ECOS_API_KEY=...`
  - `GOOGLE_API_KEY=...` → `GOOGLE_CUSTOM_SEARCH_API_KEY=...` / `CSE_CX=...` → `GOOGLE_CUSTOM_SEARCH_CX=...`
  - `CULTURE_INFO_KEY=...` → `CULTURE_INFO_API_KEY=...`
  - canonical 라인이 이미 있으면 legacy 라인 삭제 (상세: docs/82 §4)
- **완료 후 검증**: `python -m ingestion.tools.check_env_hygiene` → AMBIGUOUS_ALIAS 0건
- **미실행 시 영향**: 없음 (alias로 정상 동작 중). 경고만 지속.

### A-5. (선택) rate limit backend를 local_file로 전환 — 재기동 후 cooldown 유지

- **상황**: 기본 backend는 `memory`(기존 동작 보존). 단일 프로세스 운영 중 429 cooldown을
  재기동 후에도 유지하려면 `rate_limit_policy.yaml`의 `rate_limit_backend.backend: local_file`
  로 변경하거나 env `INGESTION_RATE_LIMIT_BACKEND=local_file` 설정 (docs/75).
- **미설정 시 영향**: 재기동 시 cooldown 소실 (기존과 동일). Celery 라운드에서는 redis가 맡음.

### A-6. (선택) secret scan을 pre-commit/CI에 등록

- `python -m ingestion.tools.scan_secrets --paths ingestion/outputs docs/ingestion plans`
  exit 0/1/2 게이트. 등록 방법: docs/81 §4. 로컬 hook 설치는 사용자 결정 사항.

### A-2. KRX 공식 OpenAPI 키 발급 (선택 — 한국 거래소 공시 활성화)

- **문제**: kind.krx.co.kr 웹 화면은 자동화 접근에 서버 오류만 반환 → 공식 API(`open.krx.co.kr`)가 유일한 경로인데 키가 없다.
- **왜 내가 못 하는가**: 회원가입·본인 인증·이용 신청은 사람만 할 수 있다.
- **사용자가 할 일**:
  1. `open.krx.co.kr` 접속 → 회원가입
  2. OpenAPI 이용 신청 (승인 1~3일 소요 가능)
  3. 발급된 키를 `.env`에 `KRX_API_KEY=발급키` 한 줄 추가
- **완료 후 검증**: 키 추가 후 알려주면 KRX REST 수집 라운드(소스 모듈 + probe spec)를 구현한다.
- **가치**: 한국 거래소 공시(evidence_level=tier1) — 국내 기업 이벤트 탐지 품질 크게 향상.

### A-3. 기상청 API허브 authKey 발급 (선택 — 현재는 불필요)

- **상황**: kma는 data.go.kr 단기예보로 이미 LIVE_SUCCESS. 다만 apihub.kma.go.kr 전용 데이터(지상관측 일자료, 황사, 태풍 등)가 필요해지면 별도 키가 필요하다.
- **사용자가 할 일 (필요 시에만)**: `apihub.kma.go.kr` 회원가입 → API 신청 → 발급 키를 `.env`에 `KMA_APIHUB_AUTH_KEY=발급키`로 추가 (기존 `KMA_API_KEY`와 별개).
- **완료 후 검증**: 추가 후 알려주면 apihub 전용 probe spec을 구성한다.

### A-4. 유료·라이선스 소스 결정 (선택 — 비용/법무 판단)

| 소스 | 결정할 것 | 비용/조건 |
|------|----------|----------|
| X (Twitter) | Basic 플랜 구독 여부 | 월 $100+; 구독 시 `X_BEARER_TOKEN` 설정 |
| Reuters | 공식 API 라이선스 협의 여부 | Thomson Reuters 계약 |
| NYT | 상업 서비스 출시 전 약관 법무 검토 | 무료 키는 비상업만 |
| Google Custom Search | CX(검색 엔진 ID) 생성 여부 | serper/tavily/exa 정상이라 우선순위 낮음 |

- **미결정 시 영향**: 없음 — 전부 MVP_EXCLUDED/CAUTION으로 이미 처리돼 있다.

> 참고: 직전 문서(docs/60)의 "REPAIRABLE_NEXT 14개 키 발급 캠페인"은 **이번 실측으로 소멸** — 해당 키들은 이미 전부 존재·유효했다. `.env`에 빈 값 키도 없음(06-12 확인).

---

## 6. 다음 단계

### 즉시 가능 (권장 순서)

1. **plans/012 구현 — 에이전트 오케스트레이션** (Celery+Redis 주기 수집 + RedisRateLimitStore 연결 + 재시도 큐). 설계 완료 + 인터페이스 준비 완료 (`get_store()`, `list_due_for_retry()`, health gate).
2. ~~Phase 1 미검증 6개 재프로브~~ — **완료 (06-12, docs/83): 6/6 LIVE_SUCCESS → CORE_READY 44**.
3. **KRX 라운드** — 사용자 A-2 완료 후.
4. **normalization / event_candidate 추출** — 주기 수집으로 데이터가 쌓인 후.

### 범위 밖 (DEFERRED — plans/012에 기록만)

Celery/Redis 실제 구현, rate_limit Redis 캐시 구현, KRX 공식 API 연동, normalization/event_candidate 구현, `.env` 직접 수정.

---

## 7. 환경 상태 요약

| 항목 | 상태 |
|------|------|
| Python | 3.11.9 (.venv, uv) |
| 테스트 | **450 passed, 0 failed** (06-12 risk closure 라운드 +91) |
| Selenium | 4.26.1, smoke LIVE_SUCCESS |
| Playwright | 1.48.0, runtime check **READY** (`run_browser_runtime_check` 실측) |
| Docker Compose | dev.yml에 redis/postgres/milvus/opensearch/backend/worker/agent-worker/frontend 정의됨 (앱 이미지에 Chrome 미포함 — Docker 전제 docs/77, 빌드는 plans/012) |
| 보안 스캔 | **scan_secrets 도구 PASS** (710 files, 실키 0건, 2026-06-12) |
| source_registry.yaml | 57개 항목, status 실측 갱신 완료 (뉴스 6개 포함) |
| retry_policy.yaml | per_source budget 4개 소스 override |
| rate_limit_policy.yaml | per-source override (gdelt/trends 7200s) + `rate_limit_backend:` 섹션 |
| 상태 파일 (신규) | `outputs/state/rate_limit_cache.json`, `outputs/state/source_health.json` |
| publication_policy.yaml | 게시 경계 정책 (수집 미연결, 게시 계층용) |

---

## 8. 문서 체계 (이 라운드 이후)

| 문서 | 내용 |
|------|------|
| **docs/70** | 전체 소스 상태 마스터 (실측 매트릭스 + 집계) |
| **docs/71** | 근본 원인 분석 + 리스크 레지스터 (RESOLVED 표기) |
| **docs/72** | 수집 프레임워크 + 브라우저 전략 (per-source budget 반영) |
| **docs/73** | 이 문서 — 최종 handoff + 사용자 액션 |
| **docs/74~84** | Pre-orchestration risk closure 라운드 (74 계획, 75~83 risk별 보고, 84 최종) |
| **docs/85~93** | Live Collection Audit 라운드 (85 계획, 86~87 분류/quota, 88~90 실측, 91~92 readiness/주기, 93 최종) |
| **plans/012** | 에이전트 오케스트레이션 구현 PLAN |

docs/60~66은 본 라운드에서 삭제됨(사용자 승인). docs/28~59는 시간순 탐색 기록 — 충돌 시 70~73이 우선.

---

## 9. 2026-06-13 갱신 — Live Collection Audit 라운드 (docs/85~93)

### 신규 runner 사용법

```powershell
# 1차 seed audit (소스당 1회, gate/record_call 포함)
.\.venv\Scripts\python.exe -m ingestion.runners.run_primary_seed_live_audit [--layers ...] [--sources ...] [--dry-run] [--include-trends-explore]

# 2차 enrichment audit (1차 jsonl에서 hot seed 자동 도출 + 대분류 query budget)
.\.venv\Scripts\python.exe -m ingestion.runners.run_enrichment_live_audit --from-primary <1차 jsonl> [--queries ...] [--sources ...] [--dry-run]

# 주기 수집 시뮬레이션 (기본 8 소스 × 2 cycle, local_file backend 자동 설정)
.\.venv\Scripts\python.exe -m ingestion.runners.run_periodic_collection_simulation --cycles 2 --sleep-seconds 10
```

query 주입 단건 검증: `run_collection_probe --source naver_news_search --query "삼성전자" --json`.

### 라운드 결과 요약
- **1차 40 소스 실측**: seed_ready yes 23 / partial 9 — 뉴스 RSS·공시·도메인 그룹이 title+url+timestamp 완비 (docs/88).
- **2차 35 query 실측**: relevance high 24 — signal_bz 실검 → serper/naver 확장 연결 실증 (docs/89).
- **시뮬레이션 16회**: cache_skip dedup·local_file 영속·health 누적 PASS (docs/90).
- **Event Queue Readiness**: ready 21 + enrichment 9, EventSeedCandidate schema 제안 (docs/91), 주기 초안 (docs/92).
- 테스트 **509 passed** (450→509), secret scan PASS(896 files), env hygiene WARNING 6건(기존 alias, 변동 없음).

### 다음 단계 갱신 (06-13)
1. plans/012 전 권장 수정: **Route 1 429 cooldown 기록 gap** (RISK-T04, docs/90 §3).
2. 소스 정비 4건: ap_news endpoint, newsapi everything 전환, gdelt 내성, fast_signal selector 보강.
3. plans/012 Celery beat에 docs/92 주기 초안 + cache_ttl 정합 반영.

> **한 줄 인수인계문 (갱신)**:
> "수집 계층은 '살아있음'을 넘어 **용도 검증(1차 seed 32종 + 2차 enrichment 9종 + 주기 시뮬레이션)**까지 실측 완료됐다(509 tests). EventSeedCandidate schema와 주기 초안(docs/91~92)이 준비되어 다음 단계는 plans/012 Celery 오케스트레이션이며, 그 전에 Route 1 429 cooldown 기록(RISK-T04)과 소스 정비 4건이 권장된다."

(이전) > "CORE_READY 44개 소스 + pluggable rate limit store + health/quarantine gate + secret scan 자동화까지 갖춘 수집 계층이 실측 검증 완료 상태(450 tests)이며, 다음 단계는 plans/012의 Celery+Redis 오케스트레이션(12-2) 구현이다. 사용자 필수 액션은 없고, KRX 키 발급(A-2)과 .env 키 개명(A-1, 6건)이 선택 과제로 남아 있다."

## 08/09 라운드 — 신규 runner/도구 (2026-06-13)

- `python -m ingestion.runners.run_api_partial_sources_audit [--sources ...] [--no-rate-limit]` — API partial/no 소스 E2E(sample→candidate/numeric_signal→본문). JSONL/MD 산출.
- `ingestion/tools/feed_discovery.py` — discover_feeds / validate_feed / google_news_proxy_url / discover_sitemaps (신규 뉴스 소스 온보딩 표준 1단계).
- `error_taxonomy.is_rate_limited_text()` — 429/soft-block 텍스트 분류 공용(playwright_probe·api_probe 공유).
- `_audit_common`: `NUMERIC_SIGNAL_SOURCES`, `seed_ready_label_for`, `_XML_FIELD_NAMES`, `_SAMPLE_PATHS`(igdb/hacker_news/bok_ecos/eia/its), `$root`/epoch 정규화.

## Trends fallback 턴 인수인계 (2026-06-13)

- **신규 진입점**: `docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`(통합 trace) + `README.md`(index). 개별 00~10은 APPLIED/SUPERSEDED.
- **신규 runner**: `run_trend_fallback_enrichment_audit.py` — Google Trends fallback enrichment(A trending_now / B RSS export / C 뉴스·검색). JSONL `trend_fallback_enrichment_audit_*`.
- **상태**: 15 checklist PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1(google_trends_explore, fallback로 비차단). pytest 635 passed. 다음 단계 plans/012(Celery/LangGraph).
