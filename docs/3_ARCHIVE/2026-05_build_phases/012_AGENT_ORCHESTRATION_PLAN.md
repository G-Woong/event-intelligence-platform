# plans/012 — Agent Orchestration 구현 PLAN (Celery+Redis 주기 수집)

**작성일**: 2026-06-12
**성격**: 구현 PLAN — 이 문서 자체는 코드를 포함하지 않으며, 다음 구현 라운드의 설계 기준이다.
**전제**: docs/70~73 (2026-06-12 실측 라운드) 완료 상태. CORE_READY 38 + CAUTION 6 소스, per-source budget 구현 완료, 테스트 359 통과.
**해소 대상 리스크**: RISK-O01(주기 수집 없음), RISK-T02(rate_limit 캐시 휘발), RISK-F01(장애 격리 없음), RISK-R02(일일 quota 카운터 없음).

---

## §0. 목표 (한 문장)

CORE_READY+CAUTION 44개 소스를 Celery beat 스케줄로 주기 수집하되, 이번 라운드에 밝혀진 모든 사실(per-source budget, 전략 분기, RATE_LIMITED cooldown, BLOCKED terminal, 소스별 quota)을 스케줄러가 그대로 흡수해 동작하게 한다.

## §1. 인프라 전제 (기존 자산 활용)

- `docker-compose.dev.yml`에 **redis / worker / agent-worker 서비스가 이미 정의돼 있다** — 신규 컨테이너 불필요.
- Celery broker/backend: 기존 `REDIS_URL` env 키 재사용 (`redis://redis:6379/0` 계열). DB 분리: broker=db0, rate_limit 캐시=db1, 재시도 큐=db2 권장.
- **전제조건 (RISK-D01/P01)**: worker 이미지에 `playwright install chromium` 추가 — Playwright 경로 소스(eu_press_corner, signal_bz, loword, dcinside, google_trending_now) 수집에 필수. Selenium fallback까지 원하면 Chrome 설치 추가.

## §2. 주기 수집 설계 (Celery beat)

### 2.1 소스 계층별 스케줄 그룹

| 그룹 | 소스 (대표) | 주기 | 근거 |
|------|------------|------|------|
| fast_signal | signal_bz, google_trending_now, loword | 30~120분 | Google 계열 IP 차단 위험(RISK-R01) — min_interval 준수 |
| market_signal | finnhub, twelve_data, polygon, coinbase, binance | 5~15분 | 시세 신호; alpha_vantage만 일 25 req → **1일 주기 별도** |
| document_discovery | bbc, ap_news, techcrunch, the_verge, cnbc | 30분 | 뉴스 기사 발행 주기 |
| search_enrichment | naver_news/blog, serper, tavily, exa, gnews, guardian | on-demand + 1시간 | 쿼리 기반 — event 후보가 생길 때 호출이 주, 주기 호출은 보조 |
| official_evidence | gdelt, sec_edgar, federal_register, opendart, bok_ecos, eia | 1시간 | 공시·통계 갱신 주기 |
| domain_signal | kofic, tmdb, kopis, aladin, igdb, kma, tour, its, culture_info | 6~24시간 | 일 단위 데이터 (박스오피스·날씨·공연) |
| caution 그룹 | newsapi(일 100), nyt(일 500), guardian(일 5000) | **daily quota guard 필수** | §6 참조 |

### 2.2 task 구조

- `collect_source(source_id)` 단일 Celery task가 `run_collection_probe(source_id)`를 호출 — 기존 3-way 라우팅(API/Playwright/strategy loop)을 그대로 재사용. 신규 수집 코드를 만들지 않는다.
- 소스당 task 격리(RISK-F01): 한 소스 실패가 다른 소스에 영향 없음. `acks_late=True` + `task_time_limit=300s`(Playwright 소스는 600s).
- 결과는 기존 `append_result_row()` jsonl + `EventQueue.enqueue()`(§7)로 이중 기록.

## §3. rate_limit 캐시 Redis 백엔드 교체 (RISK-T02 해소)

`ingestion/core/rate_limit_policy.py`는 이미 교체 친화적 구조다 — `cache_key()` / `is_cached()` / `record_call()` 3개 함수가 인터페이스의 전부이고, 호출처(`strategy_runner.py`)는 이 함수만 사용한다.

### 설계

1. **인터페이스 불변**: 함수 시그니처(`source_id, query`) 그대로 유지. 기존 테스트·호출처 무수정.
2. 내부 저장소를 전략 패턴으로 분기:
   - `REDIS_URL` 설정 + redis 접속 성공 → Redis 백엔드: 키 `rate_limit:{source_id}:{query_hash}`, 값=서버 epoch, `SETEX`로 TTL=`cache_ttl_seconds` 자동 만료. `is_cached()`는 `EXISTS` 1회.
   - 미설정/접속 실패 → 현행 프로세스 로컬 dict로 **자동 폴백** (개발·테스트 동일 동작 보장).
3. `time.monotonic()` → Redis 서버 시각 기반으로 전환 (워커 간 시계 정합).
4. min_interval 보호: `record_call`을 `SET key NX EX interval`로 바꾸면 "동시 두 워커가 같은 소스 호출" 경쟁도 원자적으로 차단된다.
5. **검증 기준**: (a) 단위 테스트 — fakeredis로 is_cached/record_call/TTL 만료, 폴백 경로; (b) 통합 — 워커 2개에서 google_trends_explore 연속 호출 시 두 번째가 cached로 skip; (c) 기존 `test_rate_limit_policy.py` 회귀 0.

## §4. RATE_LIMITED cooldown → 재시도 큐

현행: `strategy_runner`가 429 시 프로세스 안에서 `time.sleep(cooldown)` — 워커 슬롯을 점유한 채 대기한다 (Celery에서 비효율).

### 설계

1. probe 결과의 `cooldown_seconds` / `next_retry_at`(이미 ProbeResult에 필드 존재)을 사용해, task는 **즉시 반환**하고 Redis sorted set `retry_queue`(score=`next_retry_at` epoch)에 `{source_id, query, reason}`을 적재.
2. 분 단위 beat task `drain_retry_queue`: `ZRANGEBYSCORE retry_queue 0 now`로 만기 항목을 꺼내 `collect_source.delay()` 재발행.
3. 재시도 상한: 소스당 연속 RATE_LIMITED N회(기본 3) 초과 시 cooldown을 지수 증가(600s→1800s→7200s)시키고 WARNING 로그 — IP 차단 예방.
4. strategy loop 내부 sleep은 "단일 프로세스 모드" 폴백으로 유지 (Celery 환경 변수로 분기).

## §5. BLOCKED terminal 소스 자동 격리·재점검

1. 소스가 BLOCKED(CAPTCHA/LOGIN_WALL/PAYWALL/ROBOTS) 판정되면 Redis `source_quarantine` hash에 `{source_id: {first_seen, count, last_error}}` 기록 → beat 스케줄에서 **자동 제외** (스케줄러가 매 tick에 quarantine 조회).
2. 재점검 주기: 격리 소스는 주 1회 단일 probe만 발행. 2회 연속 성공 시 자동 복귀, 4주 연속 BLOCKED면 registry `status` 갱신 제안 리포트 생성 (자동 수정은 하지 않음 — 사람 승인).
3. MVP_EXCLUDED/MVP_DEFERRED(x, blind, reuters, fmkorea, google_programmable_search, reddit)는 처음부터 스케줄 대상에서 제외 — registry `status` 필드를 스케줄러가 읽는다.

## §6. per-source budget·전략 분기·quota를 스케줄러가 활용하는 방식

- **budget**: 스케줄러는 budget을 건드리지 않는다 — `run_fetch_strategy_loop`가 `retry_policy.yaml` `per_source:`를 이미 자체 적용(2026-06-12 구현). 신규 Playwright-heavy 소스 추가 시 YAML 한 줄이 전부.
- **전략 분기**: EXTRACTION_EMPTY→playwright 점프, RSS playwright-skip, Selenium gate 전부 strategy loop 내장 — task 레이어는 `run_collection_probe` 호출만.
- **daily quota guard (RISK-R02)**: Redis 카운터 `quota:{source_id}:{YYYYMMDD}` INCR + 자정 TTL. 한도(yaml `daily_quota` 신규 필드: newsapi=90, nyt=450, guardian=4500, alpha_vantage=20 — 한도의 90% 수준)를 초과하면 해당 소스 task를 그날 skip.
- **수집 우선순위**: Celery 큐 분리 — `q_fast`(market/fast_signal), `q_default`(news/official), `q_browser`(Playwright 소스, 동시성 2 제한 — CPU 보호).

## §7. `ingestion/pipeline/` stub과의 연결 지점

| stub 모듈 | 연결 방식 |
|-----------|----------|
| `event_queue.py` (`EventQueue`) | **유일하게 동작하는 stub** — Redis Stream 우선 + JSONL 폴백 구현 완료. `collect_source` task가 수집 결과를 `enqueue()` — Redis 모드에서 worker 간 공유 큐가 된다 |
| `discovery_collector.py` | Celery task 그룹 "document_discovery 주기 수집"의 본체로 구현 (현재 NotImplementedError) |
| `event_candidate_extractor.py` | EventQueue consumer로 구현 — 수집 항목에서 이벤트 후보 추출 (LLM, 후속 라운드) |
| `query_generator.py` | 이벤트 후보 → search_enrichment 쿼리 생성 (on-demand 호출 트리거) |
| `search_enrichment_collector.py` | 생성된 쿼리로 serper/tavily/exa/naver 호출하는 task |
| `canonical_event_builder.py` | 최종 정규화 — normalization 라운드(범위 밖) |

LangGraph(`agents/graph.py` `get_compiled_graph`)는 단건 소스 추론 경로로 유지 — Celery task가 노드 단위로 graph를 invoke하는 구조는 event_candidate 라운드에서 결정.

## §8. 구현 순서와 단계별 검증 기준

| 단계 | 작업 | 검증 기준 |
|------|------|----------|
| 1 | Celery app + `collect_source` task + q_default 큐 | 로컬 worker 1개로 gdelt 1회 수집 → jsonl 기록 확인 |
| 2 | rate_limit Redis 백엔드 (§3) | fakeredis 단위 테스트 + 워커 2개 중복 호출 차단 + 기존 테스트 회귀 0 |
| 3 | beat 스케줄 (그룹별 주기, §2) | 1시간 dry-run: 스케줄 발행 로그에 quota/quarantine 제외 반영 확인 |
| 4 | 재시도 큐 (§4) | google_trends_explore 강제 429 시나리오 — sleep 없이 task 반환 + 만기 후 재발행 |
| 5 | 격리·복귀 (§5) | fmkorea(BLOCKED 확정 소스)로 격리 동작 확인, 스케줄 제외 확인 |
| 6 | daily quota guard (§6) | newsapi 카운터 90 도달 시 skip 로그 |
| 7 | q_browser + Docker chromium (§1) | 컨테이너 안에서 eu_press_corner LIVE_SUCCESS |
| 8 | EventQueue Redis Stream 연결 (§7) | enqueue→dequeue 왕복, JSONL 폴백 회귀 |

각 단계는 atomic — 단계별로 pytest 회귀 0 + secret scan PASS를 완료 조건으로 한다.

## §9. 범위 밖 (이 PLAN에서도 다루지 않음)

- normalization/event_candidate LLM 추론 구현 (별도 라운드)
- KRX 공식 API 연동 (사용자 키 발급 후 — docs/73 A-2)
- Kubernetes/프로덕션 배포 토폴로지
- `.env` 직접 수정
