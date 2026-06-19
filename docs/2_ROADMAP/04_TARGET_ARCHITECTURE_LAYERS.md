# 04 — TARGET ARCHITECTURE LAYERS (L0~L14)

> 목표 아키텍처를 layer별 책임으로 분리. 각 layer = 현재상태 / 목표 / 구현방향 / 비용 / 위험 / 검증기준. 상세 체크리스트는 16, layer별 심화는 05~13.

---

## 0. 전체 그림

```text
L0  Product thesis / positioning ───────────────── (왜/누구에게)
L1  Source discovery & seed ingestion  ── ingestion/ 57소스 [구현]
L2  Search expansion (external web)     ── 검색 API 확장 [미구현]
L3  Policy-safe fetch / body / evidence ── EvidenceGate/policy_probe [구현]
L4  EventQueue / raw_events / Redis      ── A→B 배선 [P0 미배선]
L5  Storage & indexing (PG/OS/vector)    ── 3엔진 [구현, 정합성 갭]
L6  RAG retrieval & reranking            ── Milvus top-k [부분], hybrid/rerank [미구현]
L7  KG-RAG / GraphRAG / entity graph     ── [미구현, 고가치 한정]
L8  Event clustering / dedup / rank      ── dedupe_key [부분], clustering [미구현]
L9  LLM SourceSupervisor / judge         ── 인터페이스만 [부분]
L10 Agent orchestration (LangGraph)      ── 11노드 5R/6M [부분]
L11 Safety / legal / trust / no-bypass   ── 게이트/정책 [구현]
L12 Monitoring / observability / cost    ── monitoring.py [구현], cost/rate 가시화 [부분]
L13 Product surface (dashboard/alert/API)── dashboard [구현], alert/API [미구현]
L14 Commercialization / pricing / GTM    ── [전략]
```

데이터 흐름: **L1/L2 → L3 → L4 → L5 → (L6/L7) → L8 → L9/L10 → L13**, 가로질러 L11(안전)·L12(관측)이 모든 layer를 감싼다. L0/L14는 방향을 규정한다.

## 1. layer 요약표

| Layer | 현재 | 목표 | 우선순위 | 핵심 위험 | 검증기준 |
|---|---|---|---|---|---|
| **L0** Product thesis | 전략 분산 | event intelligence 포지션 확정 | — | "검색엔진" 착각 | 차별점 3 + 수익경로 2 문서화 |
| **L1** Source discovery | 57소스 deterministic [구현] | discovery↔ingestion 분리, 지속검증 | P1 | 단발 LIVE를 READY로 과신 | schedulable 소스 capability 100% |
| **L2** Search expansion | 없음 | provider-agnostic, 무료→유료 tiered | P2 | 단일 provider 의존, 비용폭발 | event당 예산 guard + 다중 fallback |
| **L3** Policy-safe fetch | EvidenceGate/probe [구현] | SSRF allowlist, retention TTL | P1 | SSRF, 전문 저장 | synthetic/local URL 거부, 전문 0 |
| **L4** EventQueue/raw_events | **A→B 미배선** | Redis Stream 실배선 + DLQ | **P0** | mirror가 DB 착시 | ingestion seed 1건 raw_events 도달 |
| **L5** Storage/indexing | 3엔진 [구현] | 정합성(outbox/DLQ), nori, pgvector 검토 | P3 | swallow silent drift | 3엔진 동일 card_id, 미전파 0 |
| **L6** RAG/rerank | Milvus top-k [부분] | hybrid(RRF)→rerank→nori | P3 | keyword-only recall 손실 | nDCG/Recall@k 베이스라인 |
| **L7** KG-RAG | 없음 | 고가치 multi-hop 한정 PoC | P6 | mock 엔티티 위 그래프, 3-5x 비용 | mock 제거 후 진입, ROI 추적 |
| **L8** Clustering/rank | dedupe_key [부분] | dedup→cluster→timeline→rank | P1 | near-dup 범람, corroboration 부풀림 | purity≥0.8, leakage<10% |
| **L9** Supervisor/judge | 인터페이스만 [부분] | judge(단기)↔supervisor(장기) 분리 | P4 | LLM 비결정/우회 제안 | allowed 게이트, fallback 100% |
| **L10** Orchestration | 11노드 5R/6M [부분] | mock 해제, 0.2.76 유지 | P1 | LLM 만능주의, 비용 | 6 mock 실연결, audit trace |
| **L11** Safety/legal | 게이트/정책 [구현] | SSRF·retention·license 매트릭스 | 상시 | 우회·전문저장·명예훼손 | 우회 0, secret scan PASS |
| **L12** Monitoring | monitoring.py [구현] | cost/rate 실시간 가시화 | P1 | 비용 폭발, 침묵 실패 | cost+rate+health 3축 노출 |
| **L13** Product surface | dashboard [구현] | alert→API→report | P7 | mock UI 노출, 신뢰 훼손 | evidence 구조화, alert 동작 |
| **L14** Commercialization | 전략 | vertical beachhead, hybrid 가격 | — | 광고 의존, per-seat | 파일럿 LOI 3 + 가격표 |

## 2. layer 간 핵심 계약(인터페이스)

- **L1/L2 → L3**: 모든 fetch는 `source_policy_probe` 단일 경유(우회 코드 우발 실행 차단).
- **L3 → L4**: `bridge_to_raw_events.to_raw_event_create`(content_hash dedup, url NOT NULL, preview_only raw_text="").
- **L4 → L5**: raw_events PG 적재 후 upsert_card → Milvus/OpenSearch 전파(현재 swallow → outbox 권장).
- **L8 → L13**: event_cards는 article이 아니라 **cluster 대표**를 발행. confidence = corroboration+diversity 매핑.
- **L11**(가로): EvidenceGate가 synthetic/dead/local URL을 evidence 자격에서 차단(승격 게이트). fetch 진입점에도 동일 룰 복제 필요.
- **L9/L10**(가로): LLM 제안은 `allowed-strategy` 집합 안에서만 채택, `UNSAFE_STRATEGIES`는 영구 차단. 외부 콘텐츠는 untrusted로 격리.

## 3. 설계 원칙

1. **deterministic 기본, LLM은 가치지점에만** — 수집은 재현성·감사·rate-limit 준수가 생명. LLM은 판단만, 실행 안 함.
2. **evidence 중심 저장** — 전문 저장 금지, URL+summary+metadata. 카드 단위 = 자연스러운 chunk.
3. **provider-agnostic** — 검색·임베딩·rerank·LLM 모두 추상화 뒤 교체 가능. 단일 provider 락인 금지.
4. **정합성보다 가용성 격리, 그러나 가시화** — Milvus/OpenSearch 인덱싱 swallow는 best-effort지만 실패를 메트릭으로 노출.
5. **cluster가 단위** — dedup(같은 글)과 cluster(같은 사건)는 다른 layer. corroboration은 제거 대상이 아니라 신뢰 신호.
6. **모든 layer에 검증기준** — "동작하게"가 아니라 측정 가능한 acceptance.

## 4. 무엇을 지금 하지 않는가 (scope 고정)

L7(GraphRAG), L2 유료 routine 호출, L13 alert 이상 고급 product는 **L4 배선 + L8 dedup/cluster + L10 mock 해제** 이후다. 토대가 JSONL 파일 큐인데 KG-RAG를 얹는 것은 순서 역전이다(적대적 비판).
