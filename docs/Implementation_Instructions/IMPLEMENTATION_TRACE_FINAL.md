# IMPLEMENTATION_TRACE_FINAL — 소스 연결 Closing 라운드 통합 trace

- 최종 갱신: 2026-06-13 (UTC)
- 목적: 흩어진 지시문(00~10) + 진행 문서의 **적용 완료 상태를 하나의 trace로 통합**한다.
  신규 에이전트가 상태를 오해하지 않도록 단일 출처를 제공한다. 원본 지시문은 삭제하지 않고
  APPLIED/SUPERSEDED 배너로 보존한다.
- 읽는 순서: **이 문서 → docs/ingestion/70·86·92 → runner_orchestration_readiness JSONL**.

## 1. 프로젝트 목표 / 원래 문제

- 목표: 전세계 실시간 사건/이벤트 인텔리전스. 다양한 소스에서 사건을 수집·정규화·랭킹하여
  신뢰가능한 실시간 인텔리전스를 제공한다. (정보 제공이지 투자 조언 아님.)
- 원래 문제(Closing 라운드 진입 시점): 소스별 connectivity는 점검됐으나
  "살아있다(LIVE_SUCCESS)"와 "이벤트 큐 seed/확장으로 쓸 수 있다"가 분리돼 있었고,
  gdelt 429·ap_news endpoint 폐기·newsapi 헤드라인 한정·google_trends_explore 429·
  Playwright Route 2 selector 결함·API partial 필드 누락 등 잔여 결함이 있었다.

## 2. 수집 pipeline 요약

- **Route 1 (API)**: `api_probe.run_api_live_probe` — `_PROBE_SPEC` per-source 메타 + query 주입(`_apply_query_override`, deepcopy). 429 시 `record_rate_limited`로 cooldown 영속.
- **Route 2 (Playwright)**: `playwright_probe.run_playwright_probe` — site_spec selector/wait 적용, `_detect_429`(error_taxonomy 단일 출처), 본문 cascade.
- **Route 3 (fetch strategy loop)**: RSS/HTML 폴백.
- **공통**: `collection_probe.run_collection_probe`가 라우팅. rate limit gate(`gate_check`: health→cooldown→cache), artifact store(raw/rendered/extracted), 본문 추출 cascade(site_selector→trafilatura→readability→dom_heuristic).

## 3. 01~15 checklist 최종 상태

집계: **PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1** (수정 가능 코드 결함 0건).

| # | 항목 | 최종 상태 | 핵심 근거 |
|---|------|----------|----------|
| 1 | RISK-T04 Route1 429 cooldown | PASS | `record_rate_limited`+`next_retry_at` 기록. test_route1_rate_limit_record 5 |
| 2 | gdelt | **PASS (live collected)** | gate 통과 live LIVE_SUCCESS items=3 + body 1. min_interval 60s 전제 |
| 3 | ap_news | PASS | Google News RSS 프록시, LIVE_SUCCESS 100건 |
| 4 | newsapi | PASS | `/v2/everything` 전환, relevance high |
| 5 | google_trends_explore | **CONFIRMED_EXTERNAL_RATE_LIMIT** | 정품 429(robot.png). optional_enrichment + **fallback chain**으로 비차단 |
| 6a~6d | loword/trending_now/dcinside/eu_press_corner selector | PASS | Route 2 위임 결함 수정, 실데이터 |
| 7 | signal_bz 보강 | PASS | keyword 10 + rank |
| 8 | dcinside 검색 영구 path | PASS | search_url→a.tit_txt→본문 .write_div |
| 9 | federal_register fields | PASS | fields[] 5종, body 1 |
| 10a/10b | igdb 날짜·url / culture_info 날짜 | PASS | $root/epoch, _XML_FIELD_NAMES |
| 11 | hacker_news detail | PASS | detail 2차 호출, title+url+time |
| 12 | bok_ecos/eia/its 샘플 매핑 | PASS | _SAMPLE_PATHS, signal_ready |
| 13 | 시장 numeric_signal 분류 | PASS | NUMERIC_SIGNAL_SOURCES, seed_ready_label_for |
| 14 | 장문 query 절단 | PASS | truncate_query |
| 15 | 의존성/기법 흡수 | PASS | check_dependency_readiness 14 READY, feed_discovery, error_taxonomy 기법10 |

## 4. 조건부/Playwright/API E2E 결과 (01~05 / 06·07 / 08·09)

- **01~05 조건부 E2E**: `run_conditional_sources_e2e_audit.py` — gdelt/ap_news/newsapi 등 sample→candidate→(URL 시) 본문 추출. extract_body cascade + force_local_file_backend.
- **06/07 Playwright selector E2E**: `run_playwright_selector_sources_audit.py` — 5종 collected 5/5, candidates 90, body 2(dcinside). page-title fallback 0.
- **08/09 API partial/no E2E**: `run_api_partial_sources_audit.py` — 8종 collected 8/8, candidates 12, numeric_signals 10, body 2. DEFERRED_NEEDS_KEY 0.
- **10 최종감사**: `run_external_rate_limit_recheck.py`(gdelt PASS / trends RATE_LIMITED_CONFIRMED), enrichment live audit(33 live collected, body 3), secret FP CLOSED, runner readiness.

## 5. Google Trends Explore 429 + fallback chain (이번 라운드 추가)

- **역할 3분할**: Google Trends(제품명) / google_trending_now(primary trend seed, PASS) / google_trends_explore(optional_enrichment, CONFIRMED_EXTERNAL_RATE_LIMIT).
- **정책 고정**: explore = min_interval 7200s / cooldown 3600s / **max_retries_on_429=0** / body_status=not_required / 실패 시 collected=false + fallback chain. (test_trend_fallback.py)
- **fallback chain** (`run_trend_fallback_enrichment_audit.py`):
  - A google_trending_now(Playwright) — trend ≥3, cooldown이면 직전 artifact.
  - B google_trends_trending_now_export — 공개 RSS `trends.google.com/trending/rss?geo=` **EXPORT_AVAILABLE 실측**(없으면 EXPORT_UNAVAILABLE, A 유지).
  - C 뉴스/검색 enrichment — serper/tavily/naver(+영문 시 exa/gnews/newsapi/guardian/ap_news) → `extract_related_candidates` 규칙 기반 related expansion. URL 시 본문 ≥1.
  - 실측(20260613_102354): collected fallback 5, aggregate related 19, body 1, explore RATE_LIMITED_CONFIRMED. **우회 0건**.

## 6. GDELT 최종 PASS 판정

- live LIVE_SUCCESS items=3 실기사 + body 676자. 빠른 연속 호출만 soft-429(200+평문 "limit requests to one every 5 seconds").
- 정책 min_interval 60s / cooldown 900s — 근거(GDELT 공식 블로그 무수치 + 커뮤니티 5s)보다 보수적. UA 필수 충족.

## 7. Agent orchestration runner map

`run_runner_orchestration_readiness.py` 실측 = **13/13 agent_ready**.

| runner/tool | 종류 | JSONL prefix |
|---|---|---|
| run_primary_seed_live_audit | CLI | primary_seed_live_audit_ |
| run_enrichment_live_audit | CLI | enrichment_live_audit_ |
| run_conditional_sources_e2e_audit | CLI | conditional_sources_e2e_audit_ |
| run_playwright_selector_sources_audit | CLI | playwright_selector_sources_e2e_audit_ |
| run_api_partial_sources_audit | CLI | api_partial_sources_e2e_audit_ |
| run_external_rate_limit_recheck | CLI | external_rate_limit_recheck_ |
| **run_trend_fallback_enrichment_audit** | CLI | **trend_fallback_enrichment_audit_** |
| run_structure_explorer | CLI | structure_explorer_ |
| run_runner_orchestration_readiness | CLI | runner_orchestration_readiness_ |
| check_dependency_readiness / scan_secrets | CLI(stdout JSON) | — |
| feed_discovery / url_resolver / article_body_extractor | library | — |

## 8. Artifact map (outputs/)

- `raw_payload/<source>/`, `raw_signal/<source>/`, `rendered_dom/<source>/`, `screenshots/<source>/`, `extracted_payload/<source>/`, `extracted_text/<source>/`
- `jsonl/` audit 결과 (위 prefix), `reports/` MD 리포트, `state/rate_limit_cache.json`(local_file backend cooldown 영속).
- `outputs/**`는 `.gitignore`로 커밋 제외. evidence 경로·크기·SHA256·재생성 명령은 **`docs/ingestion/artifact_manifest_final.md`**(단일 매니페스트)에 기록.

## 9. 테스트 / secret scan / env

- pytest: **635 passed**(직전 627 + trend fallback 8). 0 fail.
- secret scan: **verdict=PASS, WARNING 0, 실제 leak 0**. false positive 종결 방식 — openai_key URL slug(좁은 엔트로피 판별), `access_token = func(...)` 코드참조(따옴표 리터럴은 그대로 WARNING), 테스트 fixture(`# pragma: allowlist secret`, Layer1만 면제). `sk-*` 전체 무시 아님. Layer2 BLOCKED(.env 값 누출)는 pragma로도 미억제.
- env hygiene: AMBIGUOUS_ALIAS 6건(기준선, 기능 영향 없음). 실제 키 값 미노출.

## 10. 남은 외부 조건

- **google_trends_explore = CONFIRMED_EXTERNAL_RATE_LIMIT**: Google 공식 quota 부재 + IP 429. 재개=cooldown 윈도우 후 1회(local_file backend). 단, optional이며 fallback chain으로 대체되므로 event queue 비차단. **이것이 유일한 외부 이월**.
- 수정 가능한 코드/selector/mapping/계약 gap = **0건**.

## 11. 다음 단계

- **plans/012**: Celery + Redis 비동기 수집/랭킹 오케스트레이션, LangGraph 이벤트 추론 그래프.
- 후속: google_trends_trending_now_export 정식 registry 온보딩, 기법 6(sitemap 백필)·8(self-healing)·11(LLM judge) 본격 구현, EventSeedCandidate → canonical 정규화/병합(docs/91 schema 제안).

## 부록 A. 라운드 실행 순서·방법론 (ROADMAP.md 흡수, 적용 완료)

기존 `ROADMAP.md`(00~10 턴별 실행 지시서)의 방법론을 여기로 흡수한다. ROADMAP.md는 deprecated stub으로 축약됨.

- **적용 순서(의존)**: 00(체크리스트 세팅) → 01(Route1 429 cooldown 안전장치) → 09§1(의존성 readiness) → 02(gdelt+장문 query 절단) → 03(ap_news) → 04(newsapi everything) → 05(trends_explore 역할) → 08(API partial #9~#13) → 06(structure explorer) → 07(Playwright 5종 Route2 위임) → 09 나머지(기법 흡수+프레임워크 결정) → 10(최종 감사).
- **의존 근거**: 01은 모든 live 재검증의 안전장치; 02/05는 01에 의존(429 재발 가능); 06은 07의 도구; 09§1은 06/07의 전제(Playwright Chromium 런타임); 10은 01~09 완료 후 마지막.
- **소스 공통 루프 A→E**: A 직전 실패 재현 확인 → B raw/HTML/status/screenshot 증거 → C 최소 수정/대안 경로 → D 단위 테스트+전체 pytest+제한 live → E PASS/BLOCKED_TERMINAL/DEFERRED 판정. 소스당 최대 4회, "명령+핵심 출력+artifact/테스트 경로" 3종 증거 없는 PASS 금지.
- **안정성 서열(경로 승격 원칙)**: 공식 API > RSS/sitemap > 숨은 JSON/XHR > CSS selector > 본문 휴리스틱.
