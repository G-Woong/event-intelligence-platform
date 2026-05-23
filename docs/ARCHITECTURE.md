# Architecture — Event Intelligence (STEP 003)

## 컴포넌트 다이어그램

```
[외부 소스]
     │
     ▼
[producer.py]
  XADD stream:raw_events
     │
     ▼
[worker (consumer.py)]                         group:ingest
  XREADGROUP stream:raw_events
     │ ingest_pipeline: validate + forward
     ▼
  XADD stream:to_agent
     │
     ▼
[agent-worker (agent_worker.py)]               group:agent
  XREADGROUP stream:to_agent
     │ EventProcessingGraph.run(raw_event)
     │   → 11-node LangGraph pipeline (mock)
     │   → FinalEventCard
     ▼
  POST /api/admin/upsert-event
     │
     ▼
[backend (FastAPI)]
  event_service.upsert_card(card) [in-memory]
     │
     ▼
  GET /api/events → FinalEventCard[]
```

## 서비스 구성

| 서비스 | 이미지 | 포트 | 역할 |
|---|---|---|---|
| redis | redis:7.4-alpine | 6379 | Stream broker |
| milvus-standalone | milvusdb/milvus:v2.4.10 | 19530, 9091 | Vector store (STEP 004 활성화) |
| backend | ./backend/Dockerfile | 8000 | FastAPI API 서버 |
| worker | ./workers/Dockerfile | - | Stream ingest consumer |
| agent-worker | ./agents/Dockerfile | - | LangGraph pipeline consumer |

## Redis Stream 선택 이유

- Consumer group으로 메시지 ack/replay 명확
- List 대비 추가 비용: consumer group init 1줄 (`XGROUP CREATE`)
- DLQ/관측 확장에 유리 (XPENDING, XCLAIM)
- Celery 의존 없이 순수 Redis로 워커 파이프라인 구성 가능

## Mock 영역 (STEP 003)

- LLM 호출: `LLMClient(provider="mock")` — deterministic 문자열 반환
- 모든 LangGraph 노드: 실제 NLP 없음, 고정 mock 값 반환
- Milvus 임베딩: `insert_embedding`, `search_similar_events` stub (no-op)
- Postgres: placeholder (NotImplementedError)
- event_service: in-memory dict (프로세스 재시작 시 소멸)

## STEP 004 이후 활성화 예정

- 실제 crawler (RSS, sitemap)
- normalize/deduplicate 실제 로직
- Milvus embedding insert/search
- LangSmith tracing
- OpenAI provider 활성화
- Postgres 영속화
