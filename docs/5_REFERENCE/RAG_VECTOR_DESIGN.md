# RAG Vector Design — STEP 006

## Overview

STEP 006에서 구현한 Milvus 기반 Dense Vector RAG의 minimal end-to-end 경로.

```
FinalEventCard
  → upsert_card (Postgres)
  → vector_index_service.try_index_card
  → EmbeddingClient.embed_text(title + "\n" + summary)
  → milvus.insert_event_embedding (collection: event_embeddings, dim=1536)

retrieve_past_context (LangGraph node)
  → vector_search.search_similar (httpx POST)
  → POST /api/internal/search-similar
  → embed query → milvus.search_similar_events
  → Postgres lookup for title/summary
  → state.past_context + state.retrieved_context
```

## Milvus Collection Schema

**collection**: `event_embeddings` (env: `MILVUS_COLLECTION`)  
**dim**: 1536 (env: `EMBEDDING_DIM`)  
**index**: IVF_FLAT, metric=COSINE, nlist=128  
**search**: nprobe=8, limit=top_k

| field | type | note |
|---|---|---|
| `pk` | INT64, auto_id, primary | Milvus internal PK |
| `event_id` | VARCHAR(64) | FinalEventCard.id (UUID string) |
| `card_id` | VARCHAR(64) | 현재는 event_id 동일; 향후 분리 대비 |
| `text_hash` | VARCHAR(64) | sha256(title+summary)[:32] |
| `theme` | VARCHAR(64) | 단일 문자열 |
| `source_type` | VARCHAR(32) | 현재 "agent" 고정 |
| `created_at` | INT64 | unix timestamp |
| `metadata_json` | VARCHAR(2048) | sectors/entities JSON |
| `embedding` | FLOAT_VECTOR(1536) | cosine 검색용 |

**Note**: JSON 필드는 pymilvus 2.4.4 dynamic field 의존성 회피로 VARCHAR JSON 직렬화 사용.  
TODO(STEP-010+): JSON field + partition 마이그레이션.

## EmbeddingClient

`backend/app/services/embedding_client.py`

- `MockEmbeddingClient`: stdlib-only deterministic. sha256 시드 → float list → L2 정규화. 같은 text → 같은 vector.
- `OpenAIEmbeddingClient`: `text-embedding-3-small`, tenacity 2회 retry (RateLimitError/APITimeoutError).
- factory: `create_embedding_client(provider, model)`, singleton: `get_embedding_client()`.
- 기본: `EMBEDDING_PROVIDER=mock`. OpenAI opt-in: `EMBEDDING_PROVIDER=openai`.

## Insert 시점

`event_service.upsert_card` → `await session.commit()` 직후 → `try_index_card(card)`.  
Milvus 실패 시 `logger.warning` + swallow. Postgres write는 항상 유지.

## Search API

```
POST /api/internal/search-similar
Body: { "query_text": str, "top_k": int=5, "exclude_event_id": str|None }
Response: { "hits": [ { event_id, card_id, score, title, summary, theme } ] }
```

인증: STEP 006 범위 외. TODO(STEP-008+): internal-only middleware.

## Agent 연결

`agents/tools/vector_search.search_similar(text, top_k, exclude_event_id)`  
→ `httpx.post(BACKEND_INTERNAL_URL + "/api/internal/search-similar")`

`retrieve_past_context` 노드: hits → `state.past_context` (str 요약 리스트) + `state.retrieved_context` (dict 리스트).  
실패 시 `["[fallback-context]"]` + `llm_errors` 누적.

## Deduplicate

현재: sha256 hash pass-through. TODO(STEP-010): vector cosine threshold 기반 dedup 정책.  
(`agents/nodes/deduplicate.py`에 TODO 주석 추가됨)

## 비범위 / TODO

- KG-RAG, hybrid search, sparse retrieval
- partition / dynamic field 도입
- dedup vector threshold 알고리즘
- internal API 인증 middleware
- background task로 embed 분리 (STEP-008)
