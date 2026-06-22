# 04 — TARGET ARCHITECTURE LAYERS (L0~L14)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 📘 REFERENCE — L0~L14 목표 아키텍처 청사진(진입 지도). 새 방향(ADR#14/#15/#16) 반영.
> │ **구현순위:** #6 (00_ROADMAP_INDEX) · **그룹:** B
> │ **검증 근거:** 코드 산출물 아님(목표/판단 청사진). 토대는 `_CANONICAL/*`(57소스·A→B bridge·Redis/DLQ·11노드 baseline·3엔진·1517테스트).
> │ **잔여(미구현):** L1 Entity/Authority 발견엔진, L2 expansion_router, L8 Event append/timeline/heat, L9 P/G/F 배선, L13 4뷰+광고 인벤토리, L14 트래픽×광고.
> │ **완료정의(DoD):** N/A(설계 문서) — 가리키는 각 레이어의 구현으로 충족.
> │ **권위:** 구현 사실은 `_CANONICAL/*`. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> **방향:** 본 청사진은 ADR#14(LLM 수집경계 P/G/F)·ADR#15(구독→트래픽×광고×커뮤니티)·ADR#16(Event 타임라인 객체) 반영판이다(`docs/_DECISIONS/2026-06.md`). 불변 제약(우회 금지·전문저장 금지·투자조언 금지·rate-limit 준수)은 어느 레이어에서도 유지된다. 착수 임계경로는 `00_ROADMAP_INDEX §4`(Event 토대 S1 먼저).

> 목표 아키텍처를 layer별 책임으로 분리. 각 layer = 현재상태 / 목표 / 구현방향 / 비용 / 위험 / 검증기준. 상세 체크리스트는 16, layer별 심화는 05~13(+ NET-NEW ROADMAP 17·19, 상태 🔲 NOT_DONE, `00_ROADMAP_INDEX` 그룹 D).

---

## 0. 전체 그림

```text
L0  Product thesis / positioning ───────────────── (왜/누구에게)
L1  Source discovery & seed ingestion  ── ingestion/ 57소스 [구현] + Entity/Authority 발견엔진 [중기·미구현→17]
L2  Search expansion (external web)     ── tiered(무료→유료) + budget guard + expansion_router [미구현→06/19]
L3  Policy-safe fetch / body / evidence ── EvidenceGate/policy_probe [구현]
L4  EventQueue / raw_events / Redis      ── A→B 배선 [P0 미배선]
L5  Storage & indexing (PG/OS/vector)    ── 3엔진 [구현, 정합성 갭] + events/event_updates 데이터모델 [미구현→12/19]
L6  RAG retrieval & reranking            ── Milvus top-k [부분], hybrid/rerank [미구현]
L7  KG-RAG / GraphRAG / entity graph     ── [영구보류, <1000엔티티 금지]
L8  Event append / timeline / heat / rank── exact dedup [부분], Event append·timeline·heat·cluster [미구현→12/19]
L9  LLM 수집경계 P/G/F (Plan→Gate→Fetch) ── decide()/allowlist 골격 [부분], P/G/F 배선 [미구현→11/19]
L10 Agent orchestration (LangGraph)      ── 11노드 5R/6M [부분] + Agent Debate 별개 그래프 [미구현→10/19]
L11 Safety / legal / trust / no-bypass   ── 게이트/정책 [구현]
L12 Monitoring / observability / cost    ── monitoring.py [구현], cost/rate 가시화 [부분]
L13 Product surface (4뷰 + 광고 인벤토리)── dashboard [구현], 4뷰·alert·API [미구현→13]
L14 Commercialization (트래픽×광고×커뮤니티)── [전략, ADR#15 — 구독 폐기]
```

데이터 흐름: **L1/L2 → L3 → L4 → L5 → (L6/L7) → L8 → L9/L10 → L13**, 가로질러 L11(안전)·L12(관측)이 모든 layer를 감싼다. L0/L14는 방향을 규정한다. **L9는 단일 게이트가 아니라 P/G/F 3층 경계**(LAYER P 계획=LLM 관여 → LAYER G 게이트=결정론 검문 → LAYER F 페치=결정론 실행, LLM 미관여)다(ADR#14). **L8은 cluster를 1회성 카드로 발행하지 않고 Event 객체에 append**한다(ADR#16, 카드=Event의 현재 단면 snapshot).

> **레이어→심화문서 매핑(1줄):** L1/L2 Entity·Authority·tiered = `17`·`19 §5·§6` · L8 Event append/timeline/heat = `12`(개정)·`19 §1·§2` · L9 P/G/F = `11`(P/G/F 절)·`19 §10` · L2 expansion_router = `06`(tiered)·`19 §6` · L13 4뷰+광고 = `13`(전면개정) · 전 레이어 결정 논거 = `_DECISIONS ADR#14-16`. *17·19는 실재 ROADMAP 파일이나 상태는 🔲 NOT_DONE(NET-NEW, 코드 부재 — `00_ROADMAP_INDEX` 그룹 D). 끊긴 링크 아님, 미구현 청사진 링크임.*

## 1. layer 요약표

| Layer | 현재 | 목표 | 우선순위 | 핵심 위험 | 검증기준 |
|---|---|---|---|---|---|
| **L0** Product thesis | 전략 분산 | event intelligence 포지션 확정 | — | "검색엔진" 착각 | 차별점 3 + 수익경로 2 문서화 |
| **L1** Source discovery | 57소스 deterministic [구현] | discovery↔ingestion 분리 + **Entity/Authority 발견엔진(중기→17)** | P1 | 단발 LIVE를 READY로 과신 | schedulable 소스 capability 100% + Entity Registry PoC |
| **L2** Search expansion | 없음 | **tiered(무료→유료) + per-event/월 budget guard + expansion_router(다중 fallback)** | P2 | 단일 provider 의존, 비용폭발, batch fail-all(R-ExpansionPartialFailure) | event당 예산 guard + fallback chain + 부분실패 격리 |
| **L3** Policy-safe fetch | EvidenceGate/probe [구현] | SSRF allowlist, retention TTL | P1 | SSRF, 전문 저장 | synthetic/local URL 거부, 전문 0 |
| **L4** EventQueue/raw_events | **A→B 미배선** | Redis Stream 실배선 + DLQ | **P0** | mirror가 DB 착시 | ingestion seed 1건 raw_events 도달 |
| **L5** Storage/indexing | 3엔진 [구현] | 정합성(outbox/DLQ), nori, pgvector 검토 | P3 | swallow silent drift | 3엔진 동일 card_id, 미전파 0 |
| **L6** RAG/rerank | Milvus top-k [부분] | hybrid(RRF)→rerank→nori | P3 | keyword-only recall 손실 | nDCG/Recall@k 베이스라인 |
| **L7** KG-RAG | 없음 | 고가치 multi-hop 한정 PoC | P6 | mock 엔티티 위 그래프, 3-5x 비용 | mock 제거 후 진입, ROI 추적 |
| **L8** Event append/timeline | exact dedup [부분] | dedup→cluster→**Event append→timeline→heat→rank**(카드=단면, ADR#16) | P1 | near-dup 범람, false-merge 전파(R-FalseMerge), 카드↔Event 드리프트(R-EventModelMigration) | purity≥0.8, leakage<10%, clique 게이트, 3엔진 card_id 정합 |
| **L9** LLM 수집경계 P/G/F | decide()/allowlist 골격 [부분] | **P(계획·LLM 관여)→G(게이트·결정론)→F(페치·결정론, LLM 미관여)** 3층(ADR#14) + audit trace 의무 | P4 | LLM 비결정/우회 제안, unsafe 침묵폐기(R-LLMCollectBoundary), prompt injection(R-PromptInjection) | allowed 게이트, fallback 100%, 제안·채택·거부 audit 기록 |
| **L10** Orchestration | 11노드 5R/6M [부분] | mock 해제, 0.2.76 유지 | P1 | LLM 만능주의, 비용 | 6 mock 실연결, audit trace |
| **L11** Safety/legal | 게이트/정책 [구현] | SSRF·retention·license 매트릭스 | 상시 | 우회·전문저장·명예훼손 | 우회 0, secret scan PASS |
| **L12** Monitoring | monitoring.py [구현] | cost/rate 실시간 가시화 | P1 | 비용 폭발, 침묵 실패 | cost+rate+health 3축 노출 |
| **L13** Product surface | dashboard [구현] | **4뷰(스냅샷카드/타임라인/다분야그래프/논쟁스레드) + 광고 인벤토리**(ADR#15) | P7 | mock UI 노출, 신뢰 훼손, 비전문비율 미게이트 | evidence 구조화, 4뷰 동작, 페이지 비전문비율 게이트 |
| **L14** Commercialization | 전략 | **트래픽×광고×커뮤니티 성장루프**(구독 폐기, ADR#15) | — | 광고 단일점·콜드스타트·brand-safety(R-AdModelFragility) | Monetizable Dwell + 광고주 갱신율 + 트래픽 채널 1 검증 |

## 2. layer 간 핵심 계약(인터페이스) — 새 경계

> 6계약을 ADR#14/#16 새 경계로 교체. **events/event_updates 데이터모델은 L5(저장)에 위치**하고 L8(Event append)이 쓰기 주체, L13(4뷰)이 읽기 주체다. DDL은 `5_REFERENCE/EVENT_SCHEMA.md`.

- **L1/L2 → L3 (P/G/F 경유)**: 모든 fetch는 LAYER G(게이트) → LAYER F(페치) 단일 경로. LAYER P(LLM 계획: triage·query expansion·source routing)의 제안도 `_ALLOWED_BY_LAYER` + `_UNSAFE_STRATEGIES` 게이트를 반드시 통과. 우회 코드 우발 실행 차단(ADR#14).
- **L2 → L3 (expansion budget)**: expansion_router는 event candidate 1건당 tiered 호출(무료→유료) + per-event/월 budget guard 안에서만 검색. batch 부분실패는 격리(전체 중단 금지, R-ExpansionPartialFailure).
- **L3 → L4**: `bridge_to_raw_events.to_raw_event_create`(content_hash dedup, url NOT NULL, preview_only raw_text=""). 전문 저장 금지 불변.
- **L4 → L5 (Event 데이터모델)**: raw_events PG 적재 후 upsert_card → Milvus/OpenSearch 전파(현재 swallow → outbox 권장). **신규: `events`(canonical 주제)·`event_updates`(append-only 변화분)·`cluster_event_map`(라우팅)·`event_links` 테이블 추가**(L5 거주, alembic 0004 additive). `event_cards.event_id` nullable FK로 스냅샷↔주제 연결.
- **L8 → L5/L13 (Event append, 카드=단면)**: `cross_source_dedup` 출력을 카드 dedup이 아니라 **Event append로 라우팅**(cluster_event_map 경유). 2번째 보도 → 새 카드 아닌 기존 Event에 update append. event_cards는 **Event의 최신 스냅샷 뷰**(1회성 산출물 아님, ADR#16). heat = 시계열 활성도(half-life 감쇠). confidence = corroboration+diversity 매핑.
- **L11**(가로): EvidenceGate가 synthetic/dead/local URL을 evidence 자격에서 차단(승격 게이트). fetch 진입점에도 동일 룰 복제 필요.
- **L9/L10**(가로, P/G/F·Debate): LLM 제안은 `allowed-strategy` 집합 안에서만 채택, `UNSAFE_STRATEGIES`는 영구 차단, 모든 제안·채택·거부는 audit trace 기록(현재 침묵폐기는 R-LLMCollectBoundary 추적). 외부 콘텐츠는 untrusted로 격리. Agent Debate는 별개 신규 그래프이며 투자조언 금지·prompt injection 격리(R-AgentDebateSafety).

## 3. 설계 원칙 — 새 경계

1. **LLM-advised, deterministic-controlled (P/G/F)** — LLM은 무엇을·어디서를 *계획*(LAYER P)하고, 결정론 엔진은 어떻게(준수하며)를 *실행*(LAYER F)한다. LLM은 크롤러가 아니라 수집의 두뇌(planner)다. 게이트(LAYER G)가 비결정성을 검문하므로 우회·rate 위반은 어느 층에서도 금지(ADR#14). "수집 LLM 완전배제" 레거시 명제는 폐기됨.
2. **evidence 중심 저장** — 전문 저장 금지, URL+summary+metadata. 노출하는 것은 전문이 아니라 요약+증거링크+UGC+시계열 시각화(파생 콘텐츠 → 광고 면적, ADR#15).
3. **provider-agnostic** — 검색·임베딩·rerank·LLM 모두 추상화 뒤 교체 가능. 단일 provider 락인 금지. tiered expansion은 budget guard로 비용 상한.
4. **정합성보다 가용성 격리, 그러나 가시화** — Milvus/OpenSearch 인덱싱 swallow는 best-effort지만 실패를 메트릭으로 노출. 단 Event 이중쓰기(event_cards↔events) 정합성은 불변식 테스트로 강제(R-EventModelMigration).
5. **Event가 단위, 카드는 단면** — dedup(같은 글)·cluster(같은 사건)·**Event(시계열로 진화하는 주제)**는 다른 layer. cross-source 보도는 제거 대상이 아니라 Event에 append되는 corroboration 신뢰 신호. 카드는 Event의 현재 snapshot(ADR#16).
6. **트래픽×광고 정당성을 측정 가능 정책으로** — 페이지 비전문비율 게이트·신뢰 트래픽 등급제로 광고 정당성을 강제. 구독 폐기, per-seat 가격경쟁 안 함(ADR#15).
7. **모든 layer에 검증기준** — "동작하게"가 아니라 측정 가능한 acceptance.

## 4. 착수 순서 — Event 토대 먼저 (scope 고정)

> **임계경로 단일 출처는 `00_ROADMAP_INDEX §4`**(S1~S11 위상정렬). 본 절은 그 포인터 + 04 레이어 관점의 요약이다.

- **선행 필수 (S1, 최우선·임계경로 합류점):** L5의 **Event/Update 타임라인 토대**(`events`/`event_updates`/`cluster_event_map`/`event_links` + `event_cards.event_id` nullable FK, alembic 0004). Event 토대를 먼저 고정하지 않으면 "걸음1(카드 AI 품질)"이 **곧 폐기될 1회성 카드 스키마 위에** 쌓인다(코딩 전 판단 원칙).
- **그 다음 (저렴순):** S5 LLM Expansion Router(L9 게이트 존재라 가장 저렴) → S2 Event Resolution + S3 domains/tags 2층(L8) → S4 Entity Registry(L1) → S6 Source Routing 배선(L9 P/G/F).
- **그 이후 (Event 토대 의존):** S8 Evidence Graph → S9 Agent Debate(L13 광고 연결) → S10 Authority Discovery(L1) → S11 SLM Body Fallback.

**지금 하지 않는 것:** L7(GraphRAG, 영구보류 <1000엔티티 금지), L2 유료 routine 호출, **상용화(L13/13)·검색고도화(L6/08)는 Event 토대(S1)+실데이터 이후** — 그 전엔 영업/검색이 모래성이다(적대적 비판). 모든 단계 **비파괴·1517 green·우회 0·투자조언 0·전문저장 0**.
