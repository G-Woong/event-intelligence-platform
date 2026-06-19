# 07 — REDIS / QUEUE / CACHE / STREAM LAYER (L4)

> 결론: B(다운스트림)는 Redis Stream(producer XADD / consumer XREADGROUP+heartbeat)이 **이미 완성**돼 있다. A(ingestion)의 EventQueue는 Redis 경로가 `NotImplementedError("Round 2")`다. 핵심은 새 stream을 만드는 게 아니라 **A의 출력을 B의 기존 stream에 배선**하는 것(P0). 조합은 Celery(스케줄/디스패치) + Redis Streams(소비/durability) 하이브리드.

---

## 1. 현재 상태

| 컴포넌트 | 상태 | 근거 |
|---|---|---|
| B producer `stream:raw_events` XADD | IMPLEMENTED | `workers/queue/producer.py` |
| B consumer `group:ingest` XREADGROUP+xack | IMPLEMENTED | `workers/queue/consumer.py` |
| heartbeat healthcheck(60s) | IMPLEMENTED | compose worker/agent-worker |
| AOF `appendonly yes` | IMPLEMENTED | compose redis |
| A EventQueue Redis 경로 | **TODO** | `event_queue.py` `_redis_*` 4개 NotImplementedError |
| Celery(beat/tasks/retry_queue/quota_guard) | **TODO** | 설계만(plans/012) |
| DLQ / 내장 scheduler | **TODO** | 부재 |

## 2. 전환 설계 (A → B 배선)

- A의 `_redis_enqueue/_dequeue/_peek/_mark_done`를 B의 `backend/app/db/redis.py` 헬퍼(xadd/ensure_group/xreadgroup/xack)에 위임.
- payload를 B의 `RawEvent` 계약(`to_raw_event_create`)에 정합: source/url/fetched_at/content_hash. JSONL은 `REDIS_URL` 미설정 시에만 폴백.

## 3. Celery vs Temporal vs 순수 Redis Streams (선택)

| 후보 | 적합성 | 판단 |
|---|---|---|
| 순수 Redis Streams | 소비/durability(PEL reclaim) 충분 | **소비 경로 채택** |
| Celery beat | 그룹별 주기 스케줄/retry_queue/quota_guard 필요 | **스케줄 채택**(Windows `--pool=solo`, 컨테이너 prefork) |
| Temporal | durable workflow 보상 트랜잭션 | **과함**(단방향 흐름엔 불필요) |
| Kafka | 무한보존/멀티파티션 | 현 규모 불필요(재평가 트리거만) |

웹 리서치: Redis Streams는 consumer group + PEL(pending entries list)로 DLQ/reclaim, durability엔 AOF 필요. 큐와 Kafka의 중간(sub-10ms, hours-days 보존).

## 4. DLQ / retry / quota / cooldown

- **DLQ**: PEL N회 reclaim(XCLAIM) 실패 → `stream:raw_events:dlq` XADD.
- **retry/cooldown**: `rate_limit_policy.yaml` 단일 출처(gdelt 60s/900s, trends 7200s/0재시도). ZSET score로 영속.
- **quota_guard**: `quota:{source}:{YYYYMMDD}` INCR + 자정 TTL.
- **burst**: stream 자체가 흡수(sse-10ms). producer min_interval 원자 잠금(`SET NX EX`), consumer 동시성 제한. XLEN/XPENDING 가시화.

## 5. 위험

- mirror가 DB 착시(target="mirror" 명시 노출 필요), consumer except가 ack 누락 시 PEL 영구 적체(→ DLQ 라우팅), redis 단일 장애점(sentinel/replica는 후속), Windows solo pool 처리량 한계(컨테이너 prefork).

## 6. 검증기준 (완전 달성)

A `EventQueue.enqueue()` 출력이 `stream:raw_events`에 XADD → B `group:ingest`가 소비·xack, 미처리분 PEL→DLQ 회수, JSONL은 `REDIS_URL` 미설정 시만, content_hash dedup이 재실행 collapse, AOF로 크래시 내구성 보장. A→B e2e(enqueue→consume→raw_events PG) green.
