# API Contract — Event Intelligence API v0.1.0

Base URL: `http://localhost:8000`

## Health

### GET /health

```json
// Response 200
{
  "status": "ok",
  "redis": "ok",
  "milvus": "ok"
}
```

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
    "created_at": "2026-05-23T10:00:00Z"
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
// Response 200: list[FinalEventCard] filtered by theme
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
// Response 200: list[FinalEventCard] filtered by sector
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

Internal endpoint. Used by agent-worker to publish FinalEventCard.

```json
// Request Body: FinalEventCard
// Response 200: FinalEventCard
```
