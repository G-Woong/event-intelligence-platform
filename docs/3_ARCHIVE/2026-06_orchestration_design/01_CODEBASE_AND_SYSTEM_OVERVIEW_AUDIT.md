# 01 — 코드베이스 및 system_overview 분석 (Audit)

> **목적**: 오케스트레이션을 설계하기 전에, 현재 레포가 "무엇을 이미 갖췄고 / 무엇이 stub이고 / 어디에 끼워넣어야 하는지"를 정확히 못 박는다.
> **방법**: `ingestion/` 코드 deep-dive + `docs/system_overview/` 13개 문서 흡수 + 설정 분석.
> **이 문서는 사실 기록이다.** 추측은 UNKNOWN으로 표시한다.

---

## 1. 읽은 파일 목록

### 1.1 코드 (ingestion/)
- `fetch_strategies/`: collection_probe, strategy_runner, strategy_selection, models, failure_classifier, article_body_extractor, cloud_browser_like, selenium_strategy, artifact_writer
- `tools/`: url_resolver, feed_discovery, html_fetch_tool, readability_extractor, trafilatura_extractor, dom_candidate_extractor, metadata_extractor, markdown_extractor, playwright_browser_tool, scan_secrets, check_env_hygiene, check_dependency_readiness, search_query_builder
- `core/`: artifact_store, source_registry, rate_limit_store, source_health, quality_score, report_writer, fetch_result, extraction_result, error_taxonomy, retry_policy, logging_setup
- `schemas/`: event_candidate, raw_document, extracted_article, extracted_post, source_report, extraction_diagnostics
- `agents/`: state, graph, llm_judge
- `pipeline/`: discovery_collector, search_enrichment_collector, event_candidate_extractor, query_generator, canonical_event_builder, event_queue
- `runners/`: 23개 CLI runner
- `configs/`: source_registry.yaml, rate_limit_policy.yaml, retry_policy.yaml, publication_policy.yaml, extraction_policy.yaml, playwright_probe_sites.yaml, llm_policy.yaml, phase1/2/3_sources.yaml

### 1.2 다운스트림 코드 (스켈레톤)
- `backend/app/`: api(health/events/admin/internal/themes/sectors/comments/ai_replies), services(event/raw_event/search/vector_index/opensearch_index/reconciler/llm/embedding_client), db(postgres/redis/milvus/opensearch), models, schemas, core(config/security/observability/logging), alembic(0001~0003)
- `workers/`: collectors(rss_collector/sources), queue(producer/consumer), pipelines(ingest/publish)
- `agents/`: graphs(event_processing_graph), state(event_state), nodes(11개), tools(llm/vector_search), prompts(4 md)
- `frontend/`: Next.js (11 라우트, 4 API handler, 8 컴포넌트) — 코드 미정독, system_overview 07 흡수로 대체

### 1.3 문서
- `docs/system_overview/00~12` (13개 전부)
- `docs/DOCS_FINAL.md`, `docs/ingestion/INGESTION_FINAL.md`, `docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md`, `docs/Environment_setup/ENVIRONMENT_SETUP_FINAL.md`
- `plans/012_AGENT_ORCHESTRATION_PLAN.md`
- `.claude/agents/*.md`, `.claude/skills/*/SKILL.md`

---

## 2. 코드 구조 지도 (두 시스템)

```
repo-sunny-barto/
│
├── ingestion/                      ← [시스템 A] 수집 엔진 (44 CORE_READY)
│   ├── fetch_strategies/           ← 수집 전략 코어 (deterministic)
│   │   └── collection_probe.py     ← ★ run_collection_probe (최상위 진입점)
│   ├── tools/                      ← 추출/유틸 (deterministic)
│   ├── core/                       ← store/registry/quality (deterministic)
│   │   ├── rate_limit_store.py     ← ★ get_store() (memory/local_file/redis)
│   │   └── source_health.py        ← ★ get_health_store().list_due_for_retry()
│   ├── agents/graph.py             ← 소스별 크롤링 LangGraph (14노드, 2개만 LLM)
│   ├── pipeline/                   ← ★ 다운스트림 연결부 (전부 stub except event_queue)
│   │   └── event_queue.py          ← ★ EventQueue (JSONL 동작, Redis stub) = 브리지
│   ├── runners/                    ← 23개 CLI runner
│   └── configs/                    ← 7개 정책 YAML
│
├── backend/                        ← [시스템 B] FastAPI 서빙
├── workers/                        ← [시스템 B] RSS 수집 + Redis Stream 큐
│   ├── collectors/rss_collector.py ← 현재 입력원(RSS 3개뿐)
│   └── queue/{producer,consumer}   ← stream:raw_events
├── agents/                         ← [시스템 B] 사건 처리 LangGraph (11노드, 6 mock)
│   └── graphs/event_processing_graph.py
├── frontend/                       ← [시스템 B] Next.js UI
│
├── docs/                           ← 문서 (정리 완료)
├── plans/                          ← 012가 오케스트레이션 PLAN
└── docker-compose.dev.yml          ← redis/postgres/milvus/opensearch/backend/worker/agent-worker/frontend
```

**연결 끊김 지점**: `workers/collectors/`는 RSS 3개만 안다. `ingestion/`의 44개 소스는 `workers/`로 흐르지 않는다. **이 단절이 오케스트레이션이 메우려는 핵심 gap이다.**

---

## 3. 현재 source ingestion architecture (시스템 A 상세)

### 3.1 진입점과 라우팅

```
run_collection_probe(source_id, query=None, max_items=5, force=False)
 ├─ _health_gate(source_id)         # BLOCKED/cooldown/quarantine → 네트워크 없이 조기 반환
 ├─ Route 1 (API):       source_id in _PROBE_SPEC and not playwright-first
 │                       → run_api_live_probe(source_id, max_calls=1)
 ├─ Route 2 (Playwright): _PLAYWRIGHT_FIRST_SOURCES or _is_playwright_required()
 │                       → site_spec 있으면 run_playwright_probe, 없으면 CloudBrowserLikeStrategy().fetch()
 ├─ Route 3 (전략 루프):  그 외 → run_fetch_strategy_loop(source_id, base_url, source_spec, query)
 │                       STRATEGY_SEQUENCE[0..9] 순회
 └─ _update_health(...)              # 모든 return 직전 health store 갱신
```

`CollectionProbeResult` 필드: `source_id, status, strategy_used, items_found, probe_result, extraction, artifact_paths, error_category, next_action, attempts`.

### 3.2 전략 시퀀스 (Route 3)

`STRATEGY_SEQUENCE` (extraction_policy.yaml `strategy_sequence`에서 load):
```
[0] httpx_direct        [1] httpx_mobile_ua     [2] httpx_random_ua
[3] readability         [4] trafilatura         [5] dom_heuristic
[6] playwright_basic    [7] playwright_scroll   [8] playwright_wait_network_idle
[9] playwright_click_more
```
`strategy_selection.select_next_strategy()`가 실패 분류에 따라 점프(예: httpx에서 EXTRACTION_EMPTY → playwright_basic). RSS 소스는 playwright 전략 skip.

### 3.3 실패 분류 (ErrorType, core/error_taxonomy.py)

| 군 | ErrorType (대표) |
|---|---|
| 네트워크 | NETWORK_TIMEOUT, NETWORK_DNS_FAIL, NETWORK_CONNECTION_RESET, HTTP_4XX, RATE_LIMITED, HTTP_5XX, HTTP_REDIRECT_LOOP |
| 차단(terminal) | CAPTCHA_DETECTED, LOGIN_WALL_DETECTED, PAYWALL_DETECTED, ROBOTS_BLOCKED |
| 렌더/추출 | JS_RENDER_FAIL, DOM_PARSE_ERROR, EXTRACTION_EMPTY, EXTRACTION_TOO_SHORT, EXTRACTION_BOILERPLATE_ONLY, EXTRACTION_ENCODING_ERROR |
| 품질 | QUALITY_BELOW_THRESHOLD, QUALITY_PARTIAL |
| LLM | LLM_PARSE_ERROR, LLM_TIMEOUT, LLM_RATE_LIMIT |
| API | PARAMETER_MISSING, ENDPOINT_INVALID, INVALID_KEY, QUERY_ENCODING_OR_PARAM_ERROR, INVALID_SYMBOL_OR_EMPTY_MARKET_DATA, API_RETURNED_HTML_ERROR_PAGE |
| 기타 | DYNAMIC_RENDER_REQUIRED, SELECTOR_MATCHED_BUT_URL_EMPTY, LOW_EVIDENCE_EXTERNAL_SIGNAL, CONFIG_ERROR, UNKNOWN_ERROR |

차단형 4종은 즉시 BLOCKED_TERMINAL → health store 영속 → 재시도 불가.

---

## 4. runner 목록 (23개)

| runner | 용도 | 오케스트레이션 관련성 |
|---|---|---|
| `run_collection_probe` | 단일 소스 수집(1 live call) | ★ Celery task 본체 |
| `run_runner_orchestration_readiness` | 모든 runner의 CLI+JSONL 계약 점검 | 13/13 agent_ready |
| `run_enrichment_live_audit` | 2차 enrichment 소스 감사 | search_enrichment task 참조 |
| `run_trend_fallback_enrichment_audit` | Trends 429 fallback chain 검증 | fallback 설계 근거 |
| `run_periodic_collection_simulation` | 다중 cycle 시뮬(cooldown 누적) | ★ deterministic cycle 참조 |
| `run_primary_seed_live_audit` | 1차 seed 소스 감사 | seed 주기 수집 |
| `run_api_connectivity_check` | API 소스 연결 점검 | health 점검 |
| `run_browser_runtime_check` | Playwright/Selenium 런타임 점검 | Phase G 전제 |
| `run_playwright_probe` | YAML selector probe | Route 2 |
| `run_api_live_probe` | API probe | Route 1 |
| (그 외 13개) | audit/explore/inspect | 검증 보조 |

---

## 5. tools 목록 (본문 추출/URL/feed)

| tool | 함수 | 역할 |
|---|---|---|
| url_resolver | `resolve()`, `resolve_via_browser()`, `needs_browser_resolution()`, `canonical_from_html()` | redirect 추적 + Google News URL 해석 + canonical 추출 |
| feed_discovery | `discover_feeds()`, `validate_feed()`, `google_news_proxy_url()`, `discover_sitemaps()` | RSS/Atom 발견 + Google News 프록시 + sitemap |
| html_fetch_tool | `fetch_html(url, strategy, timeout)` | httpx HTML 취득(UA 3종) |
| readability_extractor | `extract_with_readability()` | readability-lxml 본문 |
| trafilatura_extractor | `extract_with_trafilatura()` | trafilatura 본문+메타 |
| dom_candidate_extractor | `extract_with_dom_heuristic()` | BeautifulSoup 휴리스틱 |
| metadata_extractor | `extract_metadata()`, `detect_language_hint()` | og 메타 + 언어 추정 |
| markdown_extractor | `extract_markdown()` | trafilatura markdown 모드 |
| playwright_browser_tool | `fetch_with_playwright_sync()`, `open_page()` | Playwright 렌더(동기 래퍼=asyncio.run) |
| scan_secrets | `main()` exit 0/1/2 | secret 스캔 |
| check_dependency_readiness | `main()` | 의존성 readiness JSON |

---

## 6. fetch strategies / extraction tools 요약

- **fetch**: httpx 3종(direct/mobile_ua/random_ua) → playwright 4종 → selenium fallback.
- **extraction**: site_selector(`article_body_extractor`) → trafilatura → readability → dom_heuristic. 최소 길이 게이트(site selector 50자, cascade 200자).
- **artifact**: `core/artifact_store.py` — raw_html/rendered_dom/screenshots/extracted_text/raw_signal/raw_payload. `.gitignore` 처리(커밋 안 함).

---

## 7. 현재 source status (INGESTION_FINAL §2 인용)

- CORE_READY **44**, READY_WITH_CAUTION **6**(cnbc, guardian, nyt, newsapi, dcinside, **google_trends_explore**), DEFERRED_SPECIAL_ROUND 1(krx_kind), MVP_DEFERRED 1(reddit), MVP_EXCLUDED 5(x, blind, reuters, fmkorea, google_programmable_search).
- **google_trends_explore = CONFIRMED_EXTERNAL_RATE_LIMIT** (PASS 아님). fallback chain 비차단.
- gdelt = PASS (min_interval 60s / cooldown 900s).

---

## 8. 현재 risk (오케스트레이션 진입 전)

| risk | 근거 |
|---|---|
| 두 시스템 미연결 | `ingestion/` 출력이 `workers/raw_events`로 안 흐름 |
| pipeline/ stub | discovery_collector/event_candidate_extractor 등 NotImplementedError |
| EventQueue Redis stub | `_redis_*` 메서드 NotImplementedError (JSONL만 동작) |
| asyncio 중첩 | `fetch_with_playwright_sync`가 `asyncio.run` — Celery/async 환경 충돌 가능 |
| 싱글톤 store fork | Celery prefork worker마다 별도 메모리 싱글톤 → local_file/redis 필수 |
| time.sleep 차단 | strategy_runner의 cooldown sleep이 워커 슬롯 점유 |
| 스켈레톤 6 mock 노드 | 사건 추론 미완(별도 STEP 014) |
| Windows Celery pool | prefork 미지원 가능 — `--pool=solo` |

---

## 9. orchestration insertion points (끼워넣을 지점)

| # | 지점 | 파일:심볼 | 방식 |
|---|---|---|---|
| 1 | task 단위 래퍼 | `ingestion/fetch_strategies/collection_probe.py:run_collection_probe` | Celery task가 이 함수 호출(수집 코드 무수정) |
| 2 | 주기 수집 본체 | `ingestion/pipeline/discovery_collector.py:DiscoveryCollector.collect` (stub) | source_ids fan-out 구현 |
| 3 | 큐 브리지 | `ingestion/pipeline/event_queue.py:EventQueue` | Redis Stream 연결(stub) + raw_events 브리지 |
| 4 | rate-limit 공유 | `ingestion/core/rate_limit_store.py:get_store` / `rate_limit_policy.py:{cache_key,is_cached,record_call}` | Redis 백엔드 전환 |
| 5 | health/격리 | `ingestion/core/source_health.py:get_health_store().list_due_for_retry` | beat가 재시도 대상 조회 |
| 6 | 소스 추론 그래프 | `ingestion/agents/graph.py:get_compiled_graph` | (선택) 단건 소스 본문 추론 |

---

## 10. deterministic vs agentic 경계 (현재 코드 실측)

- **Deterministic(LLM 호출 없음)**: `fetch_strategies/` 전체, `tools/` 전체, `core/` 전체, `agents/graph.py`의 14노드 중 12노드, `pipeline/`(stub).
- **Agentic(LLM 호출, 조건부)**: `agents/graph.py`의 `_node_extract_event_candidates`, `_node_llm_quality_judge` 2노드만. `LLM_PROVIDER` 기본=mock → `OPENAI_API_KEY` 없으면 MockJudgeClient 반환(실호출 없음).
- **결론**: 수집 계층은 본질적으로 deterministic이다. **오케스트레이션은 deterministic 코드로 만들고, LLM 판단은 소수 지점(전략 선택 보조/품질 판정/모호성 해소)에만 제한**해야 한다(03/07/09 문서 원칙).

---

## 11. system_overview 흡수 결과 (13개 문서)

| 문서 | 핵심 |
|---|---|
| 00 INDEX | 13단계 파이프라인 색인 (STEP 003~011, commit 38d0028, 2026-05-24) |
| 01 BIG PICTURE | 뉴스룸 비유, 5분 주기 수집 → AI 분석 → 사건 카드 |
| 02 GLOSSARY | raw_event/event_card, Redis Stream(XADD/XREADGROUP/XACK/PEL), worker/agent-worker 분리 |
| 03 DATA FLOW | 13단계 e2e (RSS→raw_events→stream→정규화→LangGraph→card→색인→화면) |
| 04 BACKEND/DB | FastAPI + PostgreSQL(raw_events, event_cards) + Alembic 0001~0003 |
| 05 COLLECTOR/QUEUE/WORKER | 수집·분석·API 분리 철학, heartbeat, reconciler |
| 06 LLM/RAG/SEARCH | LangGraph 11노드(real 5/mock 6), Milvus+OpenSearch, LLMClient 추상화 |
| 07 FRONTEND | Next.js 11라우트, admin token 서버 격리 |
| 08 DOCKER/ENV | 10 컨테이너, healthcheck 5종, 포트 바인딩 보안 |
| 09 STATUS | 13/13 DONE, 108 테스트 PASS (STEP 011 기준) |
| 10 STUB/MOCK/TODO | mock 8 + partial + TODO. 환경변수 전환표 |
| 11 ROADMAP | 4축(A RAG / B 수집확장 / C 본문 / D Agent loop) |
| 12 FILE MAP | 역할별 파일 인덱스 |

### 11.1 system_overview의 stale 여부 (왜곡 방지)

- **09 문서는 STEP 011(2026-05-24) 기준**이다. 그 이후 `ingestion/`의 대규모 작업(44 CORE_READY, closing round, docs 정리)이 진행되었다.
- **09 문서가 묘사하는 "수집 소스 3개(RSS)"는 시스템 B 기준으로는 여전히 사실**이다(workers/collectors). 즉 stale가 아니라 **두 시스템이 별개**라서 그렇다.
- **system_overview는 "ingestion/ 44 소스"를 모른다.** 이 둘을 잇는 것이 오케스트레이션의 일이며, 그 결과로 09/11 문서의 "축 B 수집 확장"이 실현된다.
- ⚠️ **왜곡 금지**: system_overview의 "11노드 중 6 mock"을 "완성"으로 적지 말 것. 그것은 별도 STEP 014 대상이다.

---

## 12. 구현에 필요한 기존 함수/파일 경로 (요약 인덱스)

| 목적 | 경로:심볼 |
|---|---|
| 단일 소스 수집 | `ingestion/fetch_strategies/collection_probe.py:run_collection_probe` |
| 전략 루프 | `ingestion/fetch_strategies/strategy_runner.py:run_fetch_strategy_loop` |
| 실패 분류 | `ingestion/fetch_strategies/failure_classifier.py:classify_failure` |
| 본문 추출 | `ingestion/fetch_strategies/article_body_extractor.py:extract_article_body` |
| rate-limit store | `ingestion/core/rate_limit_store.py:get_store` |
| health store | `ingestion/core/source_health.py:get_health_store` |
| 큐(브리지) | `ingestion/pipeline/event_queue.py:EventQueue` |
| 소스 레지스트리 | `ingestion/core/source_registry.py:load_registry` |
| artifact | `ingestion/core/artifact_store.py` |
| 다운스트림 입구 | `workers/collectors/rss_collector.py` (참조: raw_event 생성 패턴) |
| 다운스트림 큐 | `workers/queue/producer.py` (XADD stream:raw_events) |

---

## 13. 모호한 지점 (UNKNOWN / 확인 필요)

| # | 항목 | 상태 |
|---|---|---|
| U-1 | `rate_limit_policy.py`의 cache_key/is_cached/record_call vs `rate_limit_store.py`의 get_store 관계 | plans/012 §3는 policy.py 기준, 코드 분석은 store.py 기준 — **구현 시 실제 인터페이스 재확인 필요** |
| U-2 | `run_one_source.py`/`run_phase.py`가 `get_compiled_graph()`를 직접 호출하는지 | 라인 미정독 — UNKNOWN |
| U-3 | 다운스트림 `raw_event_service.create_raw_event` 정확한 시그니처 | system_overview 흡수로만 파악 — 코드 직접 확인 필요 |
| U-4 | worker 컨테이너에 chromium 설치 여부 | 미확인 (plans/012 §1 전제조건) |
| U-5 | 루트 `gcp-service-account-key.json`의 gitignore 여부 | **보안 확인 필요(12 문서)** |

---

## 14. Agent Committee Review

| agent | 피드백 | status |
|---|---|---|
| source-ingestion-engineer | insertion point 6지점 정확. run_collection_probe 인터페이스 안정 | CLOSED_BY_DESIGN |
| orchestrator-architect | 두 시스템 지도가 설계의 출발점. 브리지(insertion #3)가 핵심 | CLOSED_BY_DESIGN |
| docs-memory-curator | system_overview stale 아님 — "별개 시스템" 해석이 정확 | CLOSED_BY_DESIGN |
| adversarial-reality-critic | U-1~U-5 UNKNOWN을 숨기지 않은 점 양호. 구현 전 해소 필수 | USER_CONFIRMATION_REQUIRED |
| test-validation-agent | 13/13 readiness + 509/108 기준선이 회귀 측정 기준 | CLOSED_BY_TEST_PLAN |
| security-permission-guardian | U-5(gcp 키) 즉시 점검 | USER_CONFIRMATION_REQUIRED |

---

## 15. Risk Closure

| risk | cause | impact | detection | mitigation | validation | status |
|---|---|---|---|---|---|---|
| 인터페이스 오인(U-1) | policy.py vs store.py 혼동 | 잘못된 diff | 구현 전 grep 확인 | 11 문서 diff에 "VERIFY PATH" 표기 | grep으로 함수 위치 확인 | DEFERRED_WITH_TRIGGER(구현 직전) |
| system_overview 왜곡 | mock을 완성으로 오기 | 잘못된 상태 보고 | 문서 교차검증 | 11.1에 명시 | grep "11노드" 일관성 | CLOSED_BY_DESIGN |
| gcp 키 노출(U-5) | 루트 secret 파일 | 자격증명 유출 | gitignore/scan | 사람 점검 | scan_secrets | USER_CONFIRMATION_REQUIRED |

---

## 16. Commercialization Impact

이 audit의 상업적 함의는 단순하다: **이미 만든 44개 소스 수집 자산은 "연결만 하면" 즉시 제품 가치가 된다.** 추가 수집 개발 없이, 브리지 하나로 사건 카드의 소스 다양성이 14배(3→44)로 늘어난다. 이것이 가장 비용 대비 효과가 큰 다음 작업임을 audit이 입증한다.

---

## 17. USER_CONFIRMATION_REQUIRED

| question | why it matters | default recommendation | blocking? |
|---|---|---|---|
| U-1 rate-limit 인터페이스를 구현 전 grep으로 확정? | diff 정확성 | 예, Phase B 직전 확인 | No(구현 트리거) |
| U-5 gcp 키가 gitignore에 있는가? | 자격증명 유출 | 즉시 확인 | Yes(보안) |
| U-4 worker chromium 설치? | Playwright 소스 주기 수집 | Phase G 전 설치 | Phase G |

> 다음 문서: `02_SOURCE_ROLE_AND_PURPOSE_ROUTING.md` (소스 특징별 목적 라우팅).
