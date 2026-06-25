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
| 11 | 주기 auto re-collection scheduler | **NOT BUILT** | 주기 수집 auto-trigger 미배선(Celery 설치만·task/beat 0). 단 `workers/tools/run_recovery_scheduler`(`--interval-sec`/`--once`·docker `recovery-scheduler`)·Redis stream consumer 가동 — **주기-드라이버 idiom 존재**(ADR#50 backfill `--once` 재사용·ADR#51 `run_semantic_backfill_scheduler.py`[backfill 주기·preflight gated·dry-run default]·**ADR#52 docker `semantic-backfill-scheduler`**[profile-gated 기본 미기동·backend 이미지·entrypoint override·**미가동**]·**ADR#53 docker build/up dry-run 실측**[실행성 입증·3경로 exit 2/1/0·ingestion COPY 버그 수정·**여전히 미가동**]·운영 DB migration 후 게이트) |
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
1. **R-CrossBatchEventIdentity**(MEDIUM, **부분종결 진전** ADR#40+#41) — 같은 사건이 배치마다 분열(UNDER-merge). **닫힌 범위(병합):** deterministic shared-anchor 층(`event_identity_map`: 동일 canonical_url/official_id 재등장→기존 Event APPEND, live-PG 검증, ADR#40). **닫힌 범위(후보 substrate):** 공유 anchor 없는 같은 token-set+같은 날 publishable 후보를 `event_identity_candidate`→`event_links(possible)` 로 **표면화**(ADR#41, live-PG 검증). **⚠ 미해결:** ADR#41 은 **LINK 만 — 중복 Event count 미감소**(실 병합 아님). 패러프레이즈/다국어/엔티티 동일성·실 병합은 **R-SemanticIdentityAdjudicator**(신규, 미구현) → **여전히 RAG/KG 이전 gate**.
2. **R-SemanticIdentityAdjudicator**(MEDIUM, **OPEN·부분 진전** ADR#41+#42) — possible-link 후보를 실제 병합/기각해 중복 Event 를 줄이는 adjudicator. **ADR#42 부분 진전**: deterministic **shadow** adjudicator(`event_identity_adjudication`[0009])가 LINK 를 소비해 status(likely_same/ambiguous/likely_different/insufficient) 산출(소비처 0 부분 해소·자동 병합 0·API 미노출). **미해소**: 실 병합(count 감소)·embedding/LLM/KG·한국어 캘리브레이션·labeled 평가셋. **이게 닫혀야 cross-batch 동일성이 진짜 해결**.
3. **R-IdentityEvalDataset**(MEDIUM, **OPEN·harness 부분 진전** ADR#42+#43+#44) — adjudication status 가 self-labeled → 자기 precision 측정 불가. **ADR#43**: eval harness(`identity_eval_dataset.py`·fixtures·`evaluate_adjudicator`)·현재 adjudicator precision **0.57**·FPR 0.2·KO 0.67. **ADR#44**: gold loader/evaluator(`identity_human_labeling.py`)·fixture vs gold 분리·readiness 산출(sample gold precision 0.6·KO 0.5·merge gate 미달). **미해소**: live-derived+human-labeled gold set·규모·한국어 실 캘리브레이션·MERGE_GATE 런타임 배선·표본 floor 재유도. **실 병합 허용 판단의 선결**.
4. **R-IdentityHumanLabeling**(MEDIUM, **OPEN·protocol 부분진전** ADR#43+#44+#45+#46) — 워크시트→gold 승격 + reviewer agreement protocol + labeling packet. **ADR#44**: GoldPair provenance·self-label 금지·gold-only metric·readiness. **ADR#45**: `resolve_gold_from_reviewers`(다중 reviewer 합의=gold·**conflict 자동 gold 금지**·LLM adjudicator 차단)·sampling bucket·통계적 표본 floor 추정(189/381). **ADR#46**: `build_labeling_packet`(live 후보→reviewer ≥2 배정·**predicted_status 차폐**)·`adjudication_queue_from_resolved`(conflict→사람 lead). **미해소**: 실 human-reviewed gold 0·reviewer agreement 실측 0(→R-ReviewerAgreement)·sampling 대표성(→R-GoldSamplingBias)·SLA·주기 루프. **protocol/packet 코드 ≠ 실 gold/agreement** — 완전종결 금지.
   - **R-ReviewerAgreement**(MEDIUM, **OPEN·packet scaffold 부분진전** ADR#45+#46+#47) — 다중 reviewer 합의 실측·kappa·운영 절차 0(protocol+배정 packet 코드만; ADR#47 이 배정 packet 을 live-PG 백로그에 적용·실 합의 데이터 0).
   - **R-GoldSamplingBias**(MEDIUM, **OPEN·packet sampling 부분진전** ADR#45+#46+#47) — gold sampling 대표성·hard-negative/KO oversampling 실데이터 0(bucket+packet 코드만; ADR#47 옵션 D `deterministic_bucket_hash_cap`[정렬 편향 완화·재현]·live backlog/exclusion report 추가·단 실 충원/대표성 0·selection 효과 over-cap 한정[현 nil]).
   - **R-LiveIdentityBacklog**(MEDIUM, **OPEN·신규 ADR#47·부분진전 ADR#48+#49+#50+#51+#52**) — live labeling packet 이 읽을 실 운영 백로그 0(운영 DB `event_intel` 미마이그레이션 + 단계 ③ adjudication live 루프 미배선). **ADR#48**: 단계 ③ 운영 배선(`ingest_records_to_events(adjudicate_semantic=)`·flag off-by-default·배치 후 자동 `adjudicate_semantic_links`→백로그 자동 누적·자동 병합 0·멱등) + migration readiness probe(운영 0003 vs head 0009 **6 뒤·non-destructive**). **ADR#49(gap②③ 해소)**: incremental(`only_unadjudicated=,limit=`·비싼 work 미판정 link 한정·O(N) 완화·ambiguity 정확성 회귀 가드)·no-cluster backfill(`if not clusters` 제거)·`backfill_semantic_adjudications.py`(dry-run·bounded)·운영 DB 배포 runbook(`15_ROADMAP §`). **ADR#50(gap③④ 추가 진전)**: keyset(`after_link_id` cursor·`_semantic_links` 가 `WHERE id>cursor·NOT IN·LIMIT` 를 SQL 로 push→bounded run 의 cheap O(전체) 적재 완화·ambiguity 는 page candidate 한정 GROUP BY 로 link별 status 동작 보존; **cursor=UUIDv4 byte 순서·시간순 아님·진행 보장은 only_unadjudicated**·전수 경로는 `full_scan` 표면화)·backfill 운영 CLI(`--limit/--after-link-id/--dry-run`·safe-target·next_cursor/full_scan/idempotent_persist·lock 과대주장 0)·`build_operational_deploy_checklist`(0003→head 명령·backup_required·executed=False)·readiness read-only CLI·주기 가동은 기존 `run_recovery_scheduler --once` 관용구 **재사용 가능(설계·미배선)**. live-PG exclusion 1→0·Event 불변·keyset/동시성 멱등 검증. **ADR#51(gap④ scheduler-ready+cursor)**: preflight gate(`backfill_preflight`/`run_backfill_with_preflight`·ready_for_stage3 hard gate[0003 dry-run 포함 차단·NOT IN 쿼리 크래시 방지]+flag persist gate)·deterministic exit code(`decide_exit_code` 0/1/2/3)·`created_at` 시간순 cursor(`cursor_mode='created_at'`·`or_/and_` 컬럼 비교[행값 tuple_ uuid>varchar 교체·동치]·**배치 간만 정확·intra-txn tie→id·인덱스 없음**)·scheduler 스크립트(`workers/tools/run_semantic_backfill_scheduler.py`·recovery-scheduler 관용구·gated·**dry-run default·docker 미배선·미가동**); live-PG created_at 시간순/동일 created_at tie-break/0003 테이블 DROP block/preflight gate; adversarial **기술계약 VALID**. **ADR#52(gap② docker scaffold)**: scheduler 가 compose `semantic-backfill-scheduler` 로 배선 — **`profiles:["backfill"]` 기본 미기동·dry-run default(command --persist 부재)·preflight gated·단일 instance(replicas 미설정·restart "no")**·backend 이미지 재사용(worker 이미지 services/tools/models 미COPY)·entrypoint override; 옵션 C(created_at index)·D(advisory lock) 근거 DEFER(backlog 0·prod 0003·test churn 회피·DDL/single-instance runbook 문서화)·코드 변경 0(compose+일관성 테스트 5)·scheduler --help 명령 검증. **미해소**: 운영 DB 0009 배포(배포 행위·미적용)·실 fetch·**실제 profile 활성+--persist docker 가동**(docker scaffold 됨·실가동 0[profile 비활성·운영 DB 0003·flag off]·docker build/up 미검증[정적 일관성 테스트만])·대형 백로그 잔여 시 cheap scan 은 keyset 으로 완화되나 전수 report 경로는 여전히 full(`full_scan` 플래그로 표면화)·created_at index/advisory lock DEFER. **ADR#53(gap② docker 실행성 실측)**: 옵션 A 실행 — `docker compose --profile backfill build` 성공·`run --once` 3경로(DB down→graceful exit 2·미마이그레이션→`BLOCKED readiness` exit 1·dev DB head→`dry_run=True event_count 0->0 auto_merge=False` exit 0)·profile 격리 config 실증. **🔴 정적 검증이 못 잡은 런타임 버그 발견·수정**: backend 이미지 `ingestion/` 미COPY→adjudicator 전이 import `ModuleNotFoundError`→`COPY ingestion/`+회귀 테스트 2. **live-PG 91 passed 재실행**(ADR#52 미실행). 정직: run#3 0->0 은 빈 dev DB(read-only 입증=코드+live-PG)·live-PG 91=DB orchestration(scheduler 주기 가동 아님)·**scheduler 실가동 0**·production 백로그 0. **배선(능력)·docker 실행성(검증) ≠ production 가동(actuality)** — handoff 차단 gate 유지. 경계: 운영 DB 배포=R-RealSourceLoopUnproven·단계 ③ 실 병합=R-SemanticIdentityAdjudicator 와 교차 추적(중복 등재 아님).
5. **R-SourceCatalogFidelity**(**CLOSED** ADR#40) — catalog(6종)→catalog_metadata 비-publishable override 로 official Event 누수 차단(fail-closed·live-PG 0 events). KG enrichment 역할은 catalog source_type 라벨로 보존. ✅ handoff gate 통과.
6. (기존) heat/ranking 미산정(events.heat=0), event_cards↔Event 자동연결 부재, 3엔진(PG/Milvus/OpenSearch) 색인 정합 미검증(R-EventModelMigration).

## 4b. 제품 출력 계약 — raw source ≠ public product (substrate→intelligence unit)
이 제품은 **뉴스 본문 하나를 그대로 보여주는 웹이 아니다.** 모든 소스(article/catalog/market/community/official/search)는 최종적으로 다음 중 하나로 정제된다:
- **Event substrate 의 근거**(publishable: official/article → Event CREATE/APPEND 근거) · **signal**(market/numeric → 비발행 지표) · **catalog/entity enrichment**(catalog_metadata → 비발행·KG/entity 보강 후보, ADR#40) · **held/review evidence**(약신호 corroborator → possible link) · **expansion seed**(search → URL 후보) · **public intelligence unit 의 구성요소**.
규칙: **raw article/catalog/market/community 를 그대로 public 으로 내보내지 않는다.** public 출력 단위는 사건 단위 Event(향후 curated Intelligence Unit). source-type publish gate(ADR#33/#35)+catalog fidelity(ADR#40)+cross-batch identity(ADR#40 병합·ADR#41 후보)+held 정책(ADR#38)이 이 계약을 코드로 강제한다. Agent/RAG/KG 는 이 substrate **위에서** 관련 source 확장수집·entity 연결·반응/영향/시간흐름 정리·citation 유지로 intelligence unit 을 생성한다(현재 미구축 — §2/§5). **계약 단일 출처: `INTELLIGENCE_UNIT_CONTRACT.md`**(IU 구성·source role·entity/semantic identity hook).

## 5. 미구축 미래층(roadmap 사실 — RISK 아님)
신규 RISK 남발 금지: RAG/KG/agent 미구축은 **launch blocker 가 아니라 미착수 roadmap**이다(현 제품은 event card+timeline 으로 동작). 설계 문서:
- `docs/2_ROADMAP/08_RAG_VECTOR_DB_LAYER.md`(dense 토대 O, hybrid/RRF/rerank 0%)
- `docs/2_ROADMAP/09_KG_RAG_GRAPH_RAG_LAYER.md`(의도적 hold — vector RAG baseline 입증 전 GraphRAG 금지)
- `docs/2_ROADMAP/11_LLM_SOURCE_SUPERVISOR_AND_JUDGE_LAYER.md`(llm_propose 실 provider 미배선)
- `docs/5_REFERENCE/RAG_VECTOR_DESIGN.md`·`LLM_AGENT_DESIGN.md`·`SEARCH_DESIGN.md`

## 6. Go / No-Go
- **No-Go(현재):** RAG/KG/Agent 본격 구현. 이유 = mock-default + substrate 차단 gate 2개 open.
- **Go 조건:** §4 의 R-CrossBatchEventIdentity·R-SourceCatalogFidelity 종결 + 실 embedding 배선(#2) + heat/ranking(#12) → 그 다음 vector RAG baseline(#1~#4) → 입증 후 KG(#5~#7).
