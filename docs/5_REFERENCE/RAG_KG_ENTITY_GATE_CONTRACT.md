# RAG / KG / Entity Gate Contract

> **Status: CONTRACT-ONLY · runtime No-Go (ADR#78).**
> RAG ingestion·entity extraction·KG edge·GraphRAG·public Intelligence Unit 은 **R1~R7 게이트 통과 전까지
> mock/contract 로만** 존재한다(실 runtime 0). 이 문서는 그 **적재·간선·검색·공개**의 전제조건을 못박아,
> "검증 없이 KG edge 생성"·"raw corpus 를 RAG 에 직접"·"raw source → public IU 둔갑"을 구조적으로 차단한다.
> 관련: `LLM_EVIDENCE_PACKET_CONTRACT.md`, `INTELLIGENCE_UNIT_CONTRACT.md` §4, `RAG_KG_AGENT_READINESS.md` §6b
> (R1 gold → R2 MERGE_GATE → R3 embedding → R4 entity → R5 KG → R6 GraphRAG → R7 IU·현재 전부 No-Go).

## 0. 전제 (ADR#78 근거)

production gold floor 0(R1 FAIL)·MERGE_GATE 미충족(결정론 adjudicator precision 0.57)·detectable cross-source
overlap 0(ADR#77 100쌍/ADR#78 fed_rate 30쌍 전부 below floor). 따라서 **검증된 event identity 가 아직 없다.**
identity 없는 RAG/KG 는 환각·오링크를 production 으로 흘린다. 이 계약은 각 단계가 **선행 게이트의 산출물**만
입력으로 받도록 강제한다.

## 1. RAG ingestion gate (적재 전제조건)

적재되는 모든 chunk 는 다음 메타를 **반드시** 갖는다:

| 필드 | 규칙 |
|---|---|
| `storage_class` | `verified` / `candidate` / `reaction` / `signal` / `enrichment` / `url_candidate` 중 하나(혼합 금지) |
| `source_role` | official/article/news/community/market/catalog/search/unknown |
| `provenance` | canonical_url + published_at + source_id (없으면 적재 거부) |
| `identity_status` | stage①anchor / ②link / ③adjudication / **none**(미해소면 candidate 이하) |
| `merge_gate_status` | `blocked`(기본) / `eligible`(gate 통과 시만) |
| `uncertainty` | evidence_sufficiency + source_agreement + unverified_claim |
| `allowed_retrieval_use` | `evidence` / `context_only` / `reaction_only` / `excluded` |

규칙:
- **raw unverified corpus 를 retrieval index 에 직접 연결 금지** — provenance/identity gate 통과분만.
- community/market/catalog/search 는 `evidence` storage_class 로 적재 **불가**(reaction/signal/enrichment/url_candidate).
- secret/raw PII/전문 raw body 는 적재 표면에서 마스킹·배제.

## 2. KG edge eligibility (간선 생성 전제조건)

| edge | 전제조건 (없으면 생성 금지) |
|---|---|
| `same_event` | **MERGE_GATE 통과**(precision≥0.98·FPR≤0.01·hard-neg FP=0) + production gold floor 충족. 그 전엔 `possible_link`(candidate)만. |
| `update_of` | **verified event identity**(stage④ 확정) 양끝 — 미검증 event 간 update 간선 금지 |
| `reaction_to` | **verified event** + 출처가 community — community 는 오직 이 간선으로만 event 에 attach(anchor 금지) |
| `market_signal_for` | **verified entity/event link** — market 신호는 검증된 대상에만 연결(사건 확정 아님) |
| `mentions` | **entity extraction provenance**(어느 source span 에서 추출됐는지) 필수 |
| `caused_by` | **high evidence** + 명시적 `uncertainty` label — 인과는 최고 근거+불확실성 표기 없이는 금지 |

규칙:
- 어떤 edge 도 **검증 없이 생성 0**(GraphRAG/KG 는 검증된 identity·entity provenance 위에서만).
- community reaction 은 사실 근거가 아니라 **반응 레이어**다 — `reaction_to` 외 간선으로 승격 금지.

## 3. Entity candidate provenance

entity 후보는 `source_id` + `span`(추출 위치) + `extraction_method` + `confidence` + `verified(bool)` 를 갖는다.
verified=False entity 로 `same_event`/`caused_by` 간선 생성 금지. entity 정규화(alias)는 KG/공개 전 reviewer/gold
검증 대상.

## 4. Community reaction layer (오염 차단)

- community 관측은 `reaction` storage_class·`reaction_to`(verified event)로만 연결.
- community 를 event **anchor**·**fact source**·**same_event 근거**로 사용 금지.
- 공개 시 community reaction 은 event identity 와 **시각적·구조적으로 분리** 표기(§5).

## 5. Public Intelligence Unit gate (공개 전제조건)

public IU(R7)는 다음을 **모두** 만족하기 전 mock/wireframe only(`no_public_intelligence_unit=True`):

1. **verified evidence**: 모든 주장이 publishable canonical + published_at 로 근거.
2. **source agreement/disagreement** 명시: 단일출처/동의/불일치 상태 노출.
3. **uncertainty** 명시: 미확인 지점을 숨기지 않음.
4. **community reaction 분리**: 사실 근거와 반응 레이어를 분리(혼합 서사 금지).
5. **no raw hallucinated synthesis**: LLM 단독 합성 서사 금지 — evidence-bounded(§LLM contract §4/§5).
6. **raw source ≠ public IU**: raw 수집물을 그대로 공개 IU 로 둔갑 금지(정제·검증·identity 후).

## 6. 이 계약이 잠그는 실패 모드

- "GraphRAG/KG edge 를 검증 없이 생성" → §2
- "RAG 를 raw unverified corpus 에 바로 연결" → §1
- "community 를 event anchor" / "market/catalog/search 를 anchor" → §1/§2/§4
- "raw source 를 public Intelligence Unit 으로 착각" → §5
- "entity 추출 provenance 없이 mentions/same_event" → §2/§3
- "MERGE_GATE 전에 same_event edge" → §2(same_event 행)
