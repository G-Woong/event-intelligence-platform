# 07 — REDIS / QUEUE / CACHE / STREAM LAYER (L4)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🟡 PARTIAL — B 다운스트림 Redis Stream + DLQ는 실구현·배선·라이브. A→B EventQueue 배선·Celery·quota가 잔여.
> │ **구현순위:** #3 (00_ROADMAP_INDEX) · **그룹:** A
> │ **검증 근거:** B = `workers/queue/producer.py`(XADD `stream:raw_events`)·`workers/queue/consumer.py`(XREADGROUP+xack `group:ingest`)·`workers/queue/dlq.py`(`route_failure`/`reap_pending` 실구현)·`workers/tests/test_dlq_reaper.py`. A = `ingestion/pipeline/event_queue.py` `_redis_enqueue/_dequeue/_peek/_mark_done` **4메서드 모두 실구현**(XADD/XREADGROUP/XRANGE/XACK — `NotImplementedError` 아님). 라이브: `ingestion/tests/integration/test_p0_redis_publish.py`.
> │ **잔여(미구현):** A `EventQueue`(stream:ingestion_eventqueue) → B `stream:raw_events` **배선**, Celery(beat/tasks/retry_queue), quota_guard(설계만), DLQ 알림 자동화, expansion_router 재유입 경로.
> │ **완료정의(DoD):** A `enqueue()` → B `group:ingest` 소비·xack → raw_events PG e2e green, PEL→DLQ 회수, content_hash dedup collapse, AOF 내구성, quota_guard 동작, 1517 green 유지.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: B(다운스트림)는 Redis Stream(producer XADD / consumer XREADGROUP+heartbeat) + DLQ(`route_failure`/`reap_pending`)가 **이미 실구현·배선·라이브**다. A측 `EventQueue`의 Redis 경로(`_redis_*` 4메서드)도 **실구현돼 있다**(자체 durable 백엔드 `stream:ingestion_eventqueue`). 핵심 P0 잔여는 새 stream을 만드는 게 아니라 **A의 출력을 B의 P0 통합 stream(`stream:raw_events`)에 배선**하고, Celery 스케줄·quota_guard를 얹는 것이다. 조합은 Celery(스케줄/디스패치) + Redis Streams(소비/durability) 하이브리드.

---

## 1. 현재 상태

| 컴포넌트 | 상태 | 근거 |
|---|---|---|
| B producer `stream:raw_events` XADD | IMPLEMENTED | `workers/queue/producer.py` |
| B consumer `group:ingest` XREADGROUP+xack | IMPLEMENTED | `workers/queue/consumer.py` |
| B DLQ `route_failure`/`reap_pending` | **IMPLEMENTED·라이브** | `workers/queue/dlq.py`, `workers/tools/run_dlq_reaper.py`, `workers/tests/test_dlq_reaper.py` |
| heartbeat healthcheck(60s) | IMPLEMENTED | compose worker/agent-worker |
| AOF `appendonly yes` | IMPLEMENTED | compose redis |
| A `EventQueue` Redis 경로 `_redis_*` 4메서드 | **IMPLEMENTED** | `ingestion/pipeline/event_queue.py` — XADD/XREADGROUP/XRANGE/XACK 실구현(자체 stream `stream:ingestion_eventqueue`). **`NotImplementedError` 아님** |
| **A `EventQueue` → B `stream:raw_events` 배선** | **P0 TODO** | A는 자체 stream에 durable enqueue까지만; P0 통합 publish는 `ingestion/integration/raw_events_writer.py` 경로와 미연결 |
| Celery(beat/tasks/retry_queue) | **TODO** | 설계만(plans/012) |
| quota_guard | **TODO (design-only)** | 설계만 — 코드 부재 |

> **허위 TODO 교정(중요):** 이전 판본은 A `EventQueue`의 `_redis_*`를 "4개 `NotImplementedError`(Round 2)"라 적었다. 이는 **사실과 다른 허위 TODO**다. `ingestion/pipeline/event_queue.py:147-185`의 `_redis_enqueue/_redis_dequeue/_redis_peek/_redis_mark_done`은 실제 XADD/XREADGROUP/XRANGE/XACK를 호출하는 **완성 구현**이다(`_ensure_group`로 consumer group 생성, BUSYGROUP 무시 포함). 잔여는 "구현"이 아니라 **"A의 durable 출력을 B의 P0 통합 stream으로 흘리는 배선"**이다.

## 2. P0 잔여 — A→B 배선 (재정의)

P0 잔여는 다음 3개로 좁혀진다(개별 `_redis_*` 메서드 구현은 잔여 아님).

1. **A EventQueue → B stream 배선**: A `EventQueue`는 자체 stream(`stream:ingestion_eventqueue`)에 durable enqueue한다. P0 통합 흐름은 이 출력을 B `RawEvent` 계약(`to_raw_event_create`: source/url/fetched_at/content_hash)으로 정규화해 `stream:raw_events`로 흘려야 한다. JSONL은 `REDIS_URL` 미설정 시에만 폴백.
2. **Celery 스케줄/디스패치**: 그룹별 주기 스케줄·retry_queue. (Windows `--pool=solo`, 컨테이너 prefork.)
3. **quota_guard** *(design-only 라벨)*: `quota:{source}:{YYYYMMDD}` INCR + 자정 TTL. **현재 설계만 존재, 코드 부재.**

## 2.1 expansion_router 재유입 절 (LLM 확장 → 큐 재투입)

ADR#14(P/G/F 경계)의 **LAYER P**가 생성하는 확장쿼리·신규 소스 후보는 수집 사이클에 재유입돼야 한다. 이 재유입 경로는 다음 게이트를 통과해야 무한 팽창·중복을 막는다.

- **content_hash dedup**: 재유입 항목도 `content_hash`로 collapse(이미 본 URL 재호출 금지).
- **budget guard**: per-event 호출상한 + 월 예산(LAYER G, R-DiscoveryCostStarvation 대비). 예산 초과 시 재유입 drop.
- **POLICY gate**: `_ALLOWED_BY_LAYER` + `_UNSAFE_STRATEGIES` reject(우회·rate 위반 전략은 어느 재유입 경로에서도 금지).

> 배선 지점: `expansion_router.py`(06·11·미배선)가 후보를 생산 → 위 3게이트 통과분만 A `EventQueue.enqueue()`로 재투입. 상세 = `06`(tiered router/budget), `11 §2.1`(P/G/F).

## 2.2 Event-append 링크 (큐 출력 → Event 타임라인)

B `group:ingest`가 소비한 raw_event는 카드 생성 후 **별개 카드가 아니라 기존 Event에 Update를 append**해야 한다(ADR#16). 큐 레이어의 책임은 raw_event를 손실 없이·중복 없이 다운스트림에 전달하는 것이며, append 라우팅은 다운스트림(`cross_source_dedup` → `cluster_event_map` → `event_updates` APPEND)이 담당한다.

> 링크: `12`(Event append/clustering 파이프라인) · `19 §1·§2`(Event/EventUpdate 스키마·의사코드, NET-NEW 스펙) · `EVENT_SCHEMA.md`(EventUpdate `event_updates` 테이블 DDL). 큐는 전달 계약만 보장하고, "2번째 보도 → 기존 Event append"는 다운스트림 불변식이다.

## 3. Celery vs Temporal vs 순수 Redis Streams (선택)

| 후보 | 적합성 | 판단 |
|---|---|---|
| 순수 Redis Streams | 소비/durability(PEL reclaim) 충분 | **소비 경로 채택**(이미 B에 실구현) |
| Celery beat | 그룹별 주기 스케줄/retry_queue/quota_guard 필요 | **스케줄 채택**(Windows `--pool=solo`, 컨테이너 prefork) |
| Temporal | durable workflow 보상 트랜잭션 | **과함**(단방향 흐름엔 불필요) |
| Kafka | 무한보존/멀티파티션 | 현 규모 불필요(재평가 트리거만) |

웹 리서치: Redis Streams는 consumer group + PEL(pending entries list)로 DLQ/reclaim, durability엔 AOF 필요. 큐와 Kafka의 중간(sub-10ms, hours-days 보존).

## 4. DLQ / retry / quota / cooldown

- **DLQ**: PEL N회 reclaim(XCLAIM) 실패 → `stream:raw_events:dlq` XADD. **실구현**: `workers/queue/dlq.py`(`route_failure`/`reap_pending`), `workers/tools/run_dlq_reaper.py`, `workers/tools/run_recovery_scheduler.py`.
- **retry/cooldown**: `rate_limit_policy.yaml` 단일 출처(gdelt 60s/900s, trends 7200s/0재시도). ZSET score로 영속.
- **quota_guard** *(design-only)*: `quota:{source}:{YYYYMMDD}` INCR + 자정 TTL. **미구현 — 설계만.**
- **burst**: stream 자체가 흡수(sub-10ms). producer min_interval 원자 잠금(`SET NX EX`), consumer 동시성 제한. XLEN/XPENDING 가시화.

## 5. 위험

- mirror가 DB 착시(target="mirror" 명시 노출 필요), consumer except가 ack 누락 시 PEL 영구 적체(→ DLQ 라우팅, 이미 `reap_pending`이 회수), redis 단일 장애점(sentinel/replica는 후속), Windows solo pool 처리량 한계(컨테이너 prefork), expansion 재유입 부분실패(R-ExpansionPartialFailure — budget gate가 일부 통과 시 일관성).

## 6. 검증기준 (acceptance — 분리)

**B 경로 (이미 met):** B producer `stream:raw_events` XADD → `group:ingest` 소비·xack, 미처리분 PEL→`stream:raw_events:dlq` 회수(`reap_pending`), AOF 크래시 내구성. A `EventQueue._redis_*` 4메서드 자체 동작(XADD/XREADGROUP/XRANGE/XACK). → `workers/tests/test_dlq_reaper.py`·`ingestion/tests/integration/test_p0_redis_publish.py` green.

**A→B·Celery·quota (unmet — DoD):** A `EventQueue.enqueue()` 출력이 `RawEvent` 계약으로 정규화돼 `stream:raw_events`에 도달 → B 소비·raw_events PG e2e green, JSONL은 `REDIS_URL` 미설정 시만, content_hash dedup이 재실행 collapse, expansion 재유입이 3게이트(dedup/budget/POLICY) 통과분만 재투입, Celery beat 주기 스케줄 동작, quota_guard가 자정 TTL로 일일 쿼터 강제, 1517 green 유지.

> 상호참조: `00_ROADMAP_INDEX`(순위 #3) · `11 §2.1`(P/G/F) · `06`(tiered router/budget) · `12`(Event append) · `19 §1·§2`(Event/EventUpdate 스펙) · `EVENT_SCHEMA.md`(event_updates DDL) · `_DECISIONS/2026-06.md` ADR#14/#16.
