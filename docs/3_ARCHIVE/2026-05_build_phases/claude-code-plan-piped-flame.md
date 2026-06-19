# Live Collection Audit 라운드 (docs/85~93 + runner 3종 + query 주입)

## Context (왜 하는가)

직전 라운드(docs/74~84)로 수집 인프라 리스크는 닫혔다(450 tests, CORE_READY 44). 그러나 "소스가 살아있다(LIVE_SUCCESS)"와 "수집 데이터가 이벤트 큐 seed/확장 수집으로 쓸 수 있다"는 다른 문제다. 이번 라운드는 Celery 오케스트레이션(plans/012) 전에, **1차 source(seed 감지)와 2차 source(enrichment)를 실제 live 호출로 검증**하고 소스별 호출 제한·운영 주기·데이터 품질·용도를 확정한다. 정규화/병합/게시/LLM 생성은 구현하지 않는다.

## 탐색으로 확정한 사실 (설계 전제)

- **중대 gap**: `run_api_live_probe()`(api_probe.py)에 query 파라미터가 없고 `_PROBE_SPEC`에 검색어가 하드코딩("breaking news"/"테스트"/"samsung") → 2차 enrichment audit이 불가능. **query 주입이 선행 구현 항목.**
- `gnews/guardian/nyt`는 `_PROBE_SPEC`에 **없음** (default spec으로 떨어짐) → entry 신설 필요.
- Route 1(API)에는 rate limit 게이트가 없음 (`is_cached/in_cooldown`은 Route 2/3에만) — `min_interval_seconds`/`max_calls_per_run`은 로드만 되고 어디서도 강제 안 됨 → **audit runner 레벨에서 gate+record_call 수행**.
- `run_fetch_strategy_loop`는 이미 `query=""` 파라미터 보유 — collection_probe Route 3에서 전달만 안 함 (1줄 수정).
- `run_collection_probe.py`의 `_enrich_from_raw_payload`는 xml/html만 처리 — JSON 응답 sample 추출기 필요.
- `cache_key(source_id, query)`가 query 포함 → 1차(query 없음)와 2차(query별)는 캐시 충돌 없음. 1차와 시뮬레이션은 같은 key 공유 → gdelt(ttl 900s)는 시뮬레이션에서 cache_skip이 나올 수 있고 이는 **dedup 검증 성공 사례**.
- 호출 금지 소스: krx_kind(DEFERRED_SPECIAL_ROUND), reddit(MVP_DEFERRED), x/blind/reuters/fmkorea/google_programmable_search(MVP_EXCLUDED).
- quota 민감: alpha_vantage 25/day, newsapi 100/day, nyt 500/day, guardian 5000/day, gnews 100/day, finnhub 60/min, tmdb ~100/hr.

## 하드 제약 (불변)

- 키 값 출력/로그/문서 저장 금지(NAME·존재여부만). `.env` 수정 금지. rm/Remove-Item/reset/clean/push 금지.
- CAPTCHA/Turnstile/login/paywall 우회 금지(terminal BLOCKED). google_trends_explore 즉시 반복 호출 금지.
- Celery/Redis/production scheduler 구현 금지 — 짧은 시뮬레이션 runner만.
- 원문 전문을 보고서에 길게 복사 금지 — sample은 title 120자/snippet 200자 절단.
- canonical event 병합·웹 게시·LLM 기사 생성·원문 재게시 구현 금지.

---

## 작업 순서

### Step 0 — docs/85 계획 문서 작성

`docs/ingestion/85_live_collection_audit_plan.md`: 라운드 목표/제외 범위/1차·2차 source 정의/검증 대상 목록/소스별 예상 역할/호출 제한·주의사항/live 호출 원칙/반복 수집 검증 방식/성공·실패 기준/산출물 목록 + **단계별 체크리스트 + 예상 diff 요약(파일별)**.
- 검증: pytest 기준선 450 passed 확인.

### Step 1 — query 주입 (최소 diff, 기존 450 테스트 무수정 통과)

**수정 `ingestion/probes/api_probe.py`:**
- `_PROBE_SPEC` per-source 메타 2키 추가: `query_param`(파라미터명), `query_in`(`"params"`|`"json_body"`, 기본 params). `_build_request`는 모르는 키를 무시하므로 기존 테스트 무영향.
  - 기존 entry 수정 9개: naver_news_search(`query`), naver_blog_search(`query`), youtube(`q`), gdelt(`query`), sec_edgar(`q`), newsapi(`q`), serper(`q`/json_body), tavily(`query`/json_body), exa(`query`/json_body). tmdb(`query`), federal_register, opendart도 지원 가능하면 추가.
  - 신규 entry 3개: gnews(`q`, meaningful_fields=["articles"]), guardian(`q`, ["response.results"]), nyt(`q`, ["response.docs"]).
- 순수 헬퍼 `_apply_query_override(probe_spec, query) -> dict`: **deepcopy 필수** (in-place 수정 시 모듈 전역 `_PROBE_SPEC` 오염 → 배치 루프에서 이전 query 잔류). `query_param` 없으면 원본 반환.
- `run_api_live_probe(..., query: Optional[str] = None)` 시그니처 확장(하위호환) + 반환 ProbeResult에 query 채움.

**수정 `ingestion/fetch_strategies/collection_probe.py`** (2줄):
- Route 1: `run_api_live_probe(source_id, max_calls=1, query=query)`.
- Route 3: `run_fetch_strategy_loop(..., query=query or "")`.

**신규 테스트** `ingestion/tests/unit/test_query_injection.py`: params/json_body/메타없음 3분기, `_PROBE_SPEC` 불변(deepcopy), Route 1 query 전달(monkeypatch kwargs 캡처), gnews/guardian/nyt entry 존재.
- 검증: 전체 pytest + live 1회 `run_collection_probe --source naver_news_search --query "삼성전자" --json` → sample_title에 query 반영 확인.

### Step 2 — 공통 헬퍼 `ingestion/runners/_audit_common.py`

runner 3개가 공유 (중복 3벌 방지):
- `AUDIT_EXCLUDED_IDS` frozenset(krx_kind, reddit, x, blind, reuters, fmkorea, google_programmable_search) + status 제외 필터.
- `load_audit_sources(layers=None)` — source_registry.yaml 기반 소스 목록 로드+필터.
- `evaluate_event_seed_fields(item) -> (count, fields)` — title/url/timestamp/source_id/snippet 중 충족 수. 3+ = seed_ready.
- `relevance_score(query, title, snippet) -> float` — 영문 토큰 매칭 + 한글 2-gram substring, 0.0~1.0.
- `extract_sample_items(source_id, artifact_path, max_samples=3)` — json/xml/html 분기. JSON은 `_SAMPLE_PATHS` per-source 매핑(serper organic[].title/link/snippet, tavily results[], naver items[], guardian response.results[], nyt response.docs[], gdelt articles[], youtube items[].snippet 등). title 120자/snippet 200자 절단.
- `gate_check(source_id, query="") -> Optional[str]` — health should_skip → in_cooldown → is_cached 순. skip 사유는 record의 **`audit_action` 필드**("called"/"cache_skip"/"cooldown_skip"/"health_skip"/"query_unsupported")로만 기록 — **PROBE_STATUS frozenset에 신규 literal 추가 금지** (skip 시 ProbeResult를 만들지 않는다).
- `enforce_min_interval(source_id, last_called)` — min_interval_seconds in-process sleep (코드 gap 보완).
- `write_audit_jsonl/write_audit_md/audit_timestamp` — UTF-8 기록, 콘솔은 errors="replace".

**신규 테스트** `ingestion/tests/unit/test_audit_common.py` (전부 네트워크 없음): seed 필드 경계(2/3개/빈문자열), relevance 한/영, 소스 필터, JSON sample 추출(소스별 fake payload), 절단 규칙.

### Step 3 — 분류/프로파일 문서 (live 호출 전)

- `docs/ingestion/86_source_role_classification_matrix.md` — **전체 소스(제외 포함) 누락 없이**. 필수 컬럼: source_id, source_name, layer, role(primary_seed/enrichment/both/deferred/excluded), collection_method, expected_input, expected_output, minimum_required_fields, recommended_frequency, quota_or_rate_limit_notes, final_audit_priority.
  - both 예: gdelt/sec_edgar/opendart/federal_register(주기 seed + query enrichment), youtube/tmdb/igdb.
- `docs/ingestion/87_source_limit_and_frequency_profile.md` — 필수 컬럼: source_id, role, quota_type(unknown/per_minute/per_day/per_month/site_policy/browser_risk), known_limit, observed_limit_signal, current_rate_policy, recommended_mvp_frequency, recommended_max_items, burst_allowed, cooldown_strategy, risk_level, notes. **모르면 UNKNOWN + conservative 제안**. 근거: registry rate_limit_summary, rate_limit_policy.yaml, docs/80 quota, 429 이력(google_trends).

### Step 4 — Runner (a) 1차 seed audit + live 실행

**신규** `ingestion/runners/run_primary_seed_live_audit.py`:
- CLI: `--layers` (기본: search_enrichment 제외 전 layer) `--sources` `--max-items 3` `--respect-rate-limit`(기본 on — 스펙 호환용 플래그) `--dry-run` `--include-trends-explore`(기본 off).
- 소스당: gate_check → enforce_min_interval → `run_collection_probe(source_id, max_items)` → record_call → sample ≤3 추출 → seed 필드 평가.
- record: source_id, layer, audit_action, status, strategy_used, items_found, samples, seed_ready(yes/no/partial), seed_field_coverage, error_category, next_action, elapsed_sec.
- 출력: `ingestion/outputs/jsonl/primary_seed_live_audit_{ts}.jsonl` + `ingestion/outputs/reports/primary_seed_live_audit_{ts}.md`.

**live 실행**: 비검색 1차 소스 ~38개 × 1회 (뉴스 10 + cnbc, 커뮤니티 3 + dcinside, 공식 7, 트렌드 3, 시장 6, 도메인 9). google_trending_now/signal_bz/loword는 gate 통과 시만. google_trends_explore는 `--include-trends-explore`로 cooldown 확인 후 ≤1회.

**문서** `docs/ingestion/88_primary_seed_live_collection_audit.md` — 필수 표: source_id, status, items_found, event_seed_ready, minimum_fields_present, sample_title_or_keyword, sample_url_exists, timestamp_exists, artifact_exists, recommended_frequency, next_action.

### Step 5 — Runner (b) 2차 enrichment audit + live 실행

**신규** `ingestion/runners/run_enrichment_live_audit.py`:
- CLI: `--queries` `--from-primary <1차 jsonl>` `--sources` `--max-items 3` `--respect-rate-limit` `--dry-run`.
- query set: **A. hot seed** — 1차 결과에서 트렌드 keyword 3 + 뉴스 title/topic 3 + 시장/공식 signal 2 (총 5~8개). **B. 대분류** — 한글 10종(정치/국제 분쟁/경제 위기/주식 급등/AI 반도체/기후 재난/문화 콘텐츠/영화 박스오피스/교통 사고/공공 안전) + 영문 8종(politics/global conflict/economic crisis/stock surge/AI semiconductor/climate disaster/box office/public safety). 전체 set을 정의하되 **소스별 budget으로 샘플링 배정** (어떤 query가 어디 갔는지 기록).
- 소스별 query budget: serper/tavily/exa/naver_news_search/naver_blog_search = 4 (seed 2 + 대분류 2), gnews/newsapi/guardian/nyt = 2 (quota 민감), gdelt/sec_edgar = 2, youtube/tmdb = 1~2. 한글 query는 영문 전용 소스에 배정하지 않음(한글 포함 여부로 라우팅).
- query 미지원 소스(kofic/kopis/aladin/kma/its/tour/culture_info/eu_press_corner/bok_ecos/eia 등 고정 endpoint): live 재호출 없이 `audit_action="query_unsupported"` + 1차 결과 참조로 enrichment 용도 평가 (파라미터형 lookup으로 분류).
- (source, query)별: gate_check(query 포함 key) → run_collection_probe(query=...) → record_call → relevance_score 집계(relevance: high≥0.5/medium≥0.2/low/unknown).
- 출력: `enrichment_live_audit_{ts}.jsonl/.md`.

**문서** `docs/ingestion/89_enrichment_source_live_audit.md` — 필수 표: source_id, query_type(seed_based/category_based), query, status, items_found, relevance, minimum_fields_present, sample_title, sample_url_exists, published_at_exists, source_is_useful_for_expansion, recommended_usage, next_action.

### Step 6 — Runner (c) 주기 수집 시뮬레이션 + live 실행

**신규** `ingestion/runners/run_periodic_collection_simulation.py`:
- CLI: `--sources` `--cycles 2`(최대 3) `--sleep-seconds 10` `--respect-rate-limit` `--dry-run`.
- 기본 subset 8개: signal_bz, loword, serper, naver_news_search, gdelt, federal_register, **finnhub**(alpha_vantage 25/day라 제외), kma. google_trends 계열 제외.
- 시작 시 `os.environ.setdefault("INGESTION_RATE_LIMIT_BACKEND", "local_file")` — store 첫 사용 전. `.env` 미수정.
- cycle × source: gate_check(cache hit → cache_skip 기록 = 검증 포인트) → run_collection_probe → record_call. 호출 전후 raw_payload 파일 수 snapshot → `artifacts_new` (cache_skip 시 0 = 중복 없음 검증). cycle마다 health store 상태 기록.
- 종료 후 검증 섹션: cache_skip 소스 artifacts_new==0, RATE_LIMITED 소스는 다음 cycle cooldown_skip, `outputs/state/rate_limit_cache.json`에 키 존재, health 누적, 실패 소스 next_action 기록.
- 출력: `periodic_collection_simulation_{ts}.jsonl/.md`.

**문서** `docs/ingestion/90_periodic_collection_simulation_report.md` (cycle × source 표 + 검증 항목 5종 판정).

**신규 테스트** `ingestion/tests/unit/test_audit_runners.py`: runner 3개 main()을 tmp_path + monkeypatch(run_collection_probe/is_cached/in_cooldown/health store 주입)로 — jsonl/md 생성, cache_skip 분기, query budget 절단, cycle 반복, query_unsupported 분기. runner는 **모듈 레벨 import** 유지(monkeypatch 가능하게).

### Step 7 — 평가/주기 문서

- `docs/ingestion/91_event_queue_readiness_assessment.md` — 평가 기준 10종(seed 가능 소스 수/최소 필드 충족률/timestamp·source_url·title 존재율/중복 가능성/hint 존재/2차 query 생성 가능성/운영 주기/정규화 gap). 필수 출력: event_queue_ready_sources, enrichment_ready_sources, caution_sources, not_ready_sources, required_schema_before_normalization + **EventSeedCandidate schema 제안**(seed_id/source_id/source_layer/title_or_keyword/snippet/source_url/observed_at/published_at/country_hint/category_hint/entity_hints/evidence_level/raw_artifact_path/collection_status — 문서 제안만, DB migration 금지).
- `docs/ingestion/92_mvp_collection_frequency_draft.md` — bucket: near_real_time(5~15분)/short_interval(30~60분)/medium_interval(2~6시간)/daily/manual_or_deferred. 실측+quota 기반, 추측은 `provisional` 표시.

### Step 8 — 통합 검증 + 문서 갱신 + 최종 보고

```powershell
.\.venv\Scripts\python.exe -m pytest ingestion\tests -q                  # 450 + 신규, 실패 0
.\.venv\Scripts\python.exe -m ingestion.tools.check_env_hygiene --env-path .env
.\.venv\Scripts\python.exe -m ingestion.tools.scan_secrets --paths ingestion\outputs docs\ingestion plans
```
- **갱신**: docs/70(소스 status에 audit 실측 반영), docs/71(신규 리스크/이슈), docs/72(query 주입 + audit runner 아키텍처), docs/73(runner 사용법, docs/85~93 링크, 인수인계 갱신).
- **신규** `docs/ingestion/93_live_collection_audit_final_report.md` + 사용자 최종 보고(§13 형식: 한 줄 결론/1차 결과/2차 결과/seed→enrichment 연결/대분류 검증/주기 수집 가능성/Event Queue Readiness/권장 주기/실패·주의 소스/테스트·보안/판정 A·B·C).

---

## Live 호출 예산표 (소스당 1회 원칙 + budget)

| 단계 | 대상 | 호출수 | 비고 |
|------|------|--------|------|
| 1차 seed audit | 비검색 1차 ~38개 × 1 | ~38 | alpha_vantage 1/25, trends_now·explore gate 선확인 |
| 2차 enrichment | serper·tavily·exa·naver×2 × 4 query | 20 | |
| 2차 (quota 민감) | gnews·newsapi·guardian·nyt × 2 | 8 | newsapi 2/100, nyt 2/500 |
| 2차 (공식/도메인 query형) | gdelt·sec_edgar × 2, youtube·tmdb × 1~2 | ~7 | gdelt min_interval 5s 준수 |
| 시뮬레이션 | 8 소스 × 2 cycle | ≤16 (cache_skip로 실호출 ~12) | local_file backend |
| **합계** | | **~90** | 전 소스 quota의 10% 미만 |

실행 순서: 1차 → hot query 도출 → 2차 → 시뮬레이션 (gdelt 등 cache 공유는 dedup 검증 사례로 기록).

## 신규/수정 파일 요약

| 구분 | 경로 |
|------|------|
| 수정 | `ingestion/probes/api_probe.py` (query 메타 + `_apply_query_override` + 시그니처), `ingestion/fetch_strategies/collection_probe.py` (2줄) |
| 신규 | `ingestion/runners/_audit_common.py`, `run_primary_seed_live_audit.py`, `run_enrichment_live_audit.py`, `run_periodic_collection_simulation.py` |
| 신규 테스트 | `test_query_injection.py`, `test_audit_common.py`, `test_audit_runners.py` |
| 신규 문서 | docs/ingestion/85~93 (9편) |
| 갱신 문서 | docs/ingestion/70~73 |

## 주요 함정

1. `_apply_query_override`는 deepcopy 필수 — `_PROBE_SPEC` 전역 오염 방지 (불변 테스트로 고정).
2. PROBE_STATUS frozenset 강제 — skip/cached는 ProbeResult가 아닌 record의 `audit_action`으로만.
3. Route 1 무게이트 — rate limit 준수는 runner 책임 (gate_check + enforce_min_interval + record_call).
4. health store 부작용 — MISSING_KEY/NETWORK_ERROR 반복 시 failure_count 누적·격리. 같은 날 재실행 시 health_skip은 정상.
5. 1차/시뮬레이션 cache key 공유(query="") — gdelt ttl 900s로 cache_skip 가능 = dedup 검증 성공으로 분류.
6. runner의 run_collection_probe는 모듈 레벨 import (monkeypatch 가능).
7. Windows cp949 — 콘솔 errors="replace", 파일은 UTF-8.
8. gnews/guardian/nyt entry 신설 부수효과 — `--all-safe` 거동 변화는 docs에 명시 (기존 테스트 미참조 확인됨).
9. google_trends_explore — in_cooldown/is_cached 선확인, 기본 off, 루프 내 재시도 절대 금지.
10. 뉴스/html 소스 sample 0건은 실패가 아니라 `update_selector` next_action.

## 종료 조건 (사용자 §12 체크리스트)

1차/2차 분류 완료, 소스별 역할·expected output 정리, limit/frequency profile, 1차 live audit, 2차 live audit(seed 기반 + 대분류 기반), periodic simulation, rate limit/cooldown/health 동작 검증, event queue readiness 평가, EventSeedCandidate schema 제안, frequency draft, secret scan PASS, env hygiene 기록, pytest 통과, 신규 runner 실행 결과 기록, docs/85~93 생성, docs/70~73 갱신 — 전부 PASS/PARTIAL/FAILED/BLOCKED/DEFERRED/UNKNOWN으로 명시. 미충족 항목에 "완료" 표기 금지. 최종 보고는 §13 형식, 마지막 문장은 A/B/C 판정.
