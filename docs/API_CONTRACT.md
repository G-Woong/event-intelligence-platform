# API Contract — Event Intelligence API v0.1.0

Base URL: `http://localhost:8000`

## Health

### GET /health

STEP 004에서 `postgres` 필드 추가. 모든 endpoint는 `async def`로 전환됨.
STEP 004.5에서 `milvus` 부정 값 `"error"`로 통일 (기존 `"disconnected"` 제거).

```json
// Response 200
{
  "status": "ok",
  "redis": "ok",
  "milvus": "ok",
  "postgres": "ok"
}
```

각 필드 값: `"ok"` | `"error"` (연결 실패 시 공통 표현 사용).

| 필드 | 정상 | 장애 |
|---|---|---|
| `status` | `"ok"` | (항상 ok — 필드 자체 반환 실패 시 500) |
| `redis` | `"ok"` | `"error"` |
| `milvus` | `"ok"` | `"error"` |
| `postgres` | `"ok"` | `"error"` |

## Events

### GET /api/events

```json
// Response 200
[
  {
    "id": "uuid",
    "title": "...",
    "summary": "...",
    "theme": "geopolitics",
    "sectors": ["energy"],
    "entities": ["Iran"],
    "impact_path": "...",
    "evidence": [],
    "confidence_score": 0.75,
    "status": "published",
    "created_at": "2026-05-23T10:00:00+00:00"
  }
]
```

### GET /api/events/{event_id}

```json
// Response 200: FinalEventCard
// Response 404: { "detail": "event not found" }
```

## Themes

### GET /api/themes

```json
[
  { "id": "geopolitics", "label": "Geopolitics" },
  { "id": "economics", "label": "Economics" },
  { "id": "technology", "label": "Technology" },
  { "id": "climate", "label": "Climate" },
  { "id": "health", "label": "Health" }
]
```

### GET /api/themes/{theme_id}/events

```json
// Response 200: list[FinalEventCard] filtered by theme (SQL WHERE theme=?)
```

## Sectors

### GET /api/sectors

```json
[
  { "id": "energy", "label": "Energy" },
  { "id": "finance", "label": "Finance" },
  { "id": "defense", "label": "Defense" },
  { "id": "tech", "label": "Technology" },
  { "id": "trade", "label": "Trade" }
]
```

### GET /api/sectors/{sector_id}/events

```json
// Response 200: list[FinalEventCard] filtered by sector (JSONB @> operator)
```

## Comments

### POST /api/comments

```json
// Request Body:
{
  "event_id": "uuid",
  "author": "user1",
  "body": "Interesting development."
}
// Response 200: Comment object
```

### GET /api/events/{event_id}/comments

```json
// Response 200: list[Comment]
```

## AI Replies

### POST /api/ai-replies/request

```json
// Request Body:
{ "event_id": "uuid", "prompt_hint": "summarize impact" }
// Response 200:
{ "event_id": "uuid", "reply": "[mock] response for prompt length=..." }
```

## Admin

### GET /api/admin/jobs

```json
{
  "raw_events": { "length": 5, "groups": ["group:ingest"] },
  "to_agent": { "length": 3, "groups": ["group:agent"] }
}
```

### POST /api/admin/upsert-event

Internal endpoint. Used by agent-worker to publish FinalEventCard. STEP 004: persists to PostgreSQL via INSERT ... ON CONFLICT DO UPDATE.

```json
// Request Body: FinalEventCard
// Response 200: FinalEventCard
```

### POST /api/admin/raw-events (STEP 007)

Idempotent insert of a raw event from collector. Deduplicates by `content_hash`. On new insert, enqueues to Redis Stream `stream:raw_events`.

TODO STEP 008: admin token authentication.

```json
// Request Body (RawEventCreate):
{
  "source_type": "rss",
  "source_name": "bbc_world",
  "external_id": "guid-123",
  "url": "https://example.com/article/1",
  "title": "Article title",
  "raw_text": "Summary text",
  "published_at": "2026-05-23T08:00:00Z",
  "content_hash": "sha256hex64chars...",
  "theme_hint": "geopolitics",
  "raw_metadata": {"rss": {"feed_title": "BBC", "guid": "guid-123", "tags": []}}
}

// Response 200 (RawEventCreateResponse):
{
  "record": { /* RawEventRecord — all raw_events columns */ },
  "is_duplicate": false,
  "enqueued_msg_id": "1779000000000-0"
}

// Duplicate case:
{
  "record": { /* existing row */ },
  "is_duplicate": true,
  "enqueued_msg_id": null
}
```

### GET /api/admin/raw-events/{raw_event_id} (STEP 008A)

단일 raw_event row 조회. status 폴링용.

```json
// Response 200: RawEventRecord
{
  "id": "...",
  "status": "processed",
  "event_card_id": "...",
  "processed_at": "2026-05-24T00:01:00Z",
  ...
}
// Response 404: { "detail": "raw_event_id=... not found" }
```

### PATCH /api/admin/raw-events/{raw_event_id}/status (STEP 008A)

agent-worker가 처리 완료/실패 결과를 backend에 통보. status를 processed/failed로 전이.

Request body (`RawEventStatusUpdate`):
```json
{ "status": "processed", "event_card_id": "...", "error_reason": null }
```
또는
```json
{ "status": "failed", "error_reason": "LLM timeout after 30s" }
```

`error_reason`은 500자로 truncate됨.

```json
// Response 200: 갱신된 RawEventRecord
// Response 404: raw_event_id 미존재 시
```

TODO STEP 008C: admin token authentication.

### POST /api/admin/collect-rss-once (STEP 007)

Triggers RSS collector run in-process via `asyncio.to_thread`. Fetches all enabled DEFAULT_SOURCES and inserts to `raw_events`. Returns summary JSON.

TODO STEP 008C: admin token authentication.

```json
// Response 200:
{
  "sources": 3,
  "items_seen": 152,
  "items_enqueued": 5,
  "duplicates": 145,
  "errors": 2,
  "per_source": [
    { "source": "bbc_world", "items_seen": 32, "items_enqueued": 0, "duplicates": 30, "errors": 2 },
    { "source": "reuters_business", "items_seen": 0, "items_enqueued": 0, "duplicates": 0, "errors": 0 },
    { "source": "yna_economy", "items_seen": 120, "items_enqueued": 5, "duplicates": 115, "errors": 0 }
  ]
}
```
