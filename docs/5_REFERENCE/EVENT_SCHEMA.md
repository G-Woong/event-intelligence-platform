# Event Schema

## RawEvent

| 필드 | 타입 | 설명 |
|---|---|---|
| source | str | 수집 소스 식별자 (e.g. "reuters-rss") |
| url | str | 원본 URL |
| fetched_at | datetime | 수집 시각 (UTC) |
| raw_text | str | 원문 텍스트 |
| raw_metadata | dict | 소스별 추가 메타데이터 |
| raw_event_id | Optional[str] | DB raw_events.id. stream payload → agent pipeline 추적 키 (STEP 008A) |

```json
{
  "source": "reuters-rss",
  "url": "https://example.com/news/1",
  "fetched_at": "2026-05-23T10:00:00Z",
  "raw_text": "Tensions rise in the Strait of Hormuz as...",
  "raw_metadata": {"category": "world"}
}
```

## NormalizedEvent

| 필드 | 타입 | 설명 |
|---|---|---|
| id | str (uuid4) | 고유 식별자 |
| source | str | 소스 식별자 |
| title | str | 정규화된 제목 |
| body | str | 본문 |
| occurred_at | datetime | 사건 발생 시각 |
| language | str | 언어 코드 (기본 "en") |
| hash | str | 중복 탐지용 SHA-256 prefix (16자) |

```json
{
  "id": "a1b2c3d4-...",
  "source": "reuters-rss",
  "title": "Tensions rise in the Strait of Hormuz",
  "body": "...",
  "occurred_at": "2026-05-23T09:55:00Z",
  "language": "en",
  "hash": "a3f1e9d2c7b4..."
}
```

## FinalEventCard

| 필드 | 타입 | 설명 | PG 컬럼 타입 |
|---|---|---|---|
| id | str (uuid4) | 고유 식별자 | UUID PK |
| title | str | 최종 제목 | VARCHAR |
| summary | str | 요약문 | VARCHAR |
| theme | str | 주제 (geopolitics/economics/technology/climate/health) | VARCHAR, INDEX |
| sectors | list[str] | 관련 섹터 목록 | JSONB, GIN INDEX |
| entities | list[str] | 주요 엔티티 목록 | JSONB |
| impact_path | str | 영향 경로 설명 | VARCHAR |
| evidence | list[str] | 근거 출처 목록 | JSONB |
| confidence_score | float (0–1) | 신뢰도 점수 | FLOAT, CHECK(0..1) |
| status | "published"\|"hold" | 게시 상태 | VARCHAR, INDEX |
| created_at | datetime (tz-aware) | 생성 시각 | TIMESTAMPTZ, INDEX DESC |

ORM 전용 추가 컬럼: `updated_at` (TIMESTAMPTZ) — Pydantic 스키마 미포함.

## Milvus Vector Schema (STEP 006)

collection: `event_embeddings`, dim: 1536, index: IVF_FLAT / COSINE / nlist=128

| 필드 | 타입 | 설명 |
|---|---|---|
| pk | INT64, auto_id, primary | Milvus 내부 PK |
| event_id | VARCHAR(64) | FinalEventCard.id |
| card_id | VARCHAR(64) | 현재 event_id 동일; 향후 분리 대비 |
| text_hash | VARCHAR(64) | sha256(title+summary)[:32] |
| theme | VARCHAR(64) | 단일 string |
| source_type | VARCHAR(32) | 현재 "agent" 고정 |
| created_at | INT64 | unix timestamp |
| metadata_json | VARCHAR(2048) | sectors/entities JSON |
| embedding | FLOAT_VECTOR(1536) | cosine 검색 벡터 |

```json
{
  "id": "x9y8z7w6-...",
  "title": "Tensions rise in the Strait of Hormuz",
  "summary": "Military vessels from multiple nations...",
  "theme": "geopolitics",
  "sectors": ["energy", "defense"],
  "entities": ["Iran", "US Navy", "Strait of Hormuz"],
  "impact_path": "medium-term oil supply disruption risk",
  "evidence": ["reuters.com/...", "bbc.com/..."],
  "confidence_score": 0.82,
  "status": "published",
  "created_at": "2026-05-23T10:01:00+00:00"
}
```

## raw_events Table (STEP 007)

| 컬럼 | 타입 | NULL | 기본값 | 비고 |
|---|---|---|---|---|
| id | UUID | NO | uuid.uuid4 | PK |
| source_type | VARCHAR(32) | NO | — | "rss" / 미래: dart/sec/web |
| source_name | VARCHAR(128) | NO | — | feed 식별자 (e.g. bbc_world) |
| external_id | VARCHAR(512) | YES | NULL | RSS guid/link fallback |
| url | VARCHAR(2048) | NO | — | canonical link |
| title | VARCHAR(1024) | YES | NULL | RSS title |
| raw_text | TEXT | NO | '' | HTML 제거된 summary — 본문 저장 금지 |
| published_at | TIMESTAMPTZ | YES | NULL | UTC 변환 |
| collected_at | TIMESTAMPTZ | NO | now() | |
| content_hash | VARCHAR(64) | NO | — | sha256(dedup key) |
| theme_hint | VARCHAR(64) | YES | NULL | sources config에서 주입 |
| status | VARCHAR(16) | NO | 'collected' | collected→enqueued→processed\|failed (STEP 008A 완료) |
| enqueued_msg_id | VARCHAR(64) | YES | NULL | Redis XADD msg id |
| error_reason | VARCHAR(512) | YES | NULL | failed status 시 |
| event_card_id | UUID | YES | NULL | 처리 완료 후 생성된 FinalEventCard.id (STEP 008A) |
| processed_at | TIMESTAMPTZ | YES | NULL | processed/failed 전이 시각 (STEP 008A) |
| raw_metadata | JSONB | NO | '{}' | RSS tags/feed metadata |
| created_at | TIMESTAMPTZ | NO | now() | |
| updated_at | TIMESTAMPTZ | NO | now() | |

**UNIQUE 제약**: `content_hash` + partial `(source_type, external_id) WHERE external_id IS NOT NULL`

**인덱스**: collected_at DESC, status, source_type, published_at DESC NULLS LAST, raw_metadata GIN, event_card_id, processed_at

## OpenSearch Document: `event_cards` (STEP 009)

OpenSearch에 색인되는 document 구조 (source of truth는 Postgres).

| 필드 | OpenSearch 타입 | 내용 |
|---|---|---|
| `card_id` | keyword | FinalEventCard.id (UUID string) |
| `title` | text + keyword subfield | 제목 |
| `summary` | text | 요약 |
| `text_all` | text | title + summary + entities + sectors 합산 (검색 전용) |
| `theme` | keyword | 테마 (e.g. geopolitics) |
| `status` | keyword | published / hold |
| `sectors` | keyword[] | 섹터 배열 |
| `entities` | keyword[] | 엔티티 배열 |
| `confidence_score` | float | 신뢰도 0.0-1.0 |
| `created_at` | date | ISO 8601 |

인덱스 이름: `event_cards` (설정: `OPENSEARCH_EVENT_INDEX`).
Analyzer: standard (기본). 한국어 nori는 STEP 010+ TODO.

## Comment

| 필드 | 타입 | 설명 | PG 컬럼 타입 |
|---|---|---|---|
| id | str (uuid4) | 고유 식별자 | UUID PK |
| event_id | str (uuid4) | 연관 이벤트 ID | UUID FK → event_cards.id ON DELETE CASCADE |
| author | str | 작성자 | VARCHAR |
| body | str | 댓글 내용 | VARCHAR |
| created_at | datetime (tz-aware) | 작성 시각 | TIMESTAMPTZ |

인덱스: `ix_comments_event_id_created` (event_id, created_at)
