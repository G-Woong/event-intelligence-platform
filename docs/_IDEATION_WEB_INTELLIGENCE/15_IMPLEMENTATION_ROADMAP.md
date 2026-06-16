# 15 — IMPLEMENTATION ROADMAP (Phase 0~10)

> 원칙: 토대(배선·dedup·mock 해제)를 먼저 닫고, 고급 layer(검색확장·rerank·GraphRAG)는 그 위에 얹는다. 순서 역전 금지(적대적 비판). 각 Phase는 측정 가능한 acceptance를 가진다.

---

## P0/P1 우선순위 요약

```text
P0  ingestion 57소스 엔진 → 실 raw_events Postgres 배선 (mirror→DB)
P1  Redis Stream/DLQ/retry/monitoring 실배선 + 6 mock 노드 결정론분 해제 + dedup/clustering
P2  Search API expansion layer (provider-agnostic)
P3  OpenSearch+vector hybrid + reranker + nori
P4  LLM SourceSupervisor 실 provider 연결
P5  Event clustering/timeline/ranking 완성
P6  KG-RAG/GraphRAG (고가치 multi-hop 한정)
P7  Commercial dashboard/alert/report/API
```

---

## Phase 0 — Canonical docs & architecture freeze
- Goal: 현재 상태/목표 아키텍처 동결. **(완료)** `_CANONICAL/` 11 + 본 ideation 세트.
- Acceptance: 본 문서 세트 커밋, P0 명시. Do-not-do: 코드 변경.

## Phase 1 — ingestion → raw_events 실배선 (P0)
- Goal: ingestion seed가 실 raw_events PG에 적재.
- Required: `bridge_to_raw_events` db_writer 주입(workers POST), payload→RawEvent 계약 정합.
- Dependencies: workers raw_events API(구현됨).
- Acceptance: ingestion seed 1건+ raw_events PG row 확인, mirror→DB 전환, A→B e2e green.
- Risks: 스키마 drift(compat test), mirror 착시. Complexity: 중. Do-not-do: 소스 추가, 우회.

## Phase 2 — Redis stream / worker / DLQ / monitoring
- Goal: A EventQueue Redis 배선 + DLQ/retry/quota + cost/rate 가시화.
- Required: `event_queue.py` `_redis_*` 구현(B 헬퍼 위임), Celery beat(스케줄), DLQ stream, rate_limit ZSET, cost/rate 대시보드.
- Acceptance: enqueue→consume→ack, PEL→DLQ 회수, cost+rate+health 3축 노출. Complexity: 중상.

## Phase 3 — 6 mock 노드 해제 + dedup/clustering
- Goal: LangGraph 6 mock 중 결정론 가능분(entity_linking=NER, evidence_check=URL/출처 검증) 실구현 + cross-source dedup/cluster.
- Required: NER, MinHash LSH, 임베딩 HDBSCAN, prompt injection 방어 layer.
- Acceptance: end-to-end 카드 1건 실데이터 생성, cluster purity≥0.8, leakage<10%. Complexity: 상.

## Phase 4 — Search API expansion layer
- Goal: provider-agnostic tiered router(무료→유료), event 트리거 enrichment.
- Acceptance: candidate→확장→dedup→raw_events, per-event/월 예산 guard, 다중 fallback. Complexity: 중.

## Phase 5 — hybrid search + reranker + nori (indexing)
- Goal: RRF hybrid → cross-encoder rerank → nori.
- Acceptance: golden set nDCG/Recall@k 베이스라인, p99 내, fusion-only 폴백. Complexity: 중.

## Phase 6 — LLM SourceSupervisor 실 provider 연결
- Goal: `llm_propose` 콜백 실연결(allowed 게이트 강제, 끄면 규칙기반 동작).
- Acceptance: 옵션 on/off 모두 동작, audit trace, fallback 100%, eval CI. Complexity: 중.

## Phase 7 — Event clustering / ranking / timeline 완성
- Goal: 4신호 랭킹(freshness/corroboration/diversity/impact) + timeline(FSD).
- Acceptance: 설명가능 랭킹, timeline 단조 정렬, corroboration precision 측정. Complexity: 중상.

## Phase 8 — KG-RAG / GraphRAG (조건부)
- Goal: vector RAG로 못 푸는 multi-hop use case 한정 PoC.
- Why now: mock 엔티티 제거 + vector RAG 커버리지 실측 이후에만.
- Acceptance: PoC 게이트(사전 성공기준) 통과, 근거 노드 인용, ROI 추적. Complexity: 상. Do-not-do: <1000 엔티티에 도입, mock 위 그래프.

## Phase 9 — Commercial pilot (dashboard/alert/report/API)
- Goal: 단일 vertical alert/API 베타 + 파일럿.
- Required: evidence 구조화, alert 규칙/채널, API 키 인증/rate plan.
- Acceptance: freemium 출시, alert 구독 가동, 파일럿 LOI 3, API 베타. Complexity: 상.

## Phase 10 — Enterprise-grade security / compliance
- Goal: Admin RBAC(빈토큰 bypass 해제), SSRF allowlist, retention TTL, PII 스크럽, 라이선스 매트릭스, prod docker/TLS.
- Acceptance: 상업 공개 선행조건(14) 전수 충족, secret scan PASS. Complexity: 상.

---

## 의존 그래프

```text
P1(배선) ─┬─> P2(큐/관측) ─┬─> P4(검색확장)
          └─> P3(mock해제/dedup) ─┬─> P5(hybrid/rerank)
                                  ├─> P7(clustering/rank) ─> P8(GraphRAG, 조건부)
                                  └─> P6(supervisor 실연결)
P5+P7 ─> P9(상용 alert/API) ─> P10(enterprise 보안/컴플라이언스)
```

> P8(GraphRAG)·P4 유료 routine 호출은 P1+P3 이후. 토대 없이 고급 layer 욕심 금지.
