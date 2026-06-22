# 08 — RAG & VECTOR DB LAYER (L5 저장·인덱싱 / L6 검색·리랭킹)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — §1 3엔진 색인·Milvus top-k 토대는 DONE; §2~ hybrid/RRF/rerank/nori는 0% 미구현.
> │ **구현순위:** #13 (00_ROADMAP_INDEX) · **그룹:** C
> │ **검증 근거:** §1 토대 DONE — `upsert_card → PG commit → Milvus insert(swallow) → OpenSearch index(swallow)`, Milvus `event_embeddings` IVF_FLAT/COSINE를 `retrieve_past_context` 노드가 top-k 실호출. §2~ 갭은 `agents/` grep 0건(RRF/rerank/nori 부재).
> │ **잔여(미구현):** hybrid(BM25+dense, RRF) 0%, cross-encoder reranker 0%, 한국어 nori 0%, 이벤트 신호(heat/event-cluster dedup/domains diversity) 0%, Evidence Graph 색인 0%, golden set 메트릭 베이스라인 부재.
> │ **완료정의(DoD):** hybrid+RRF baseline 동작, 2단계 retrieve→rerank p99 내, 이벤트 신호 반영, nori 한국어 recall, golden set nDCG/Recall@k/MRR/Diversity@k 통과, 3엔진 동일 card_id·미전파 0, 투자조언 미출력 가드.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 결론: §1 3엔진(PG SoT / Milvus 의미 / OpenSearch 키워드) 색인 토대와 Milvus top-k 실호출은 **DONE**이다. 그러나 검색이 **의미·키워드로 분리**돼 융합되지 않는다(§2~ 0% 미구현). 도입 순서는 **hybrid(BM25+dense, RRF) → cross-encoder reranker → 한국어 nori**. evidence URL+summary 중심(전문 저장 금지)이므로 **임베딩 단위는 곧 카드=chunk였으나, Event 타임라인 전환(ADR#16) 이후 카드는 "Event의 한 단면 snapshot"이다 — 무엇을 임베딩 단위로 삼을지(Event/Update/snapshot 다층)가 결정질문**이다(§2.1).

---

## 1. 현재 상태 (§1 토대 = DONE)

- Postgres raw_events/event_cards = SoT. `upsert_card → PG commit → Milvus insert(swallow) → OpenSearch index(swallow)`. **DONE.**
- Milvus `event_embeddings` dim=1536 IVF_FLAT/COSINE — `retrieve_past_context` 노드가 top-k 실호출. **DONE.**
- OpenSearch `event_cards` standard analyzer, multi_match bool/must title^2 — 키워드만. **DONE(키워드 한정).**
- 임베딩 Mock(sha256 결정론) ↔ OpenAI(text-embedding-3-small) via `EMBEDDING_PROVIDER`. pymilvus 2.4.4.

> §1은 "색인 토대가 살아있다"는 뜻이며, **§2 이하 검색 융합/리랭킹/한국어/이벤트 신호는 0% 미구현**이다. 이 문서의 나머지는 ROADMAP(미래계획)다.

## 2. 갭 (§2~ 0% 미구현)

- **hybrid 부재**: BM25 단독은 패러프레이즈에 약하고, dense 단독은 정확한 엔티티·날짜에 약하다.
- **reranker 부재**: query-aware 정밀 재정렬 없음.
- **nori 부재**: 한국어 형태소 분석 미적용.
- **swallow silent drift**: 인덱싱 실패가 메트릭 없이 묻힘 → PG와 인덱스 불일치.
- **이벤트 신호 부재**: heat·event-cluster dedup·domains diversity 미반영.

## 2.1 임베딩 단위 재정의 — 카드=chunk 전제 개정 (결정질문)

이전 판본은 "카드 단위가 곧 chunk"라 단정했다. **ADR#16(Event 타임라인)** 이후 카드는 최종산출물이 아니라 **Event의 현재 단면(snapshot)**이다. 따라서 임베딩 단위는 단일 결정이 아니라 **다층 결정질문**이다.

| 후보 임베딩 단위 | 의미 | 트레이드오프 |
|---|---|---|
| **Event(주제)** | 안정 주제 1벡터(canonical_title 기반) | 주제 검색엔 강하나 시간변화 추적 약함 |
| **EventUpdate(변화분)** | append-only Update마다 1벡터 | 시계열 변화 검색에 강함, 벡터 수 팽창 |
| **snapshot card(현재 단면)** | 현 카드 1벡터(=기존 동작) | 호환·단순, "최신 단면"만 표현 |

> **결정질문(구현 전 UNKNOWN):** 검색 의도가 "주제 발견"이면 Event 임베딩, "이 사건 어떻게 변했나"면 Update 임베딩, "지금 상태"면 snapshot 임베딩이 맞다. **다층(Event+Update+snapshot) 동시 색인**이 이상적이나 비용·정합성 증가 → golden set로 어느 층이 nDCG를 끌어올리는지 실측 후 결정. 임베딩 생성 자체는 **LAYER F 경계 밖**(수집이 아니라 색인 — §2.3).

## 2.2 Evidence Graph 색인

ADR#16의 EvidenceNode(`evidence: list[EvidenceNode]`, `EVENT_SCHEMA.md §EvidenceNode)는 검색 대상이다. 증거 단편(소스·신뢰등급·인용)을 색인하면 "이 주장의 근거" 검색·corroboration 랭킹이 가능하다.

- **무엇을 색인하나:** EvidenceNode의 텍스트(요약/인용)+메타(source, trust_tier). 전문 저장 금지(§DATA_POLICY) — URL+요약만.
- **GraphRAG 아님:** 증거↔증거(지지/반박) 관계는 **지금 GraphRAG로 색인하지 않는다**(09 영구보류). vector RAG + JSONB 메타로 충분; 관계는 Agent Debate(19 §9)가 자연어로 생성.
- **링크:** `09`(GraphRAG 경계) · `19 §8`(Evidence Graph 스펙) · `EVENT_SCHEMA.md §EvidenceNode`.

## 2.3 임베딩 = LAYER F 경계 밖 (P/G/F 정합)

ADR#14의 LAYER F(Fetch, 결정론 실행)는 **수집**이다. **임베딩 생성은 수집이 아니라 색인(L5)**이므로 P/G/F 경계 밖이다. 혼동 금지: LAYER F는 "어떻게 가져올지"를 결정론 실행하고, 임베딩은 "가져온 것을 어떻게 인덱싱할지"다. SLM body fallback(LAYER F 최후폴백)이 본문을 채워도, 그 본문의 임베딩 여부는 L5 색인 정책이 결정한다.

## 3. 구현방향 (L6 도입 순서)

1. **RRF fusion** — Milvus(dense) + OpenSearch(BM25) 결과를 Reciprocal Rank Fusion으로 병합(점수 스케일 무관). 프로덕션 RAG 최소 베이스라인.
2. **2단계 retrieve→rerank** — top-1000 빠른 recall → cross-encoder로 top-100 정밀 재정렬. "top-1000→top-100"은 p99 내. 후보: Cohere rerank v4 Pro / Voyage rerank-2.5(instruction-following+긴 컨텍스트) / FlashRank(로컬 저비용).
3. **nori** — OpenSearch 한국어 형태소.

### 3.4 이벤트 도메인 신호 (개정 — heat 중심)

검색 랭킹에 이벤트 인텔리전스 고유 신호를 반영한다(투자 권유 아님 — 정보 환원 톤 §1).

- **freshness = heat**: 단순 time-decay가 아니라 **heat(시계열 활성도, half-life 감쇠)**를 신선도 신호로 사용. 최근 Update가 잦은 Event가 가산(ADR#16 `events.heat`). heat는 "지금 뜨거운 사건"을 표면화하되 가치판단(매수/매도) 아님.
- **event-cluster dedup**: 같은 사건의 N개 소스 보도는 제거가 아니라 corroboration 신호(12 §). 검색 결과에서 같은 cluster는 1개 대표 + 멤버 source 수 노출.
- **domains diversity**: 결과가 한 도메인(섹터)에 쏠리지 않게 domains 다양성(MMR류)으로 분산. domains는 닫힌 8섹터가 아니라 **열린 2층(통제어휘 ~20 + free-form tags)**(ADR#16).

## 4. L5 정합성 / 인프라 선택

- **outbox + DLQ**: PG 커밋과 인덱스 전파 정합성. 미전파 0건 수렴, swallow 실패를 메트릭으로 노출.
- **Milvus 유지 vs pgvector 통합**(ADR 필요):

| 옵션 | 장점 | 적합 |
|---|---|---|
| Milvus 2.5 유지 | hybrid ES 대비 ~30x, 50M+ | 대규모·고QPS 전망 |
| **pgvector 0.9 통합** | HNSW 50M까지, **별도 인프라 0**(PG=SoT+벡터), swallow drift 동시 완화 | 50M 미만·운영인력 제한 |

> **pgvector ADR에 추가 인자(ADR#16 결합):** ① **Event/event_updates가 PG 테이블**이므로 pgvector면 Event·Update·snapshot 임베딩을 같은 트랜잭션에 색인(2층 정합성↑, swallow drift 제거). ② EvidenceNode는 **JSONB**(`evidence` 컬럼)이라, pgvector면 JSONB 메타 필터(`source`/`trust_tier`)와 벡터 검색을 단일 SQL로 결합(별도 OpenSearch 왕복 불필요). ③ 현 데이터 규모 50M 미만 + 운영 제한이면 pgvector 통합이 인프라 1개 제거 + Event 정합성 단순화. 대규모 전망이면 Milvus 유지.

## 5. 비용 / 위험

- OpenAI 임베딩 비용(대량) → dedup 후에만 임베딩, content_hash 캐시, batch API. Event/Update 다층 임베딩 시 벡터 수 팽창 → Update 임베딩은 heat 임계 이상 Event만(선택).
- reranker latency spike → 비동기/배치, 장애 시 fusion-only 폴백.
- dim=1536 모델 락인 → embedding_model 버전 필드.
- 원칙: 랭킹이 추천(매수/매도)으로 비치지 않게 정보 환원 톤(§1). heat 가산이 "이 사건 사라"로 오독되지 않게 정보 환원.

## 6. 검증기준 (golden set 메트릭)

hybrid+RRF baseline 동작, 2단계 retrieve→rerank가 p99 내, 이벤트 신호(heat/domains-diversity/event-cluster-dedup) 반영, nori로 한국어 recall 확보, **golden set 메트릭 베이스라인 통과 — nDCG@k / Recall@k / MRR / Diversity@k**(각 베이스라인 수치는 golden set 구축 후 확정, 현재 UNKNOWN), reranker 장애 폴백(fusion-only) + 투자조언 미출력 가드, 3엔진 동일 card_id·미전파 0.

> 상호참조: `00_ROADMAP_INDEX`(순위 #13) · `09`(GraphRAG 영구보류) · `12`(event-cluster dedup/heat) · `19 §8`(Evidence Graph) · `EVENT_SCHEMA.md`(Event/EventUpdate/EvidenceNode) · `5_REFERENCE/RAG_VECTOR_DESIGN.md` · `DATA_POLICY.md`(전문저장 금지) · `_DECISIONS/2026-06.md` ADR#14/#16.
