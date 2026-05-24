# 수집 → 큐 → 워커 → 에이전트 분리 구조

> RSS 수집기, Redis Stream 큐, worker 컨테이너, agent-worker 컨테이너의 역할 분담을 설명합니다.

---

## 왜 이렇게 분리했나

```
[하나의 프로세스로 했을 때 문제]
수집(느림) + 분석(매우 느림) + API 서비스(빠름) → 서로 블로킹

[분리 후]
수집 → 큐에 넣기 (빠름)
큐에서 꺼내 정규화 → 다른 큐 (빠름, worker)
큐에서 꺼내 AI 분석 (느려도 OK, agent-worker 독립)
API 서비스 (수집·분석 영향 없이 항상 빠름)
```

---

## RSS 수집기 동작

### 파일: `workers/collectors/rss_collector.py`

```
실행 주기: 외부 cron 또는 Admin API /collect-rss-once 수동 트리거

동작:
1. sources.py의 DEFAULT_SOURCES 목록 읽기 (enabled=True만)
2. 각 소스 URL에 feedparser 요청
3. 각 기사마다 content_hash(title+body SHA256) 계산
4. raw_event_service.create_raw_event() 호출 → raw_events 테이블 upsert
5. ON CONFLICT (content_hash) DO NOTHING → 중복 기사 자동 건너뜀
6. 신규 기사마다 Redis Stream stream:raw_events에 메시지 발행 (producer.py)
```

### 현재 수집 소스 (`workers/collectors/sources.py`)

```python
DEFAULT_SOURCES = [
    {"name": "BBC World News",    "url": "...", "theme_hint": "geopolitics", "enabled": True},
    {"name": "Reuters Business",  "url": "...", "theme_hint": "macro",       "enabled": True},
    {"name": "YNA Economy",       "url": "...", "theme_hint": "macro_kr",    "enabled": True},
]
```

신규 소스 추가 방법: `sources.py`에 항목 추가 → 동일한 흐름으로 자동 처리

---

## Redis Stream 구조

```
stream:raw_events     ← producer가 XADD (rss_collector → raw_event 저장 후)
       │
       ▼
consumer.py (worker 컨테이너, XREADGROUP GROUP worker_group)
       │
       ├── ingest_pipeline.normalize()
       └── XADD stream:to_agent

stream:to_agent       ← ingest_pipeline이 XADD
       │
       ▼
agent_worker.py (agent-worker 컨테이너, XREADGROUP GROUP agent_group)
       │
       └── LangGraph graph.run()
```

### 메시지 흐름 보장
1. `XREADGROUP`: 메시지를 "처리 중" 상태로 락 (같은 메시지 중복 소비 방지)
2. 처리 완료 후 `XACK`: 메시지 완료 표시
3. ACK 없으면 PEL(Pending Entry List)에 잔류 → 재처리 가능
4. `consumer.py`에서 주기적으로 PEL 확인 및 재처리

---

## worker 컨테이너 (`ei-worker`)

### 파일: `workers/queue/consumer.py`

주요 동작:
1. `stream:raw_events`에서 `XREADGROUP`으로 메시지 읽기
2. `raw_event_service`로 DB에서 raw_event 조회
3. `ingest_pipeline.process(raw_event)` 호출 → 정규화
4. `XADD stream:to_agent`에 정규화 결과 발행
5. `XACK stream:raw_events`로 처리 완료 표시
6. `/tmp/worker_heartbeat` 파일 갱신 (healthcheck용)

### 파일: `workers/pipelines/ingest_pipeline.py`

- RSS 기사 텍스트 정규화 (공백 정리, 언어 감지 등)
- `NormalizedEvent` 객체 반환
- `stream:to_agent`에 발행할 payload 구성

---

## agent-worker 컨테이너 (`ei-agent-worker`)

### 파일: `agents/agent_worker.py`

주요 동작:
1. `stream:to_agent`에서 `XREADGROUP`으로 메시지 읽기
2. `RawEvent` 객체 구성
3. `event_processing_graph.run(raw_event)` 호출 → LangGraph 11 노드 실행
4. 반환된 `FinalEventCard`를 `publish_pipeline.publish(card)` 호출
5. `/tmp/agent_heartbeat` 파일 갱신 (healthcheck용)

### heartbeat 방식 healthcheck

```yaml
# docker-compose.dev.yml
healthcheck:
  test: ["CMD-SHELL", "test $(($(date +%s) - $(stat -c %Y /tmp/worker_heartbeat))) -lt 60"]
```
→ 파일 수정 시각이 60초 이내이면 healthy

---

## Publish Pipeline

### 파일: `workers/pipelines/publish_pipeline.py`

동작:
1. `FinalEventCard` JSON을 HTTP POST `/api/admin/upsert-event`에 전송
2. backend에서 event_cards 저장 + Milvus 색인 + OpenSearch 색인
3. raw_events.status → "done" 업데이트

---

## Reconciler (조정자)

처리 중 크래시 또는 타임아웃으로 영원히 pending/processing 상태가 된 raw_events 처리.

### 파일: `backend/app/services/reconciler_service.py`
### 파일: `scripts/reconcile_stuck_once.py`

동작:
```
/api/admin/raw-events/reconcile-stuck 호출
  │
  ▼
before_seconds 파라미터로 기준 시각 설정
  │
  ▼
status=pending/processing + updated_at < (now - before_seconds) 조건으로 조회
  │
  ▼
dry_run=true: 조회만 / dry_run=false: status=failed로 업데이트
```

---

## Scheduler (스케줄러)

**현재 미구현** — 외부 cron 또는 k8s CronJob 가정

일회성 스크립트 존재:
- `scripts/reconcile_stuck_once.py` — reconcile 1회 실행
- `scripts/reindex_opensearch_once.py` — 전체 색인 재구축 1회

운영 환경 진입 시 내장 스케줄러 또는 k8s CronJob 연결 예정 (STEP 015).

---

## DART / SEC Collector (미구현)

| 소스 | 상태 | 추가 예정 위치 |
|---|---|---|
| DART (한국 공시) | TODO | `workers/collectors/dart_collector.py` |
| SEC EDGAR (미국 공시) | TODO | `workers/collectors/sec_collector.py` |
| 정부 OpenAPI | TODO | `workers/collectors/gov_collector.py` |

신규 collector가 추가되어도 출구(`raw_events` 테이블 + `stream:raw_events`)는 동일 — 하위 파이프라인 변경 불필요.
