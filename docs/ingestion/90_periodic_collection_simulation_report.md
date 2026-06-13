# 90. Periodic Collection Simulation Report (주기 수집 시뮬레이션)

- 실행: 2026-06-12 17:39 UTC (`run_periodic_collection_simulation --cycles 2 --sleep-seconds 10`)
- backend: `INGESTION_RATE_LIMIT_BACKEND=local_file` (process env만 설정 — `.env` 미수정)
- 산출물: `ingestion/outputs/jsonl/periodic_collection_simulation_20260612_173955.jsonl`, `ingestion/outputs/reports/periodic_collection_simulation_20260612_173955.md`
- 대상 8개: signal_bz, loword, serper, naver_news_search, gdelt, federal_register, finnhub, kma (alpha_vantage는 25/day quota로 제외, google_trends 계열은 429 이력으로 제외)

## 1. cycle × source 결과

| cycle | source_id | audit_action | status | artifacts_new | health_state |
|---|---|---|---|---|---|
| 1 | signal_bz | called | LIVE_SUCCESS | 0* | HEALTHY |
| 1 | loword | called | LIVE_SUCCESS | 0* | HEALTHY |
| 1 | serper | called | LIVE_SUCCESS | 2 | HEALTHY |
| 1 | naver_news_search | called | LIVE_SUCCESS | 2 | HEALTHY |
| 1 | gdelt | **cache_skip** | - (네트워크 호출 없음) | 0 | RATE_LIMITED_COOLDOWN→유지 |
| 1 | federal_register | called | LIVE_SUCCESS | 2 | HEALTHY |
| 1 | finnhub | called | LIVE_SUCCESS | 2 | HEALTHY |
| 1 | kma | called | LIVE_SUCCESS | 1 | HEALTHY |
| 2 | signal_bz | called | LIVE_SUCCESS | 0* | HEALTHY |
| 2 | loword | called | LIVE_SUCCESS | 0* | HEALTHY |
| 2 | serper | called | LIVE_SUCCESS | 2 | HEALTHY |
| 2 | naver_news_search | called | LIVE_SUCCESS | 2 | HEALTHY |
| 2 | gdelt | **cache_skip** | - | 0 | 유지 |
| 2 | federal_register | called | LIVE_SUCCESS | 2 | HEALTHY |
| 2 | finnhub | called | LIVE_SUCCESS | 2 | HEALTHY |
| 2 | kma | called | LIVE_SUCCESS | 1 | HEALTHY |

\* playwright 소스(signal_bz/loword)는 raw_payload/rendered_dom 카운트 대상 디렉토리에 신규 파일이 잡히지 않음 — artifact는 screenshot 경로로 저장되는 경로 차이. 수집 자체는 LIVE_SUCCESS. (artifact 카운터 보완은 후속 과제, 기능 결함 아님)

## 2. 검증 항목 5종 판정

| # | 검증 항목 | 판정 | 관찰 |
|---|---|---|---|
| 1 | cache_skip 소스 artifacts_new == 0 (중복 수집 없음) | **PASS** | gdelt cache_skip 2건 전부 artifacts_new 0 — **1차 audit(17:31) 호출의 cache(ttl 900s)가 시뮬레이션(17:39~)까지 유지되어 dedup 동작 실증** (docs/85 함정 5의 "검증 성공 사례") |
| 2 | RATE_LIMITED 소스는 다음 cycle cooldown_skip | **N_A** | 시뮬레이션 중 RATE_LIMITED 발생 없음. 단, gdelt가 2차 audit에서 429 후 이번 라운드 내 gate(cache_skip)로 차단된 것이 동등한 보호 동작 |
| 3 | `outputs/state/rate_limit_cache.json`에 호출 키 존재 (재기동 생존) | **PASS** | called 7개 소스 키 7/7 존재 — local_file backend 영속 확인 |
| 4 | health store 상태 누적 | **PASS** | called 소스 전부 health 기록 보유 (HEALTHY, failure_count 리셋) |
| 5 | 실패 소스 next_action 기록 | **N_A** | 시뮬레이션 중 실패 소스 없음 (16회 중 called 14회 전부 LIVE_SUCCESS) |

## 3. 해석

1. **반복 수집 시 인프라 게이트가 의도대로 동작** — cache ttl 보유 소스(gdelt)는 재호출이 차단되고 artifact 중복이 발생하지 않는다. ttl이 없는 소스는 매 cycle 호출된다(현 정책: 대부분 cache_ttl 0 — 운영 주기 확정 시 ttl을 docs/92 주기에 맞춰 설정 권장).
2. **process 재기동을 넘는 rate limit 상태 영속 확인** — 1차 audit(별도 프로세스)의 gdelt 호출 기록이 시뮬레이션 프로세스에서 읽혀 cache_skip을 유발 (local_file backend 계약 충족, plans/012 Redis 전환 시 동일 인터페이스).
3. **429 → cooldown 경로의 한계 발견**: Route 1(API)의 429는 `record_rate_limited`(rate limit store) 기록 없이 health store에만 RATE_LIMITED_COOLDOWN으로 남고, **next_retry_at이 비어 should_skip이 작동하지 않는다** (playwright 경로는 기록함). 이번에는 gdelt cache ttl이 대신 보호했다. → **신규 리스크: Route 1 429 시 record_rate_limited 호출 추가 필요** (docs/71 등재, plans/012 전 수정 권장).
4. cycle당 8소스 처리 시간 ~40s (playwright 2개 포함) — 짧은 주기 운영의 병목은 playwright 렌더링.
