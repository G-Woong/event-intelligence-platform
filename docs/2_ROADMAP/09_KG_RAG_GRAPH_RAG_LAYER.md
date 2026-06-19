# 09 — KG-RAG / GRAPH RAG LAYER (L7)

> 결론: **지금 도입하지 않는다.** 현재 entity_linking/sector_mapping이 mock(고정값)이라 엔티티 추출 자체가 없다. mock 위에 그래프를 쌓으면 "쓰레기 입력으로 만든 정교한 추론" — 구조 비용만 발생하고 가치는 0이다. GraphRAG는 vector RAG의 **3-5x 비용**(그래프 구축 인덱싱 10-100x)이며, 이 플랫폼 질의 대부분(섹터별 최신/키워드)은 vector RAG로 1/10 비용에 동등 결과를 낸다.

---

## 1. 현재 상태

- KG-RAG/GraphRAG 없음. event_cards에 `entities(JSONB)`/theme/sectors 필드는 있으나 그래프 저장/추론 없음.
- `entity_linking.py` MOCK(`[mock-entity-1]` 고정), `sector_mapping` MOCK. **엔티티 추출이 존재하지 않는다.**
- raw_events↔event_cards FK 관계만 RDB로 존재.

## 2. 목표 그래프 설계 (미래, RDB 투영)

5종 노드: `Entity`(인물/조직/지역/자산), `Event`(event_card 1:1), `Source`(+신뢰등급), `Time`(발생/관측, 버킷), `Evidence`(raw_event 단편).
핵심 엣지: `(Event)-[:MENTIONS]->(Entity)`, `(Entity)-[:RELATED_TO {type,weight}]->(Entity)`, `(Event)-[:REPORTED_BY]->(Source)`, `(Evidence)-[:SUPPORTS|CONTRADICTS]->(Event)`, `(Event)-[:OCCURRED_AT]->(Time)`, `(Event)-[:PRECEDES]->(Event)`.

> **그래프는 RDB의 투영(projection)으로 설계** — 원본(SoT)은 RDB, 그래프는 단방향 동기 파생. 그래프를 원본 삼으면 이중 진실 소스로 정합성 붕괴.

## 3. GraphRAG가 필요한 질문 vs 아닌 질문

| GraphRAG 필요(multi-hop/관계추론) | vector RAG로 충분 |
|---|---|
| "이 제재 이벤트와 2-3홉으로 연결된 다른 사건" | "오늘 에너지 섹터 최신 이벤트" |
| "엔티티 A·B 동시 언급 + 상충 evidence" | "키워드 X 포함 이벤트" |
| "공급망 노드 충격의 섹터 전파" | "특정 소스 최근 카드" |

현재 플랫폼 질의의 대부분이 우측(후자)이다.

## 4. 도구 / 비용

- 단계적: vector+메타데이터 RAG를 P0/P3로, GraphRAG는 고가치 use case에만.
- 프로토타입: LlamaIndex `PropertyGraphIndex`(라벨노드+kg_extractors) → 규모/동시성 커지면 Neo4j(성숙·운영도구) 또는 Memgraph(인메모리·스트리밍).
- 비용: vector 대비 운영 3-5x, 그래프 구축 인덱싱 10-100x. MS GraphRAG community summarization은 "전체 코퍼스 요약"엔 강하나 실시간 스트림과 인덱싱 주기 충돌.

## 5. 위험

- **entity resolution이 최대 유지보수 부담**: 이름기반 매칭 동명이인 충돌, 미관리 소스 30-40% 중복/모호 노드. → canonical_id(위키데이터 등)·alias 테이블·신뢰도 기반 human-in-loop.
- relation extraction 환각 관계(근거 인용 필수, 화이트리스트 제약).
- 인과(CAUSES) 라벨의 명예훼손/투자조언 오해 → PRECEDES만, 인물 인과 엣지 보류.
- 그래프 답변 환각 → 근거 노드/경로 인용 필수.

## 6. 도입 게이트 (검증기준)

(1) entity_linking/sector_mapping mock → 실 NER·실 분류로 전부 대체, (2) vector+메타 hybrid RAG가 P0 안정화 + 질의 커버리지 실측, (3) vector RAG로 못 푸는 multi-hop 질의가 로그로 검증된 고가치 use case에 한해, (4) RDB 투영 + PoC 게이트(사전 성공기준) 통과, (5) 모든 답변에 근거 노드/경로 인용, (6) ROI(vector 대비 3-5x 정당화)가 대시보드로 추적될 때.
