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
