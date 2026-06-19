# 08 — RAG & VECTOR DB LAYER (L5 저장·인덱싱 / L6 검색·리랭킹)

> 결론: 3엔진(PG SoT / Milvus 의미 / OpenSearch 키워드)은 구현돼 있으나 검색이 **의미·키워드로 분리**돼 융합되지 않는다. 도입 순서는 **hybrid(BM25+dense, RRF) → cross-encoder reranker → 한국어 nori**. evidence URL+summary 중심(전문 저장 금지)이므로 카드 단위가 곧 chunk.

---

## 1. 현재 상태 (IMPLEMENTED)

- Postgres raw_events/event_cards = SoT. `upsert_card → PG commit → Milvus insert(swallow) → OpenSearch index(swallow)`.
- Milvus `event_embeddings` dim=1536 IVF_FLAT/COSINE — `retrieve_past_context` 노드가 top-k 실호출.
- OpenSearch `event_cards` standard analyzer, multi_match bool/must title^2 — 키워드만.
- 임베딩 Mock(sha256 결정론) ↔ OpenAI(text-embedding-3-small) via `EMBEDDING_PROVIDER`. pymilvus 2.4.4.

## 2. 갭

- **hybrid 부재**: BM25 단독은 패러프레이즈에 약하고, dense 단독은 정확한 엔티티·날짜에 약하다.
- **reranker 부재**: query-aware 정밀 재정렬 없음.
- **nori 부재**: 한국어 형태소 분석 미적용.
- **swallow silent drift**: 인덱싱 실패가 메트릭 없이 묻힘 → PG와 인덱스 불일치.

## 3. 구현방향 (L6 도입 순서)

1. **RRF fusion** — Milvus(dense) + OpenSearch(BM25) 결과를 Reciprocal Rank Fusion으로 병합(점수 스케일 무관). 프로덕션 RAG 최소 베이스라인.
2. **2단계 retrieve→rerank** — top-1000 빠른 recall → cross-encoder로 top-100 정밀 재정렬. "top-1000→top-100"은 p99 내. 후보: Cohere rerank v4 Pro / Voyage rerank-2.5(instruction-following+긴 컨텍스트) / FlashRank(로컬 저비용).
3. **nori** — OpenSearch 한국어 형태소.
4. **이벤트 도메인 신호** — freshness time-decay(최신 가산), source diversity(MMR), event-cluster dedup.

## 4. L5 정합성 / 인프라 선택

- **outbox + DLQ**: PG 커밋과 인덱스 전파 정합성. 미전파 0건 수렴, swallow 실패를 메트릭으로 노출.
- **Milvus 유지 vs pgvector 통합**(ADR 필요):

| 옵션 | 장점 | 적합 |
|---|---|---|
| Milvus 2.5 유지 | hybrid ES 대비 ~30x, 50M+ | 대규모·고QPS 전망 |
| **pgvector 0.9 통합** | HNSW 50M까지, **별도 인프라 0**(PG=SoT+벡터), swallow drift 동시 완화 | 50M 미만·운영인력 제한 |

> 현 데이터 규모가 50M 미만이고 운영이 제한적이면 pgvector 통합이 인프라 1개 제거 + 정합성 단순화. 대규모 전망이면 Milvus 유지.

## 5. 비용 / 위험

- OpenAI 임베딩 비용(대량) → dedup 후에만 임베딩, content_hash 캐시, batch API.
- reranker latency spike → 비동기/배치, 장애 시 fusion-only 폴백.
- dim=1536 모델 락인 → embedding_model 버전 필드.
- 원칙: 랭킹이 추천(매수/매도)으로 비치지 않게 정보 환원 톤(§1).

## 6. 검증기준

hybrid+RRF baseline 동작, 2단계 retrieve→rerank가 p99 내, 이벤트 신호(freshness/diversity/cluster-dedup) 반영, nori로 한국어 recall 확보, golden set nDCG/Recall@k/MRR/Diversity@k 베이스라인 통과, reranker 장애 폴백 + 투자조언 미출력 가드, 3엔진 동일 card_id·미전파 0.
