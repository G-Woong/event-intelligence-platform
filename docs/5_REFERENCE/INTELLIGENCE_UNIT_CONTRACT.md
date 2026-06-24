# Intelligence Unit Contract (제품 출력 계약)

> **단일 출처**: 최종 public 단위가 무엇이고, 각 source 가 거기서 어떤 역할을 하며, Event substrate 가
> 미래 Agent/RAG/KG/LLM 층에 무엇을 제공해야 하는지를 정의한다. 코드(`event_resolver`/`event_ingest_pipeline`/
> `event_resolution_pipeline`/`event_timeline_service`)가 강제하는 계약의 서술 단일 출처.
> 신규: 2026-06-24 (ADR#41). 관련: `EVENT_SCHEMA.md`·`RAG_KG_AGENT_READINESS.md`·`_CANONICAL/02_CURRENT_ARCHITECTURE.md`.

## 0. 한 줄 원칙

**raw source ≠ public product.** 이 프로젝트는 뉴스 본문 하나·카탈로그 메타 하나·시장 스냅샷 하나·커뮤니티 글
하나를 그대로 웹에 내보내는 시스템이 **아니다**. 여러 소스의 관측값을 **에이전트가 사건 단위로 묶고 정제한
하나의 고품질 Intelligence Unit**을 제공한다.

## 1. 계층 (substrate → public)

```
source record (관측값, raw)            ← 직접 노출 금지
  → cross_source_dedup (cluster)        ← 결정론 묶음
  → event_resolver / event_timeline     ← 결정론 substrate(Event/Update/links/identity)
  → [미래] Agent/RAG/KG/LLM routing      ← 정제(요약·반응·신호·entity·confidence)
  → Intelligence Unit (public)          ← 최종 노출 단위
```

- **source record 는 observation 이다** — 그 자체로 public 아님.
- **Event 는 substrate 다** — 관측의 결정론 묶음. LLM 이 덮어쓰지 않는다(전 경로 결정론 유지).
- **Intelligence Unit 은 public 단위다** — Agent/RAG/KG/LLM 이 substrate 위에 정제. **현재 미구현**(NOT BUILT).

## 2. Intelligence Unit 구성 (미래 public 단위가 포함해야 할 것)

| 구성요소 | substrate 출처(현재) | 정제 주체(미래) |
|---|---|---|
| 사건 요약 | events.canonical_title + event_updates.delta_summary | LLM summarizer |
| 핵심 변화 / 시간축 업데이트 | event_updates(append-only, observed_at) | change detection + LLM |
| 관련 공식 근거 | evidence(source_type=official/article, url) | evidence graph |
| 보도 흐름 | event_updates evidence(article) | RAG |
| 커뮤니티 반응 | (held/corroborator lane; 직접 발행 안 함) | reaction summarizer |
| 시장/수치 신호 | (signal lane; 직접 발행 안 함) | signal normalizer |
| catalog/entity context | catalog_metadata(KG enrichment lane) | entity/KG |
| 동일성 후보 | event_links(possible, semantic_cross_batch_candidate) | semantic adjudicator |
| confidence / uncertainty | delta_summary 헤지·clique/약신호 | LLM confidence revision |
| evidence citations | evidence(url, allowlist) | citation-grounded answer |

## 3. Source Role Contract (코드가 강제)

각 source 는 **직접 발행 단위가 아니라** 다음 역할로만 substrate 에 들어간다. publishability 는
`record_type→source_type` 매핑 + publish gate(`event_resolver`)로 강제(테스트로 잠금).

| source 종류 | source_type | publishable | 역할 |
|---|---|---|---|
| official/news | official / article | ✅ publishable | high-authority evidence(단 identity·false-merge 방어 통과) |
| community | community | ❌ | **반응·정서·확산·논쟁·현장감 layer**(직접 사건 발행 금지·corroborator/held) |
| market/numeric | signal | ❌ | **signal**(사건 전후 변화·이상신호·관련도·confidence — 가격 숫자 그대로 아님) |
| catalog | catalog | ❌ | **entity/KG enrichment**(인물·작품·기업·기관·장소 metadata·disambiguation — 사건 아님) |
| search | search | ❌ | URL 후보(expansion candidate; 증거 승격 금지) |
| unknown/missing | — | ❌ (fail-closed) | 발행 안전하지 않음 → WITHHELD |

**금지(코드/문서 공통):** community 글을 사건으로 발행 · catalog 메타를 official Event 로 발행 ·
market 스냅샷을 Event 로 발행 · source_group 하나로 publishability 추정 · unknown 우회 발행.

## 4. Entity / Semantic Identity Hook (future contract, 현재 empty)

미래 NER/KG/LLM adjudicator 가 붙을 자리를 **DB 컬럼 남발 없이** 계약으로 연다:

- **entity hook**: catalog_metadata 와 evidence 가 인물/기관/작품 entity 로 정규화될 입력(현재 entities=JSONB
  baseline, 정규화·alias·edge 미구현 — NOT BUILT).
- **semantic identity status**: cross-batch 동일성은 4단계 — ① 확정 anchor 병합(`event_identity_map`, ADR#40)
  ② 결정론 fingerprint 후보 LINK(`event_identity_candidate`→`event_links possible`, ADR#41, **병합 아님**)
  ③ deterministic **shadow 판정**(`event_identity_adjudication`: likely_same/ambiguous/likely_different/insufficient,
  ADR#42, **병합 아님·자동 병합 0**) ④ semantic **실 병합**(embedding/LLM/KG adjudicator, **미구현** —
  R-SemanticIdentityAdjudicator·R-IdentityEvalDataset). IU 합성기는 ③의 status 를 신뢰도 신호로 받되 병합은 ④ 전까지 금지.
- **possible-link substrate**: `event_links(possible, reason='semantic_cross_batch_candidate')` 는 ③ shadow
  adjudicator 가 소비(ADR#42)하고, 미래 ④ adjudicator 가 confirmed/rejected/merged 로 재판정할 **가역 입력**이다.
  shadow status(③)도 현재 소비처 0(report 휘발성·정직) — 실 병합·labeled 평가셋 전까지 "중복 해결" 아님.

## 5. 정직 경계 (over-claim 방지)

- cross-batch 후보 LINK 는 **중복 Event count 를 줄이지 않는다**(실 병합 아님).
- LLM/RAG/KG/Entity/Agent 는 **미구축**(mock-default). Intelligence Unit 은 아직 substrate 단계.
- 이 문서는 **계약**이지 구현 증거가 아니다 — 구현 상태는 `RAG_KG_AGENT_READINESS.md` 가 단일 출처.
