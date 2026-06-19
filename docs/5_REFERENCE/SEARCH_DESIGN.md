# SEARCH_DESIGN.md — Event Intelligence 검색 아키텍처

## 역할 분리

| 엔진 | 역할 | 강점 |
|---|---|---|
| **Milvus** | 의미 기반 유사 사건 검색 | embedding cosine similarity, RAG context retrieval |
| **OpenSearch** | 키워드 / 전문(full-text) 검색 | BM25, field boosting, keyword filter |
| **Postgres** | 컬럼 필터 조회 | theme/sector/status exact match, 정렬 |

STEP 009 기준: **Hybrid retrieval(Milvus + OpenSearch reranking)은 STEP 011+ 예정**.

---

## OpenSearch Index: `event_cards`

### Mapping (standard analyzer, STEP 009)

```json
{
  "mappings": {
    "properties": {
      "card_id":          { "type": "keyword" },
      "title":            { "type": "text", "fields": { "keyword": { "type": "keyword" } } },
      "summary":          { "type": "text" },
      "text_all":         { "type": "text" },
      "theme":            { "type": "keyword" },
      "status":           { "type": "keyword" },
      "sectors":          { "type": "keyword" },
      "entities":         { "type": "keyword" },
      "confidence_score": { "type": "float" },
      "created_at":       { "type": "date" }
    }
  }
}
```

### `text_all` 필드

`title + summary + entities + sectors`를 공백으로 합산한 검색 전용 필드.
단일 `multi_match` 쿼리로 전체 텍스트를 커버한다.

---

## 검색 쿼리 패턴

```json
{
  "query": {
    "bool": {
      "must": [
        { "multi_match": { "query": "<q>", "fields": ["title^2", "summary", "text_all"] } }
      ],
      "filter": [
        { "term": { "theme": "<theme>" } },
        { "term": { "sectors": "<sector>" } },
        { "term": { "status": "<status>" } }
      ]
    }
  }
}
```

`title^2` — 제목 매치 가중치 2배.

---

## 색인 흐름

```
upsert_card (event_service)
  ├─► Postgres commit (source of truth)
  ├─► Milvus insert (vector_index_service.try_index_card)   ← 비동기, 실패 시 warning
  └─► OpenSearch index (opensearch_index_service.try_index_card)  ← 동기, 실패 시 warning
```

- **Source of truth**: Postgres. OpenSearch는 검색 가속용 파생 뷰.
- **Eventually consistent**: OpenSearch 실패 시 reindex 스크립트로 보정.
- **Milvus/OpenSearch 독립**: 하나 실패해도 다른 하나는 시도. 둘 다 실패해도 Postgres commit 유지.

---

## 장애 정책

| 시나리오 | 동작 |
|---|---|
| OpenSearch 다운 시 upsert | log warning, Postgres 저장 유지, OpenSearch는 eventually consistent |
| `GET /api/events/search` 시 OpenSearch 다운 | `503 search unavailable` (fallback 없음) |
| `POST /api/admin/search/reindex` | bulk scan + try_index_card, 실패 건은 warning |

---

## Reindex

### Admin endpoint
```
POST /api/admin/search/reindex
Body: { "limit": 1000, "dry_run": false }
Response: { "indexed": N, "dry_run": bool }
```

### Script
```bash
REINDEX_LIMIT=500 REINDEX_DRY_RUN=false python scripts/reindex_opensearch_once.py
```

---

## TODO (이번 단계 제외)

| 항목 | 예정 STEP |
|---|---|
| 한국어 nori analyzer | STEP 010+ |
| raw_events / comments 색인 통합 | STEP 010+ |
| Hybrid search (Milvus + OpenSearch reranking) | STEP 011+ |
| BM25 boost 튜닝 / synonym filter | STEP 011+ |
| OpenSearch security plugin (prod 인증) | prod 진입 시 |
| Bulk API reindex 최적화 | 대량 데이터 진입 시 |
| Search analytics / click tracking | STEP 012+ |
| OpenSearch cluster / sharding / replica | prod 진입 시 |
