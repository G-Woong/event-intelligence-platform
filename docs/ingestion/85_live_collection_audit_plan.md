# 85. Live Collection Audit 라운드 계획

- 작성일: 2026-06-13
- 선행 라운드: docs/74~84 (pre-orchestration risk closure — pytest 450 passed, CORE_READY 44)
- 후속 라운드: plans/012 (Celery 오케스트레이션)

## 1. 라운드 목표

"소스가 살아있다(LIVE_SUCCESS)"와 "수집 데이터를 이벤트 큐 seed/확장 수집에 쓸 수 있다"는 다른 문제다.
이번 라운드는 Celery 오케스트레이션 전에:

1. **1차 source(seed 감지)** — 주기적으로 호출해 "지금 무슨 일이 일어나는가" 후보(seed)를 만들 수 있는지 live 검증.
2. **2차 source(enrichment)** — 1차에서 나온 키워드/주제(query)로 확장 수집이 가능한지 live 검증.
3. 소스별 **호출 제한·운영 주기·데이터 품질·용도**를 실측 기반으로 확정.
4. **반복 수집 시뮬레이션**으로 rate limit/cache/cooldown/health 게이트가 실제로 동작하는지 검증.

## 2. 제외 범위 (이번 라운드에서 구현하지 않음)

- 정규화/canonical event 병합/랭킹.
- 웹 게시, LLM 기사 생성, 원문 재게시.
- Celery/Redis/production scheduler — 짧은 in-process 시뮬레이션 runner만.
- DB migration (EventSeedCandidate는 **문서 제안만**).

## 3. 1차/2차 source 정의

| 구분 | 정의 | 입력 | 출력 |
|------|------|------|------|
| 1차 (primary_seed) | query 없이 주기 호출 → 신규 사건 후보 감지 | 없음(고정 endpoint/feed) | title/keyword + url + timestamp → EventSeedCandidate |
| 2차 (enrichment) | 1차 seed 키워드/대분류 query로 확장 수집 | query 문자열 | 관련 문서/검색결과 → evidence 확장 |
| both | 주기 seed + query enrichment 둘 다 가능 | 선택적 query | 양쪽 | 

both 후보: gdelt, sec_edgar, youtube (query 지원 + 주기 호출 가능). opendart/federal_register는 파라미터형(날짜/조건) lookup.

## 4. 검증 대상 목록

### 1차 seed audit 대상 (비검색, ~40개)
- 뉴스 11: bbc, ap_news, techcrunch, the_verge, zdnet_korea, etnews, yna, hankyung, maekyung, aljazeera, cnbc
- 커뮤니티 4: hacker_news, product_hunt, youtube, dcinside
- 공식 7: gdelt, opendart, sec_edgar, bok_ecos, eia, federal_register, eu_press_corner
- 트렌드 3: google_trending_now, signal_bz, loword (+ google_trends_explore는 `--include-trends-explore` 시 ≤1회)
- 시장 6: finnhub, twelve_data, alpha_vantage, polygon, coinbase_market, binance_market
- 도메인 9: kma, tour, its, kofic, tmdb, kopis, aladin, igdb, culture_info

### 2차 enrichment audit 대상
- 검색: serper, tavily, exa, naver_news_search, naver_blog_search (budget 4)
- quota 민감 뉴스 API: gnews, newsapi, guardian, nyt (budget 2)
- 공식 query형: gdelt, sec_edgar (budget 2), youtube/tmdb (budget 1~2)
- query 미지원(고정/파라미터형): kofic, kopis, aladin, kma, its, tour, culture_info, eu_press_corner, bok_ecos, eia 등 → live 재호출 없이 `query_unsupported` + 1차 결과 참조 평가

### 호출 금지 (audit 제외)
krx_kind(DEFERRED_SPECIAL_ROUND), reddit(MVP_DEFERRED), x/blind/reuters/fmkorea/google_programmable_search(MVP_EXCLUDED).

## 5. 호출 제한·주의사항

| 소스 | 제한 | 이번 라운드 사용량 |
|------|------|--------------------|
| alpha_vantage | 25/day | 1 |
| newsapi | 100/day | 1차 0 + 2차 2 |
| nyt | 500/day | 2 |
| guardian | 5000/day | 2 |
| gnews | 100/day | 2 |
| finnhub | 60/min | 1차 1 + 시뮬레이션 ≤3 |
| tmdb | ~100/hr | 1차 1 + 2차 ≤2 |
| gdelt | min_interval 5s, cache ttl 900s | 준수 (cache_skip은 dedup 검증 사례) |
| google_trends_explore | min_interval 7200s, 429 이력 | 기본 off, gate 통과 시 ≤1회, 루프 재시도 금지 |

## 6. Live 호출 원칙

1. 소스당 1회 원칙 (2차는 소스별 query budget 내).
2. 호출 전 gate: health should_skip → in_cooldown → is_cached. skip 시 네트워크 호출 없이 `audit_action`으로만 기록.
3. 호출 후 record_call (Route 1은 rate limit 게이트가 없으므로 runner 책임).
4. min_interval_seconds는 runner의 in-process sleep으로 강제.
5. CAPTCHA/Turnstile/login/paywall 우회 금지(terminal BLOCKED 그대로 기록).
6. 키 값 출력/로그/문서 저장 금지 — NAME·존재 여부만.
7. sample은 title 120자/snippet 200자 절단 — 원문 전문 복사 금지.

## 7. 반복 수집 검증 방식 (시뮬레이션)

- 8개 소스 × 2 cycle (최대 3), cycle 간 sleep 10s, `INGESTION_RATE_LIMIT_BACKEND=local_file` (process env만, `.env` 미수정).
- 검증 항목 5종:
  1. cache hit 소스는 2번째 cycle에서 `cache_skip` + artifacts_new == 0 (중복 수집 없음).
  2. RATE_LIMITED 발생 소스는 다음 cycle에서 cooldown_skip.
  3. `outputs/state/rate_limit_cache.json`에 호출 키 존재 (재기동 생존).
  4. health store에 cycle별 상태 누적.
  5. 실패 소스는 next_action 기록.

## 8. 성공/실패 기준

| 항목 | PASS 기준 |
|------|-----------|
| query 주입 | 기존 450 테스트 무수정 통과 + live 1회에서 query 반영 확인 |
| 1차 audit | 대상 소스 전부 record 생성(호출 또는 skip 사유), seed_ready 판정 산출 |
| 2차 audit | budget 내 (source, query) 전 조합 record + relevance 판정 |
| 시뮬레이션 | 검증 항목 5종 판정 기록 |
| 테스트 | pytest 전체 실패 0 |
| 보안 | scan_secrets PASS, env hygiene 기록 |

소스 단위 실패(NETWORK_ERROR 등)는 라운드 실패가 아니라 next_action과 함께 기록 대상.

## 9. 산출물 목록

| 산출물 | 경로 |
|--------|------|
| 계획 | docs/ingestion/85 (본 문서) |
| 역할 분류 매트릭스 | docs/ingestion/86 |
| limit/frequency 프로파일 | docs/ingestion/87 |
| 1차 live audit 보고 | docs/ingestion/88 + outputs/jsonl·reports/primary_seed_live_audit_* |
| 2차 live audit 보고 | docs/ingestion/89 + outputs/jsonl·reports/enrichment_live_audit_* |
| 시뮬레이션 보고 | docs/ingestion/90 + outputs/jsonl·reports/periodic_collection_simulation_* |
| Event Queue Readiness | docs/ingestion/91 (EventSeedCandidate schema 제안 포함) |
| MVP 수집 주기 초안 | docs/ingestion/92 |
| 최종 보고 | docs/ingestion/93 |
| 마스터 갱신 | docs/ingestion/70~73 |

## 10. 단계별 체크리스트

- [ ] Step 0: 본 문서 + pytest 기준선(450 passed) 확인
- [ ] Step 1: query 주입 (api_probe 메타 + `_apply_query_override` + 시그니처 + collection_probe 2줄 + test_query_injection.py) → 전체 pytest + naver live 1회
- [ ] Step 2: `_audit_common.py` + test_audit_common.py (네트워크 없음)
- [ ] Step 3: docs/86, 87 (live 호출 전 분류/프로파일)
- [ ] Step 4: run_primary_seed_live_audit.py + live 실행 + docs/88
- [ ] Step 5: run_enrichment_live_audit.py + live 실행 (hot seed + 대분류) + docs/89
- [ ] Step 6: run_periodic_collection_simulation.py + live 실행 + docs/90 + test_audit_runners.py
- [ ] Step 7: docs/91 (readiness + schema 제안), docs/92 (frequency draft)
- [ ] Step 8: pytest/env hygiene/secret scan + docs/70~73 갱신 + docs/93 + 최종 보고(§13, A/B/C 판정)

## 11. 예상 diff 요약 (파일별)

| 구분 | 파일 | 내용 |
|------|------|------|
| 수정 | `ingestion/probes/api_probe.py` | `_PROBE_SPEC`에 `query_param`/`query_in` 메타(기존 9+α, 신규 gnews/guardian/nyt), `_apply_query_override` (deepcopy), `run_api_live_probe(..., query=None)` 확장 |
| 수정 | `ingestion/fetch_strategies/collection_probe.py` | Route 1에 `query=query`, Route 3에 `query=query or ""` 전달 (2줄) |
| 신규 | `ingestion/runners/_audit_common.py` | runner 3종 공유 헬퍼 |
| 신규 | `ingestion/runners/run_primary_seed_live_audit.py` | 1차 seed audit runner |
| 신규 | `ingestion/runners/run_enrichment_live_audit.py` | 2차 enrichment audit runner |
| 신규 | `ingestion/runners/run_periodic_collection_simulation.py` | 주기 수집 시뮬레이션 runner |
| 신규 | `ingestion/tests/unit/test_query_injection.py` `test_audit_common.py` `test_audit_runners.py` | 단위 테스트 (전부 네트워크 없음) |
| 신규 | docs/ingestion/85~93 | 본 라운드 문서 9편 |
| 갱신 | docs/ingestion/70~73 | audit 실측 반영 |

### 주의 (설계 함정)
1. `_apply_query_override`는 **deepcopy 필수** — `_PROBE_SPEC` 모듈 전역 오염 방지.
2. skip/cached는 `PROBE_STATUS`에 신규 literal을 추가하지 않고 record의 `audit_action` 필드로만 기록.
3. Route 1(API)은 rate limit 게이트가 없음 — runner가 gate_check + enforce_min_interval + record_call 수행.
4. 1차/시뮬레이션은 `cache_key(source_id, "")`를 공유 — gdelt(ttl 900s) cache_skip은 dedup 검증 성공 사례.
5. gnews/guardian/nyt entry 신설로 `--all-safe` 및 collection_probe Route 1 거동이 변함 (기존: default spec/Route 3) — docs에 명시.
6. Windows cp949 — 콘솔 출력은 errors="replace", 파일은 UTF-8.

## 12. 기준선

- 2026-06-13 pytest: **450 passed, 2 warnings** (`.venv` Python 3.11.9).
