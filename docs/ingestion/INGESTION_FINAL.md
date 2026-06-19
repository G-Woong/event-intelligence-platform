# docs/ingestion/INGESTION_FINAL.md — 수집 계층 최종 상태 (단일 출처)

> ⚠️ **수치 SUPERSEDED (2026-06-19):** 본 문서의 테스트/소스 기준선(**509 passed**, **44 CORE_READY / 58**)은 작성 시점 기록이며 **현재 권위 수치가 아니다.** 현재값 = `docs/_CANONICAL/09_VALIDATION_AND_TESTS.md`(ingestion **1293 passed**) · `docs/_CANONICAL/03_SOURCE_STATUS.md`(**46 PRODUCTION_READY / 57**). 충돌 대장: `_CANONICAL/06_CONFLICTS_AND_SUPERSEDED.md`(C-2). 본문은 수집 설계 근거로 보존한다.

- 최종 갱신: 2026-06-14
- 대체 문서: docs/ingestion/00~93 (91개 제거 → git history 보존)
- 근거: docs/70~73 (master), docs/84 (pre-orchestration risk closure), docs/86/92/93 (live audit final), IMPLEMENTATION_TRACE_FINAL.md
- 읽는 순서: **이 문서 → docs/Implementation_Instructions/IMPLEMENTATION_TRACE_FINAL.md → ingestion/outputs/jsonl/runner_orchestration_readiness_*.jsonl**

---

## 1. 최종 결론 (한 문장)

44개 소스가 CORE_READY로 실측 검증되었고, 오케스트레이션(plans/012) 진입 전 코드 결함은 0건이다.
수집 계층: **PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1** (google_trends_explore, fallback chain으로 비차단).
테스트: 509 passed 기준선 유지 + closing round 추가 테스트 전부 통과 (무회귀).

---

## 2. 소스 상태 최종표

| 분류 | 수 | 의미 |
|------|----|----|
| **CORE_READY** — 즉시 수집 가능 | **44** | live 실측으로 수집 확인. 즉시 파이프라인 연결 가능 |
| **READY_WITH_CAUTION** | **6** | 수집 가능, quota/약관/봇감지 모니터링 필요 |
| **DEFERRED_SPECIAL_ROUND** | **1** | krx_kind — open.krx.co.kr 공식 API 전환 필요 |
| **MVP_DEFERRED** | **1** | reddit — MVP 보류 (사용자 확정) |
| **MVP_EXCLUDED** | **5** | 구조적 장벽 (라이선스/로그인/봇 차단) |
| 내부 테스트 픽스처 | 1 | _dummy (운영 대상 아님) |
| **합계** | **58** | registry 57개 + YAML 미등록 google_trends_explore 1개 |

### CORE_READY 44 목록

```
문서/뉴스(10): bbc, ap_news, techcrunch, the_verge, zdnet_korea, etnews,
               yna, hankyung, maekyung, aljazeera
커뮤니티(3):   hacker_news, youtube, product_hunt
검색(6):       naver_news_search, naver_blog_search, serper, tavily, exa, gnews
공식 데이터(7): gdelt, sec_edgar, federal_register, opendart, bok_ecos, eia, eu_press_corner
트렌드(3):     signal_bz, google_trending_now, loword
시장(6):       finnhub, twelve_data, alpha_vantage, polygon, coinbase_market, binance_market
도메인(9):     kofic, igdb, tmdb, kopis, aladin, kma, tour, its, culture_info
```

### READY_WITH_CAUTION 6

```
cnbc, guardian, nyt, newsapi, dcinside, google_trends_explore
```

### MVP_EXCLUDED 5

```
x (유료 API), blind (login wall), reuters (라이선스+bot protection),
fmkorea (Cloudflare Turnstile — 우회 불가), google_programmable_search (CX 미설정)
```

---

## 3. 소스 역할 분류 (요약)

| 역할 | 소스 수 | 의미 | 대표 소스 |
|------|--------|------|---------|
| primary_seed | ~30 | 주기 호출로 사건 후보 감지 | yna, bbc, signal_bz, gdelt, finnhub, opendart |
| enrichment | ~10 | 1차 seed 발생 후 query 확장 수집 | serper, tavily, naver_news_search, guardian, nyt |
| both | ~5 | seed + enrichment 겸용 | gdelt, sec_edgar, youtube, federal_register |
| deferred | 1 | 별도 라운드 필요 | krx_kind |
| excluded | 6 | 구조적 장벽 (운영 제외, 코드 보존) | x, blind, reuters, fmkorea, reddit, google_programmable_search |

상세 분류표 원문: git history `docs/ingestion/86_source_role_classification_matrix.md`

---

## 4. 수집 주기 초안 (Celery beat 도입 전 provisional)

| bucket | 주기 | 소스 |
|---|---|---|
| **near_real_time** (5~15분) | yna, finnhub, binance_market, gdelt(**15분 고정**) |
| **short_interval** (30~60분) | bbc, ap_news, techcrunch, the_verge, zdnet_korea, etnews, hankyung, maekyung, aljazeera, cnbc, hacker_news, dcinside, opendart, sec_edgar, signal_bz, loword, naver_news_search, coinbase_market, twelve_data, kma, its |
| **medium_interval** (2~6시간) | google_trending_now(**2시간+ 고정**, min_interval 7200s), eu_press_corner(2~6h), serper/tavily/exa(**이벤트 트리거 전용**, 정기 폴링 금지) |
| **daily** (일 1회) | kofic, alpha_vantage(**25/day — 일 1회 고정**), polygon, federal_register, bok_ecos, eia, product_hunt, tmdb, kopis, aladin, igdb, culture_info, tour |
| **manual_or_deferred** | google_trends_explore(수동, gate 필수), krx_kind, reddit, x, blind, reuters, fmkorea |

### enrichment 일일 budget (정기 폴링 아님 — 1차 seed 트리거 시)

| source | 일일 query budget | 근거 |
|---|---|---|
| naver_news_search / naver_blog_search | ≤200 | 25,000/day 대비 1% 미만 |
| serper | ≤30 | 일회성 2500 크레딧 보존 |
| tavily / exa | ≤30 | 1000/month ≈ 33/day |
| guardian | ≤100 | 5000/day |
| nyt | ≤50 | 500/day |
| gnews / newsapi | ≤20 | 100/day |
| youtube(search) | ≤50 | 10,000 units/day |
| gdelt(query) | ≤20 + 15분 간격 | 429 실측 기준 |
| sec_edgar(entity query) | ≤50 | 10 req/s 공개 |

---

## 5. rate-limit 정책 (핵심 소스)

| source_id | min_interval | cooldown_on_429 | max_retries_on_429 | policy_note |
|---|---|---|---|---|
| gdelt | 60s | 900s | 1 | 공식 "rate limited" 수치 미공개. 보수 설정. UA 필수 |
| google_trends_explore | 7200s | 3600s | 0 | 공식 public API 없음. 429 확정(robot.png). 우회 불가 |
| google_trending_now | 7200s | 3600s | 0 | 동일 provider(Google Trends) 정책 |

근거 원문: `docs/ingestion/rate_limit_evidence.md`

---

## 6. Google Trends Explore — CONFIRMED_EXTERNAL_RATE_LIMIT

- **상태**: CONFIRMED_EXTERNAL_RATE_LIMIT. optional_enrichment. 이벤트 큐 비차단.
- **근거**: 실측 rendered DOM = 정품 `Error 429 Too Many Requests` + `images/errors/robot.png`. CAPTCHA 아님 → BLOCKED_TERMINAL 아님.
- **정책**: min_interval 7200s / cooldown 3600s / max_retries_on_429=0 / body_status=not_required
- **재개 조건**: gate 통과 후 `python -m ingestion.probes.playwright_probe --site google_trends_explore --query <hot seed> --region KR --rate-limit-backend local_file` 1회.
- **주의**: `--rate-limit-backend local_file` 필수 (memory backend는 프로세스 재시작 시 cooldown 소실).
- **fallback chain** (google_trends_explore 실패 시 자동 적용):
  - A: google_trending_now (Playwright) — trend ≥3, 쿨다운 시 직전 artifact 재사용
  - B: google_trends_trending_now_export — 공개 RSS `trends.google.com/trending/rss?geo={region}` (EXPORT_AVAILABLE 실측 2026-06-13)
  - C: 뉴스/검색 enrichment — serper/tavily/naver(+영문 시 exa/gnews/newsapi/guardian/ap_news) → `extract_related_candidates` 규칙 기반 related expansion
  - 실측 결과: collected fallback 5, aggregate related 19, body 1. **우회 0건**.

---

## 7. GDELT — PASS

- **상태**: PASS. CORE_READY. 15분 주기 고정.
- **근거**: live LIVE_SUCCESS items=3 실기사 + body 676자. 빠른 연속 호출만 soft-429(200+평문 "Please limit requests to one every 5 seconds").
- **정책**: min_interval 60s / cooldown 900s — 커뮤니티 통념(5s)보다 12배 보수적.
- **phrase quoting**: query를 GDELT에 보낼 때 따옴표 없이 전송 시 오류 텍스트 200 응답 → `_apply_query_override`에서 쿼리 전처리.

---

## 8. 수집 루프 API (runner 진입점)

| 함수/CLI | 파일 | 용도 |
|---|---|---|
| `run_collection_probe(source_id, force=False)` | `ingestion/fetch_strategies/collection_probe.py` | **최상위 진입점** — 3-way 라우팅 + health gate |
| CLI `run_collection_probe --source <id> [--json] [--force]` | `ingestion/runners/run_collection_probe.py` | 단일 소스 probe CLI |
| `run_api_live_probe(source_id)` | `ingestion/probes/api_probe.py` | API 소스 직접 호출 |
| `run_fetch_strategy_loop(source_id, url)` | `ingestion/fetch_strategies/strategy_runner.py` | 전략 루프 (per-source budget 적용) |
| `CloudBrowserLikeStrategy().fetch(url, source_id)` | `ingestion/fetch_strategies/cloud_browser_like.py` | Playwright 렌더링 |
| `SeleniumRenderStrategy().fetch(url)` | `ingestion/fetch_strategies/selenium_strategy.py` | Selenium fallback |
| `run_playwright_probe(site_id)` | `ingestion/runners/run_playwright_probe.py` | YAML selector probe |
| CLI `run_browser_runtime_check [--launch] [--strict]` | `ingestion/runners/run_browser_runtime_check.py` | 브라우저 런타임 점검 |
| CLI `scan_secrets --paths <...>` | `ingestion/tools/scan_secrets.py` | secret 유출 스캔 (exit 0/1/2) |

```python
# 오케스트레이션 진입 예시
from ingestion.fetch_strategies.collection_probe import run_collection_probe
result = run_collection_probe("gdelt", max_items=5)
print(result.status, result.items_found)  # LIVE_SUCCESS 3
```

### Celery 연결 포인트 (plans/012)

Celery worker가 꽂을 인터페이스 (이미 준비됨):
- `run_collection_probe` — 단일 소스 수집
- `get_store()` (redis backend) — rate limit store
- `get_health_store().list_due_for_retry()` — 재시도 대기 소스 목록

---

## 9. 수집 루프 흐름 (내부 구조)

```
run_collection_probe(source_id)
 ├─ health gate: BLOCKED_TERMINAL/쿨다운/격리/이월 → 네트워크 없이 즉시 반환
 ├─ Route 1 (API): _PROBE_SPEC 소스 → run_api_live_probe
 ├─ Route 2 (Playwright): playwright_required → CloudBrowserLikeStrategy
 ├─ Route 3 (전략 루프): 그 외 → strategy_runner (STRATEGY_SEQUENCE[0..9])
 │    ├─ 429 → record_rate_limited → deadline 영속 (backend에 따라 디스크/redis)
 │    └─ CAPTCHA/LOGIN/PAYWALL/ROBOTS → 즉시 BLOCKED_TERMINAL (terminal, 재시도 불가)
 └─ 모든 return 직전 health store 갱신 (성공 시 failure_count 리셋)
```

STRATEGY_SEQUENCE: [0]httpx_direct → [1]httpx_mobile_ua → [2]httpx_random_ua → [3]readability → [4]trafilatura → [5]dom_heuristic → [6]playwright_basic → [7]playwright_scroll → [8]playwright_wait_network_idle → [9]playwright_click_more

---

## 10. body 추출 정책

body cascade (우선순위 순): site_selector → trafilatura → readability → dom_heuristic

artifact store (9종, `.gitignore` 제외 — 커밋 안 함):
- raw_payload / rendered_dom / screenshots / extracted_text / raw_signal
- 재생성: `docs/ingestion/artifact_manifest_final.md` 참조

---

## 11. 금지 정책 (불변)

- **CAPTCHA/Turnstile/로그인/페이월 우회 금지** → 감지 시 BLOCKED_TERMINAL + health store 영속
- **proxy rotation / 내부 RPC scraping 금지**
- **provider rate limit 무시 연속 재시도 금지**
- **google_trends_explore를 PASS로 표기 금지** — CONFIRMED_EXTERNAL_RATE_LIMIT
- **google_programmable_search 재활성화 금지** (CX 미설정)
- **gdelt min_interval 60s 위반 금지** (cooldown 900s)
- **publication boundary**: 수집 경로 미연결. 기사 원문 재배포 경로는 게시 계층에서만 (docs/80)
- **secret 출력 금지**: `.env` 값은 존재/길이만 보고. 키 값 미기록 (scan_secrets 도구로 검증)

---

## 12. pre-orchestration risk closure 결과 (docs/74~84, 2026-06-12)

| RISK | 결과 | 주요 내용 |
|------|------|---------|
| 12-1 RateLimitStore pluggable | PASS | memory/local_file/redis 3종, 재기동 roundtrip 검증 |
| 12-2 Celery+Redis | **미구현 (의도)** | **plans/012** |
| 12-3 SourceHealthState + quarantine | PASS | 6상태 전이, gate 네트워크 미호출 |
| 12-4 browser runtime check | PASS | 러너 신설 + READY 실측 + Docker 문서 |
| 12-5 전략 복원력 회귀 테스트 | PASS | 14 tests, blocker 4종 즉시 terminal |
| 12-6 trends 429 영속 | PASS | Route 2 429 감지 + 매핑 테스트 |
| 12-7 publication boundary | PASS | yaml + 모듈, 수집 경로 미연결 가드 |
| 12-8 secret scan 도구 | PASS | 2계층 (baseline + 종료), exit code gate |
| 12-9 env hygiene | PASS | _ALIASES 일반화, MISMATCH/EMPTY 탐지. WARNING 6건(legacy alias, 기능 무영향) |
| 12-10 Phase 1 뉴스 6개 재프로브 | PASS | 6/6 LIVE_SUCCESS → CORE_READY 38→44 |

테스트 baseline (pre-orchestration risk closure 종료 시): 450 passed

---

## 13. closing round 결과 (docs/01~10 지시서, IMPLEMENTATION_TRACE_FINAL.md)

| # | 항목 | 최종 상태 |
|---|------|----------|
| 1 | Route 1 429 cooldown 기록 (RISK-T04) | PASS |
| 2 | gdelt | PASS (live LIVE_SUCCESS items=3, min_interval 60s 준수) |
| 3 | ap_news | PASS (Google News RSS 프록시, items=100) |
| 4 | newsapi | PASS (/v2/everything 전환) |
| 5 | google_trends_explore | **CONFIRMED_EXTERNAL_RATE_LIMIT** (fallback chain으로 비차단) |
| 6a~6d | selector 미매칭 4종 (loword/trending_now/dcinside/eu_press_corner) | PASS (Route 2 위임, 실데이터) |
| 7 | signal_bz 보강 | PASS (keyword 10 + rank) |
| 8 | dcinside 검색 영구 path | PASS (search_url→본문 e2e) |
| 9 | federal_register fields | PASS (url+publication_date+abstract) |
| 10a/10b | igdb 날짜/url / culture_info 날짜 | PASS |
| 11 | hacker_news detail 2차 호출 | PASS (title+url+time) |
| 12 | bok_ecos/eia/its 샘플 매핑 | PASS (_SAMPLE_PATHS) |
| 13 | 시장 numeric_signal 분류 | PASS (NUMERIC_SIGNAL_SOURCES) |
| 14 | 장문 query 절단 | PASS (truncate_query) |
| 15 | 의존성/기법 흡수 | PASS (14/14 READY, feed_discovery, error_taxonomy) |

**집계: PASS 14 / CONFIRMED_EXTERNAL_RATE_LIMIT 1**
pytest baseline 진입: **509 passed** → closing round 후 추가 테스트 전부 통과 (무회귀)
agent orchestration runner readiness: **13/13 agent_ready**

---

## 14. event queue readiness (docs/91 요약)

| category | 수 |
|---|---|
| seed_ready (즉시 이벤트 큐 seed 가능) | 21 |
| enrichment_ready (query 확장 가능) | 9 |
| caution (수집 가능, 모니터링 필요) | 8 |
| not_ready (추가 정비 필요) | 7 |

EventSeedCandidate 최소 필드: title_or_keyword, source_url, timestamp

---

## 15. 사용자 액션 (선택 — 기능 영향 없음)

**A-1. `.env` legacy alias 6건 개명** (hygiene 경고 해소, 기능 정상 동작 중):
- `CLIENT_ID` → `NAVER_CLIENT_ID`
- `CLIENT_SECRET` → `NAVER_CLIENT_SECRET`
- `ECOS_API_KEY` → `BOK_ECOS_API_KEY`
- `GOOGLE_API_KEY` → `GOOGLE_CUSTOM_SEARCH_API_KEY`
- `CSE_CX` → `GOOGLE_CUSTOM_SEARCH_CX`
- `CULTURE_INFO_KEY` → `CULTURE_INFO_API_KEY`
- 검증: `python -m ingestion.tools.check_env_hygiene` → AMBIGUOUS_ALIAS 0건

**A-5. rate limit backend를 local_file로 전환** (재기동 후 cooldown 유지):
`INGESTION_RATE_LIMIT_BACKEND=local_file` 설정 또는 `--rate-limit-backend local_file` CLI 플래그

---

## 16. 다음 단계

**plans/012 Celery/LangGraph 오케스트레이션 구현**

Celery worker 연결 준비 완료 인터페이스:
- `run_collection_probe` — 단일 소스 수집 진입점
- `get_store()` (redis backend) — rate limit store (Celery에서 redis 연결 시 자동 사용)
- `get_health_store().list_due_for_retry()` — 재시도 대기 소스 목록

수집 주기 초안: §4 참조 (Celery beat에 rate_limit_policy.yaml과 정합한 cache_ttl 추가 필요)

---

## 17. 흡수된 문서 (2026-06-14 정리)

| 범위 | 파일 수 | 내용 |
|---|---|---|
| docs/ingestion/00~66 | 67 파일 | 순차 audit/report — 70~73으로 통폐합 완료 (2026-06-12) |
| docs/ingestion/70~73 | 4 파일 | master docs — 이 파일로 흡수 |
| docs/ingestion/74~84 | 11 파일 | pre-orchestration risk closure |
| docs/ingestion/85~93 | 9 파일 | live collection audit |
| **합계** | **91 파일** | git history에서 검색 가능 |

git history 검색: `git log --all -- docs/ingestion/` 또는 `git show <hash>:<path>`
