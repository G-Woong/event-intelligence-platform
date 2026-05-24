# 엔드-투-엔드 데이터 흐름 (13단계)

> RSS 피드 XML이 들어와서 Next.js 화면에 표시되기까지의 전 과정을 단계별로 설명합니다.

---

## 전체 흐름 요약

```
RSS feed XML
  → feedparser(Python)
  → raw_events (PostgreSQL 테이블)
  → Redis Stream: stream:raw_events
  → consumer.py (worker 컨테이너)
  → ingest_pipeline.normalize()
  → Redis Stream: stream:to_agent
  → agent_worker.py (agent-worker 컨테이너)
  → LangGraph 11 노드
  → FinalEventCard (JSON)
  → publish_pipeline → backend /api/admin/upsert-event
  → event_cards (PostgreSQL)
  → Milvus (벡터 색인)
  → OpenSearch (키워드 색인)
  → FastAPI GET /api/events
  → Next.js 화면
```

---

## 단계별 상세표

| # | 단계 | 입력 | 처리 주체 | 출력 | 저장소 | 관련 파일 |
|---|---|---|---|---|---|---|
| 1 | RSS 수집 | RSS feed URL | `rss_collector.py` | `RawEventCreate` dict | — | `workers/collectors/rss_collector.py` |
| 2 | raw_event 저장 | `RawEventCreate` | `raw_event_service.create_raw_event()` | `RawEventRecord` (DB row) | PostgreSQL `raw_events` | `backend/app/services/raw_event_service.py` |
| 3 | Stream 발행 | `raw_event_id` | `queue/producer.py` | Redis Stream 메시지 | Redis `stream:raw_events` | `workers/queue/producer.py` |
| 4 | Stream 소비 | Stream 메시지 | `consumer.py` (xreadgroup) | Python dict | — | `workers/queue/consumer.py` |
| 5 | Ingest 파이프라인 | `RawEventRecord` | `ingest_pipeline.py` | 정규화된 `NormalizedEvent` | Redis `stream:to_agent` | `workers/pipelines/ingest_pipeline.py` |
| 6 | Agent 소비 | `stream:to_agent` 메시지 | `agent_worker.py` | `RawEvent` 객체 | — | `agents/agent_worker.py` |
| 7 | LangGraph 처리 | `EventState` (초기화) | 11개 노드 순차 실행 | `EventState` (최종) | — | `agents/graphs/event_processing_graph.py` |
| 8 | FinalEventCard 생성 | `EventState.final_card` | `final_card_writer` 노드 | `FinalEventCard` JSON | — | `agents/nodes/final_writer.py` |
| 9 | 발행 | `FinalEventCard` | `publish_pipeline.py` | HTTP POST 응답 | — | `workers/pipelines/publish_pipeline.py` |
| 10 | event_cards 저장 | `FinalEventCard` | `event_service.upsert_card()` | DB row | PostgreSQL `event_cards` | `backend/app/services/event_service.py` |
| 11 | 벡터 색인 | `FinalEventCard` | `vector_index_service.try_index_card()` | Milvus insert | Milvus `event_embeddings` | `backend/app/services/vector_index_service.py` |
| 12 | 키워드 색인 | `FinalEventCard` | `opensearch_index_service.try_index_card()` | OS document | OpenSearch `event_cards` | `backend/app/services/opensearch_index_service.py` |
| 13 | API 제공 + 화면 | HTTP GET 요청 | FastAPI + Next.js | HTML 화면 | — | `backend/app/api/events.py`, `frontend/src/app/` |

---

## 각 단계 데이터 모양 예시

### 단계 1 출력 — RawEventCreate
```json
{
  "source_type": "rss",
  "source_name": "Reuters Business",
  "source_url": "https://feeds.reuters.com/reuters/businessNews",
  "title": "Oil prices rise on supply concerns",
  "raw_text": "Oil prices climbed on Monday...",
  "published_at": "2026-05-24T08:30:00Z",
  "content_hash": "sha256:a1b2c3..."
}
```

### 단계 2 출력 — RawEventRecord (PostgreSQL row)
```json
{
  "raw_event_id": "uuid-xxxx",
  "status": "pending",
  "source_type": "rss",
  "title": "Oil prices rise...",
  "raw_text": "...",
  "content_hash": "sha256:a1b2c3...",
  "created_at": "2026-05-24T08:30:05Z"
}
```

### 단계 3 출력 — Redis Stream 메시지 (`stream:raw_events`)
```
XADD stream:raw_events * raw_event_id uuid-xxxx source_type rss
```

### 단계 7 — LangGraph EventState (처리 중)
```python
{
  "raw": RawEvent(...),
  "normalized": NormalizedEvent(...),
  "dedupe_key": "sha256:...",
  "entities": ["Entity-A", "Entity-B"],
  "theme": "macro",
  "sectors": ["energy"],
  "past_context": [...],
  "impact": "supply disruption risk...",
  "evidence": [...],
  "fact_check": "pass",
  "final_card": None,  # final_card_writer 이전
  "status": "",
  "llm_provider": "mock",
  "llm_errors": [],
  "prompt_versions": {"impact_analysis": "v1", ...}
}
```

### 단계 8 출력 — FinalEventCard
```json
{
  "event_id": "uuid-yyyy",
  "title": "Oil prices rise on supply concerns",
  "headline": "[mock] Supply disruption risk detected",
  "summary": "...",
  "theme": "macro",
  "sectors": ["energy"],
  "entities": ["[mock-entity-1]"],
  "impact": "[mock] moderate risk",
  "fact_check_status": "pass",
  "source_name": "Reuters Business",
  "source_url": "...",
  "published_at": "2026-05-24T08:30:00Z",
  "status": "published",
  "llm_provider": "mock",
  "model_used": null
}
```

### 단계 13 — FastAPI 응답 (GET /api/events)
```json
[
  {
    "event_id": "uuid-yyyy",
    "title": "...",
    "headline": "...",
    "theme": "macro",
    "sectors": ["energy"],
    "status": "published",
    ...
  }
]
```

---

## 오류 처리 흐름

```
정상 흐름:    raw_events.status = pending → processing → done
오류 발생:    raw_events.status = failed (error_reason 기록)
재시도:       /api/admin/raw-events/{id}/requeue → 다시 pending
장기 stuck:   reconcile-stuck API → pending/processing 상태가 N초 초과 시 failed 처리
```

→ Redis Stream PEL(Pending Entry List) 관리: `workers/queue/consumer.py`  
→ Reconcile 서비스: `backend/app/services/reconciler_service.py`  
→ Reindex(색인 재구축): `backend/app/api/admin.py` + `scripts/reindex_opensearch_once.py`

---

## 현재 실제 수집 소스

| 소스 이름 | URL | 테마 힌트 | 상태 |
|---|---|---|---|
| BBC World News | `feeds.bbci.co.uk/...` | geopolitics | REAL (실동작) |
| Reuters Business | `feeds.reuters.com/...` | macro | REAL (실동작) |
| YNA Economy | `yonhapnewstv.co.kr/...` | macro_kr | REAL (실동작) |
| DART (한국 공시) | 미구현 | — | TODO |
| SEC EDGAR (미국 공시) | 미구현 | — | TODO |

관련 파일: `workers/collectors/sources.py`
