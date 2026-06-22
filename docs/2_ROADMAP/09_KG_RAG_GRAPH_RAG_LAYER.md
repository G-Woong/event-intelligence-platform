# 09 — KG-RAG / GRAPH RAG LAYER (L7)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — **의도적 영구보류**. <1000 엔티티에선 도입 금지. risk 0(미도입이 곧 위험회피).
> │ **구현순위:** #15 (00_ROADMAP_INDEX) · **그룹:** C
> │ **검증 근거:** entity_linking/sector_mapping이 mock 고정값(`entity_linking.py` `[mock-entity-1]`) → 엔티티 추출 부재. 그래프 저장/추론 grep 0건. 미구현이 **설계 결정**(쌓을 토대 자체가 mock).
> │ **잔여(미구현):** 전부 미구현이며 **이것이 의도된 상태**다. 도입 게이트(§6) 6조건 미충족 동안 영구보류 유지.
> │ **완료정의(DoD):** 본 레이어의 DoD는 "구현"이 아니라 **"도입 게이트 6조건이 실측으로 충족될 때까지 도입하지 않음을 유지"**다. vector RAG 커버리지 실측 전 진입 금지.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획·영구보류).
> └────────────────────────────────────────────────────────

> 결론: **의도적으로 영구보류한다(지금 도입하지 않는다 — risk 0).** <1000 엔티티 규모에서는 GraphRAG 도입 금지가 결정이다. 현재 entity_linking/sector_mapping이 mock(고정값)이라 엔티티 추출 자체가 없다. mock 위에 그래프를 쌓으면 "쓰레기 입력으로 만든 정교한 추론" — 구조 비용만 발생하고 가치는 0이다. GraphRAG는 vector RAG의 **3-5x 비용**(그래프 구축 인덱싱 10-100x)이며, 이 플랫폼 질의 대부분(섹터별 최신/키워드)은 vector RAG로 1/10 비용에 동등 결과를 낸다. **미도입 = 위험회피**이므로 이 레이어의 열린 risk는 0이다.

---

## 1. 현재 상태

- KG-RAG/GraphRAG 없음. event_cards에 `entities(JSONB)`/theme/sectors 필드는 있으나 그래프 저장/추론 없음.
- `entity_linking.py` MOCK(`[mock-entity-1]` 고정), `sector_mapping` MOCK. **엔티티 추출이 존재하지 않는다.**
- raw_events↔event_cards FK 관계만 RDB로 존재.

## 2. 목표 그래프 설계 (미래, RDB 투영)

5종 노드: `Entity`(인물/조직/지역/자산), `Event`(event_card 1:1), `Source`(+신뢰등급), `Time`(발생/관측, 버킷), `Evidence`(raw_event 단편).
핵심 엣지: `(Event)-[:MENTIONS]->(Entity)`, `(Entity)-[:RELATED_TO {type,weight}]->(Entity)`, `(Event)-[:REPORTED_BY]->(Source)`, `(Evidence)-[:SUPPORTS|CONTRADICTS]->(Event)`, `(Event)-[:OCCURRED_AT]->(Time)`, `(Event)-[:PRECEDES]->(Event)`.

> **그래프는 RDB의 투영(projection)으로 설계** — 원본(SoT)은 RDB, 그래프는 단방향 동기 파생. 그래프를 원본 삼으면 이중 진실 소스로 정합성 붕괴.

### 2.1 Evidence Graph 2단계('증거↔증거')는 지금 GraphRAG가 아니다

ADR#16의 Evidence Graph는 2단계로 본다. **이 둘을 혼동하면 09 영구보류 원칙이 깨진다.**

| 단계 | 무엇 | 지금 어떻게 |
|---|---|---|
| 1단계 | Evidence ↔ Event(증거가 이 사건을 뒷받침) | **경량 JSONB부터** — `EVENT_SCHEMA.md §EvidenceNode`(`event_updates.evidence: list[EvidenceNode]`). 그래프 DB 불필요. |
| 2단계 | Evidence ↔ Evidence(증거가 다른 증거를 **지지/반박**) | **지금 GraphRAG로 색인하지 않는다.** 이 지지/반박 관계는 **Agent Debate(19 §9)가 자연어로 생성**한다 — 에이전트가 "근거 A는 근거 B와 상충한다"를 발화. 정형 그래프 엣지(`SUPPORTS|CONTRADICTS`)는 <1000 엔티티에선 과잉. |

> **핵심:** 증거↔증거 관계가 필요해 보여도, 그것은 **GraphRAG 도입 신호가 아니라 Agent Debate(자연어)·경량 JSONB로 먼저 푼다.** 정형 그래프 엣지로 승격하는 시점은 §6 도입 게이트(특히 vector RAG 커버리지 실측 후 + multi-hop 질의가 로그로 검증된 고가치 use case)에 종속된다. `EVENT_SCHEMA.md §EvidenceNode`(JSONB) → `19 §8`(Evidence Graph 스펙) → `19 §9`(Agent Debate) 순으로 경량부터 쌓는다.

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

## 6. 도입 게이트 (검증기준 — 영구보류 해제 조건)

> **진입 시점 = vector RAG 커버리지 실측 후.** 아래 6조건이 **전부** 충족되기 전엔 영구보류를 유지한다(부분 충족으로 도입 금지). 어느 하나라도 미충족이면 도입은 과잉이다.

(1) entity_linking/sector_mapping mock → 실 NER·실 분류로 전부 대체, (2) **vector+메타 hybrid RAG(08)가 P0 안정화 + 질의 커버리지 실측 완료**(이것이 진입 선행조건), (3) vector RAG로 못 푸는 multi-hop 질의가 로그로 검증된 고가치 use case에 한해, (4) RDB 투영 + PoC 게이트(사전 성공기준) 통과, (5) 모든 답변에 근거 노드/경로 인용, (6) ROI(vector 대비 3-5x 정당화)가 대시보드로 추적될 때.

> **그 전까지:** 증거↔증거 관계 욕구는 §2.1대로 **Agent Debate(19 §9, 자연어) + 경량 JSONB(EVENT_SCHEMA EvidenceNode)**로 흡수한다. GraphRAG는 도입하지 않는다.

> 상호참조: `00_ROADMAP_INDEX`(순위 #15) · `08`(vector RAG 커버리지 — 진입 선행) · `12`(Event clustering) · `19 §8`(Evidence Graph) · `19 §9`(Agent Debate) · `EVENT_SCHEMA.md §EvidenceNode` · `_DECISIONS/2026-06.md` ADR#16.
