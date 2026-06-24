# RAG / KG / Entity / LLM-routing / Agent-expansion Readiness (정직 평가)

> 작성 2026-06-24 (ADR#39). **목적:** 결정론 Event substrate(events/event_updates/cluster_event_map/event_links/event_cards)가
> downstream RAG·KG·Entity·LLM routing·deep agent 층에 넘길 만큼 익었는지 **숨김 없이** 기록한다.
> 상태값: **BUILT**(실동작) / **PARTIAL**(일부·mock-default·미배선) / **NOT BUILT**(코드 없음) / **PLANNED**(roadmap 설계만).
> ⚠ 이 문서는 "미구축을 미구축이라 적는" 정직성 장치다. 낙관 금지. 근거 file:line 은 ADR#39 감사(Explore) 기준.

## 1. 한 줄 결론
**Event substrate(쓰기/발행/타임라인)는 S1+S2a~e + live-PG 30/30 으로 토대 견고하나, RAG/KG/Agent 층은 대부분 NOT BUILT/PARTIAL 이고 핵심 모델이 mock 기본값**(`EMBEDDING_PROVIDER=mock`·`LLM_PROVIDER=mock`). **지금 RAG/KG 로 넘기면 안 된다** — 먼저 substrate 차단 gate 2개(아래 §4)를 닫아야 한다.

## 2. 12 역량 상태표 (정직)
| # | 역량 | 상태 | 근거 / mock 여부 |
|---|---|---|---|
| 1 | RAG pipeline(grounded answer path) | **NOT BUILT** | dense top-k 검색만(`backend/app/db/milvus.py`); 합성/citation 층 없음 |
| 2 | Embedding + vector DB 실배선 | **PARTIAL** | Milvus 스키마 O, `EMBEDDING_PROVIDER` 기본 **mock**(`config.py`); 실 임베딩=flag flip+키 |
| 3 | Event/Evidence/Source → chunk schema | **NOT BUILT** | title+summary 단일 임베딩, chunking 없음 |
| 4 | citation-grounded answer | **NOT BUILT** | evidence 는 게이트(pass/hold)일 뿐 답변 근거 합성 없음 |
| 5 | Entity extraction | **PARTIAL** | 결정론 baseline(대문자 고유명사 regex, `agents/nodes/baselines.py`); LLM NER·형태소 없음 |
| 6 | Entity canonical/alias/relation | **NOT BUILT** | entities=JSONB list, 정규화·alias·edge 없음 |
| 7 | Event-Entity/Event-Event/Source-Entity edge | **PARTIAL** | `event_links` 스키마 O, 자동 edge 생성 로직 없음 |
| 8 | LLM router 실배선 | **PARTIAL** | `source_supervisor` allowlist·judge 프레임 O, `llm_propose`=테스트 람다, `LLM_PROVIDER` 기본 **mock**; unsafe 제안 audit=TODO |
| 9 | Event→확장수집 plan agent | **NOT BUILT** | `query_generator`=NotImplementedError; event-reactive expansion 없음 |
| 10 | instruction pipeline | **NOT BUILT** | 고정 DAG 만(event_processing_graph) |
| 11 | 주기 auto re-collection scheduler | **NOT BUILT** | Celery beat/cron 없음; passive Redis stream 소비만 |
| 12 | Event substrate 안정성 | **PARTIAL→견고(쓰기/발행)** | events/updates/map/links/cards + read API + **live-PG 30/30**; heat·domains·auto-snapshot·cross-batch identity 는 미완 |

## 3. 소스군 orchestration 상태 (ADR#39 재감사)
| 소스군 | record_type→source_type | 발행 | 상태 | 비고 |
|---|---|---|---|---|
| news/domain(article) | article_candidate→article | publishable | **LIVE VERIFIED** | ADR#29 실 fetch Event·timeline 렌더 입증 |
| official(opendart/sec_edgar/federal_register) | (vendor route) official_record→official | publishable | **PARTIAL** | 실 fetch probe O, 실 cross-source 비뉴스 Event 미관측(R-RealSourceLoopUnproven) |
| **catalog(aladin/tmdb/kofic/kopis/tour/igdb)** | **domain→official_record→official** | **publishable(누수)** | **🔴 LEAK — R-SourceCatalogFidelity** | `_GROUP_TO_RECORD_TYPE` domain→official_record. catalog 메타가 official Event 로 발행 가능(미수정·ADR 필요) |
| search | search_result→search | 차단(gate) | **POLICY PROTECTED** | 직접발행 WITHHELD; URL candidate 만 |
| community(hacker_news 등) | community_signal→community | 차단(gate) | **SIGNAL ONLY** | 직접발행 0·corroborator/held 만; 승격도 parent 연결만 |
| market/numeric/structured | structured_signal→signal | 차단(gate) | **SIGNAL ONLY** | signal-only·투자조언성 Event 금지; 단일 집계 스냅샷=싱글톤 |
| unknown/missing source_type | (미지) | 차단(fail-closed) | **FAIL-CLOSED** | publishable 0→WITHHELD(ADR#35 조용한 우회 차단) |

## 4. RAG/KG 이전 **필수 substrate gate**(닫아야 handoff 가능)
1. **R-CrossBatchEventIdentity**(MEDIUM, open) — 같은 사건이 배치마다 새 Event 로 분열(UNDER-merge). substrate 분열은 RAG/KG/Entity graph 를 그대로 오염. Event identity 층 ADR 선행.
2. **R-SourceCatalogFidelity**(MEDIUM, open) — catalog 메타가 official Event 로 누수. 발행 fidelity 가 깨지면 KG entity/authority 가 catalog 노이즈로 오염. 정책 ADR 선행.
3. (기존) heat/ranking 미산정(events.heat=0), event_cards↔Event 자동연결 부재, 3엔진(PG/Milvus/OpenSearch) 색인 정합 미검증(R-EventModelMigration).

## 5. 미구축 미래층(roadmap 사실 — RISK 아님)
신규 RISK 남발 금지: RAG/KG/agent 미구축은 **launch blocker 가 아니라 미착수 roadmap**이다(현 제품은 event card+timeline 으로 동작). 설계 문서:
- `docs/2_ROADMAP/08_RAG_VECTOR_DB_LAYER.md`(dense 토대 O, hybrid/RRF/rerank 0%)
- `docs/2_ROADMAP/09_KG_RAG_GRAPH_RAG_LAYER.md`(의도적 hold — vector RAG baseline 입증 전 GraphRAG 금지)
- `docs/2_ROADMAP/11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md`(llm_propose 실 provider 미배선)
- `docs/5_REFERENCE/RAG_VECTOR_DESIGN.md`·`LLM_AGENT_DESIGN.md`·`SEARCH_DESIGN.md`

## 6. Go / No-Go
- **No-Go(현재):** RAG/KG/Agent 본격 구현. 이유 = mock-default + substrate 차단 gate 2개 open.
- **Go 조건:** §4 의 R-CrossBatchEventIdentity·R-SourceCatalogFidelity 종결 + 실 embedding 배선(#2) + heat/ranking(#12) → 그 다음 vector RAG baseline(#1~#4) → 입증 후 KG(#5~#7).
