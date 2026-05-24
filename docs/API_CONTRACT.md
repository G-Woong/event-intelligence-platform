# API Contract — Event Intelligence API v0.1.0

Base URL: `http://localhost:8000`

## CORS (STEP 010)

Backend에 `CORSMiddleware`가 추가됨.

| 항목 | 값 |
|---|---|
| allow_origins | `settings.CORS_ALLOW_ORIGINS` (기본: `["http://localhost:3000"]`) |
| allow_methods | GET, POST, PATCH, OPTIONS |
| allow_headers | Content-Type, X-Admin-Token, Accept |
| allow_credentials | False |
| max_age | 600 |

env `CORS_ALLOW_ORIGINS`로 쉼표 구분 origin 목록 지정 가능.

## Frontend Proxy Routes (STEP 010)

브라우저는 ADMIN_API_TOKEN을 모르며, frontend Route Handler를 통해 admin mutation 실행.

| Proxy | Backend target |
|---|---|
| `POST /api/admin/reindex` | `POST http://backend:8000/api/admin/search/reindex` |
| `POST /api/admin/reconcile` | `POST http://backend:8000/api/admin/reconcile-stuck` |
| `POST /api/admin/requeue/{id}` | `POST http://backend:8000/api/admin/raw-events/{id}/requeue` |

## 인증 (STEP 008C)

`/api/admin/*` 전체와 `/api/internal/*` 엔드포인트는 `X-Admin-Token` 헤더로 보호된다.

| 환경 | `ADMIN_API_TOKEN` 설정 여부 | 동작 |
|---|---|---|
| Dev | 미설정 (기본) | 모든 admin 호출 허용 (startup WARNING 출력) |
| Prod | 설정 필수 | 헤더 없음 또는 불일치 → **401** |

헤더 예:
```
X-Admin-Token: <your-secret-token>
```

비교는 `secrets.compare_digest`로 timing-safe 처리.
`/health`, `/api/events|themes|sectors|comments|ai-replies`는 인증 불필요.

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

### POST /api/admin/raw-events (STEP 007, auth: STEP 008C)

Idempotent insert of a raw event from collector. Deduplicates by `content_hash`. On new insert, enqueues to Redis Stream `stream:raw_events`.

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

### POST /api/admin/raw-events/reconcile-stuck (STEP 008B, auth: STEP 008C)

stuck enqueued 상태의 raw_event를 탐지/처리. `dry_run=true`(기본)이면 조회만 하고 변경 없음.

Request body (`ReconcileStuckRequest`):
```json
{
  "before_seconds": 600,
  "limit": 100,
  "dry_run": true,
  "error_reason": "reconciler: stuck enqueued"
}
```

Response (`ReconcileStuckResponse`):
```json
{
  "stuck_count": 3,
  "marked_failed": 0,
  "dry_run": true,
  "items": [ /* list[RawEventRecord] */ ]
}
```

`dry_run=false`이면 `marked_failed` == `stuck_count` (빈 결과 제외).

### POST /api/admin/raw-events/{raw_event_id}/requeue (STEP 008C)

failed/stuck raw_event를 Redis Stream에 다시 넣는다. `requeue_count` 증가, `error_reason` 초기화.

Request body (`RequeueRequest`):
```json
{ "force": false }
```

`force=false`(기본): `status=processed` 인 경우 거부 → **409**.
`force=true`: processed 상태도 requeue 허용.

Response (`RequeueResponse`):
```json
{
  "record": { /* 갱신된 RawEventRecord */ },
  "enqueued_msg_id": "1779000001-0",
  "requeue_count": 1
}
```

| 상태 코드 | 조건 |
|---|---|
| 200 | 성공 |
| 404 | raw_event_id 미존재 |
| 409 | status=processed 이고 force=false |
| 401 | ADMIN_API_TOKEN 설정 + 헤더 없음/불일치 |

### GET /api/admin/raw-events (STEP 008B, extended: 008C)

status + age 기반 raw_event 목록 조회. Query params:

| 파라미터 | 타입 | 기본값 | 설명 |
|---|---|---|---|
| `status` | str | null | 특정 status로 필터 (null이면 전체) |
| `before_seconds` | int | null | updated_at이 N초 이전인 row만 반환 (null이면 전체) |
| `limit` | int | 50 | 최대 반환 수 |
| `source_type` | str | null | source_type 필터 (예: `rss`) |
| `offset` | int | 0 | 페이지 오프셋 |
| `order` | str | `asc` | updated_at 정렬 방향 (`asc`\|`desc`) |

```json
// Response 200: list[RawEventRecord]
[
  {
    "id": "...",
    "status": "enqueued",
    "updated_at": "2026-05-24T01:00:00Z",
    ...
  }
]
```

### GET /api/events/search (STEP 009, 무인증)

키워드 기반 event_cards 검색. OpenSearch `multi_match` + bool filter.

Query params:

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---|---|---|---|---|
| `q` | str | ✓ | — | 검색어 (1-200자). 빈 값 → 422 |
| `theme` | str | — | null | keyword filter |
| `sector` | str | — | null | keyword filter (sectors 배열 내 포함 여부) |
| `status` | str | — | null | keyword filter (`published`/`hold`) |
| `limit` | int | — | 20 | 최대 반환 수 (1-100) |
| `offset` | int | — | 0 | 페이지 오프셋 |

```json
// Response 200 (EventSearchResponse):
{
  "total": 2,
  "hits": [
    {
      "card_id": "uuid",
      "title": "Iran Sanctions Update",
      "summary": "...",
      "theme": "geopolitics",
      "sectors": ["energy", "finance"],
      "status": "published",
      "score": 1.234,
      "created_at": "2026-05-24T00:00:00+00:00"
    }
  ]
}

// Response 422: q 누락 또는 길이 초과
// Response 503: OpenSearch 다운 ({ "detail": "search unavailable" })
```

`title^2` 가중치 부스트. `text_all`(title+summary+entities+sectors 합산 필드) 포함 검색.

### POST /api/admin/search/reindex (STEP 009, auth 필요)

Postgres event_cards를 OpenSearch에 bulk reindex.

```json
// Request Body (ReindexRequest):
{ "limit": 1000, "dry_run": false }

// Response 200 (ReindexResponse):
{ "indexed": 42, "dry_run": false }
```

`dry_run=true`이면 count만 반환, 실제 색인 없음.

### POST /api/admin/collect-rss-once (STEP 007, auth: STEP 008C)

Triggers RSS collector run in-process via `asyncio.to_thread`. Fetches all enabled DEFAULT_SOURCES and inserts to `raw_events`. Returns summary JSON.

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
