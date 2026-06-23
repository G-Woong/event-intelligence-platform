# 15 — IMPLEMENTATION ROADMAP (Phase 0~10 + Event 토대 + Agent Debate)

> ┌─ 진행상황 식별 (STATUS STAMP) ──────────────────────────
> │ **상태:** 🟡 PARTIAL — **Phase 0 DONE / Phase 1–3 PARTIAL DONE / Phase 4–10 NOT_DONE.** **Event 토대(S1) + Event Resolution(S2-core a~c + S2d CRUD 영속 + S2e 통합 파이프라인 + live-PG 검증) 구현 완료**(alembic 0004/0005/**0006** + ORM/Pydantic + event_resolver + event_timeline_service + event_resolution_pipeline + 통합 E2E + **✅ live-PG E2E 14**(0001~0006 실 Postgres·2-세션 동시성·FK RESTRICT) + ADR#19/#20/#21, 2026-06-22; live wiring·heat 잔여). Agent Debate Phase는 코드 0(설계).
> │ **구현순위:** #4 (00_ROADMAP_INDEX) · **그룹:** A
> │ **검증 근거:** Phase1(`ingestion/integration/` BackendApiRawEventsWriter, 라이브 e2e 5타입)·Phase2(`event_queue.py` `_redis_*`, `workers/queue/dlq.py`)·Phase3(`evidence_check`·`publish_or_hold` fail-closed, `agents/nodes/baselines.py`)는 `_CANONICAL/01·04·09`가 권위. Phase4–10·S1·Agent Debate는 grep 0(미배선).
> │ **잔여(미구현):** **S1 토대 + S2-core(a~c) + S2d CRUD 영속 + S2e 통합 파이프라인 ✅ 구현**(events/event_updates/event_cards.event_id+0004; cluster_event_map/event_links+0005; event_resolver/event_timeline_service/event_resolution_pipeline + 통합 로직 E2E, 2026-06-22); **S2 잔여 = live-PG 통합 E2E·heat 4신호(S2.5)·merge_score entity/domain(S4)**, Phase4(tiered+budget+gate+ChangeDetection), Phase6(P/G/F+unsafe gate+audit+유형→role), Phase8(EvidenceNode), Phase9(트래픽KPI+광고4종+커뮤니티), Agent Debate Phase.
> │ **완료정의(DoD):** 각 Phase Acceptance 충족 + 전단계 1517 green 유지 + 우회 0·전문저장 0·투자조언 0.
> │ **권위:** 구현 사실은 `_CANONICAL/*`(본 문서보다 최신). 결정 = `_DECISIONS/2026-06.md` ADR#14/#15/#16. 본 문서는 ROADMAP(미래계획).
> └────────────────────────────────────────────────────────

> 원칙: 토대(배선·dedup·mock 해제)를 먼저 닫고, 고급 layer(검색확장·rerank·GraphRAG)는 그 위에 얹는다. 순서 역전 금지(적대적 비판). 각 Phase는 측정 가능한 acceptance를 가진다. **새 방향(ADR#16):** 카드 dedup 위에 **Event/Update 타임라인 토대(S1)**가 **임계경로 최상위**로 들어온다 — 카드 알맹이 AI 품질(Phase3 잔여)을 올리기 전에 Event 형태를 고정하지 않으면 곧 폐기될 1회성 스키마 위에 쌓인다(00_ROADMAP_INDEX §4).

> 📌 **로드맵 문서(ABSORB, 10 Group E E16)**: P0(ingestion→raw_events 배선)은 **PARTIAL DONE**(ap_news 라이브 E2E; canonical `04 T-IngA`·`01`). 아래 Phase의 "DONE 여부"는 `docs/_CANONICAL/04·09`가 권위(본 문서보다 최신). Phase 의존 순서는 `04` 상단 + 00_ROADMAP_INDEX §4 임계경로(S1~S11)에 흡수됨.

---

## P0/P1 우선순위 요약 (Phase 1–3 PARTIAL DONE; 새 방향 반영)

```text
[PARTIAL] P0  ingestion 57소스 엔진 → 실 raw_events Postgres 배선 (mirror→DB; ap_news 라이브 E2E)
[PARTIAL] P1  Redis Stream/DLQ/retry/monitoring 실배선 + mock 노드 결정론분 baseline화
[PARTIAL] P3  published 게이트 fail-closed (evidence_check·publish_or_hold) — dedup/clustering 잔여
[PARTIAL ] S1  ★Event/Update 타임라인 토대★ (구현 2026-06-22: alembic 0004+ORM+회귀; +S2 Resolution a~c·S2d CRUD·S2e 통합 파이프라인, live-PG E2E 잔여, ADR#16/#18/#19/#20)
[NOT_DONE] P4  Search API expansion layer (tiered 무료→유료 + per-event/월 budget + ChangeDetection)
[NOT_DONE] P5  hybrid search + reranker + nori (indexing)
[NOT_DONE] P6  LLM SourceSupervisor 실 provider 연결 (P/G/F + unsafe gate + audit + 사건유형→role)
[NOT_DONE] P7  Event clustering/timeline/ranking 완성 (heat + FSD)
[NOT_DONE] P8  KG-RAG/GraphRAG (조건부, <1000 엔티티 금지) + EvidenceNode
[NOT_DONE] P9  ★수익화 전환★ 구독 폐기 → 트래픽 KPI + 광고 4종 + 커뮤니티 루프 (ADR#15)
[NOT_DONE] PD  Agent Debate Phase (페르소나 논쟁 + 발화 게이트 fail-closed, S9)
[NOT_DONE] P10 Enterprise 보안/컴플라이언스 (RBAC·SSRF allowlist·TTL·PII·라이선스)
```

> **정직 주의:** 위 P0~P3 PARTIAL은 토대(배선·큐·게이트·baseline)만 실구현이고 DoD(잔여 0·risk 0) 미달이다. 어떤 Phase도 ✅ DONE(risk 0)에 도달하지 않았다 — 권위 = `_CANONICAL/*`, 00_ROADMAP_INDEX §1.

---

## Phase 0 — Canonical docs & architecture freeze
- Goal: 현재 상태/목표 아키텍처 동결. **(완료)** `_CANONICAL/` 11 + 본 ideation 세트.
- Acceptance: 본 문서 세트 커밋, P0 명시. Do-not-do: 코드 변경.

## Phase 1 — ingestion → raw_events 실배선 (P0)  — **PARTIAL DONE 2026-06-18**
- Goal: ingestion seed가 실 raw_events PG에 적재.
- DONE: `ingestion/integration/`(BackendApiRawEventsWriter = bridge db_writer, backend POST 경유 PG+Redis).
  `run_production_orchestration --raw-events-sink backend` 진입점. 라이브 e2e 5 record_type green
  (PG→Redis→worker→LangGraph→event_card). 멱등 collapse. community hold 봉인. 신규 테스트 37 PASS.
- 남은 부분: ① production-validation 라이브 외부 probe→backend 1회(미실행), ② 기본 sink backend 전환,
  ③ 카드 콘텐츠 mock(Phase 3 의존), ④ DLQ/PEL/auto-requeue(신규 P0 운영, 04 T-Ops-DLQ).
- Risks: mock 카드 콘텐츠 사용자 노출(05 R-MockCard), 라이브 수집 미검증. Do-not-do: 소스 추가, 우회.

## Phase 2 — Redis stream / worker / DLQ / monitoring  — **PARTIAL DONE 2026-06-18**
- Goal: A EventQueue Redis 배선 + DLQ/retry/quota + cost/rate 가시화.
- DONE: `event_queue.py` `_redis_*`(Stream+group+PEL ack). **DLQ 부품**: `workers/queue/dlq.py`
  (route_failure=재시도/DLQ, reap_pending=XAUTOCLAIM PEL 회수), consumer 실패시 DLQ 라우팅(silent leak 제거),
  `run_dlq_reaper` CLI, `reconciler_service.requeue_failed_xadd`(xadd_failed 자동 requeue, poison 한도).
- 남음: 자동 주기 트리거(Celery beat/cron), DLQ depth 모니터링/알림, cost/rate 대시보드(04 T-Ops-DLQ 잔여).
- Acceptance: enqueue→consume→ack, PEL→DLQ 회수, cost+rate+health 3축 노출. Complexity: 중상.

## Phase 3 — mock 노드 해제 + dedup → **Event append** (clustering)  — **published 게이트 PARTIAL DONE 2026-06-18**
- Goal: LangGraph mock 중 결정론 가능분(entity_linking=NER, evidence_check=URL/출처 검증) 실구현 + cross-source dedup/cluster.
- DONE(노출 차단): `evidence_check` 실 source URL 채택(`evidence_rules` 구조검증), `publish_or_hold` 근거+본문+
  fact_check 게이트(fail-closed), 공개 API published-only. → mock/근거없는 카드 published 차단(라이브 proof).
- 남음: evidence_check **도달성(HTTP)** 검증, entity_linking=NER, sector_mapping 분류기, impact_analysis 실구현,
  MinHash LSH, 임베딩 HDBSCAN, prompt injection 방어 layer.
- **방향 전환(ADR#16):** `cross_source_dedup` 출력을 **카드 dedup이 아니라 Event append로 라우팅**한다(아래 Event 토대 Phase 의존). 2번째 보도 → 새 카드 아님, 기존 Event에 Update append. **R-FalseMerge:** Union-Find transitive 오염이 영속 Event로 전파되지 않도록 **clique 게이트** 필수(약신호 edge가 끌어온 멤버 자동승격 금지).
- Acceptance: end-to-end 카드 1건 **실데이터 콘텐츠** 생성(현재는 배관+노출게이트만, 알맹이 mock), cluster purity≥0.8, leakage<10%, **transitive-only 클러스터 자동승격 0**. Complexity: 상.

## Phase Event 토대 (S1) — **Event/Update 타임라인 토대 [임계경로 최우선·토대 PARTIAL DONE 2026-06-22]** (ADR#16)
- Goal: 사건을 1회성 카드 → **진화하는 Event 타임라인 객체**로. 카드 = Event의 최신 스냅샷 뷰로 재정의(비파괴).
- **구현 현황(2026-06-22):** S1 토대 ✅ — alembic 0004 + EventORM/EventUpdateORM + Pydantic + is_snapshot_bidirectional + 회귀 17. **S2-core(a~c) ✅** — alembic 0005(cluster_event_map/event_links) + cross_source_dedup clique 게이트 + event_resolver 라우팅. **S2d CRUD 영속 ✅** — `event_timeline_service`(create/append-only/get/set_snapshot 쌍방향강제/cluster_event_map/event_links possible/apply_routing 단일 원자 tx+동시 CREATE rollback, ADR#19) + 회귀 27. **S2e 통합 파이프라인 ✅** — `event_resolution_pipeline`(실 cross_source_dedup→resolver→apply_routing 배선) + 통합 로직 E2E + 삭제정책 ADR#20. **✅ live-PG 검증(ADR#21)** — alembic 0001~0006 실 Postgres up/down + E2E(CREATE/APPEND/HOLD·멱등·FSD·sanitize)·2-세션 동시 CREATE orphan 0·FK RESTRICT 삭제 차단. **✅ C live wiring(ADR#22)** — `event_ingest_pipeline`(수집 후보→cross_source_dedup→candidate_for→resolver→events/event_updates; flag `EVENT_RESOLUTION_ENABLED` 기본 off; 후보 격리; 본문/PII 차단; singletons 가시화) + `run_production_orchestration(event_resolution_sink=)` 주입 seam + live-PG candidate→CREATE→APPEND. event_cards 무변경 병행. **✅ D-1 운영 결선(ADR#23)** — `backend/app/tools/run_event_orchestration.py`(backend-side composition root: 전용 NullPool 엔진 생명주기 소유 + `make_orchestration_event_sink` 주입 → ingestion `main(event_resolution_sink=)` 위임; ingestion→backend import 0, decoupling 보존) + `--event-resolution`/`EVENT_RESOLUTION_ENABLED` 게이트 + live-PG 로 실 sink → Event CREATE→APPEND 입증. **운영 runner 가 Event 영속 *능력* 확보**(flag off 기본=DB 미접근·event_cards 경로 보존; 주기 자동 가동은 미배선). **✅ D-2a Event 타임라인 read API(ADR#24)** — `/api/events/timeline`(list)·`/timeline/{id}`(event+updates) additive endpoint(`EVENT_TIMELINE_API_ENABLED` flag, held degenerate 제외, 레거시 event_cards 무영향) → Event 타임라인이 웹 레이어로 처음 연결. **✅ D-2b frontend 렌더(ADR#25)** — Next.js `/events/timeline`(목록)·`/events/timeline/[id]`(상세) page+컴포넌트(`EventTimelineCard`/`List`/`EventUpdateItem`) + `lib/api` 타입/메서드 + nav; 안전 evidence 렌더(url http/https 게이트+rel, allowlist 6키만, source_refs 미렌더), flag off→graceful 빈상태/notFound; 기존 event_cards UI 무변경. tsc 0·node:test 12·lint 0. **✅ D-2b 하드닝(ADR#26)** — 테스트 provider mock 격리(conftest, `.env` 비의존·network 0; pre-existing embedding 결합 해소) + 공개 read 스키마 분리(`PublicEventUpdate` source_refs 제외) + 에러표현 통일 → R-EventTimelineRenderHardening ①③ 종결. **✅ D-2c 데모(ADR#27, 2026-06-23)** — `seed_event_timeline`(합성 Event 4건×update 3~4·자연어 delta_summary·example.com evidence·멱등·오프라인, service 직접 영속) + `db_target`(2중 fail-closed 가드=APP_ENV allowlist+dbname 교차검증, R-EventSinkDbTarget **종결**) + compose `EVENT_TIMELINE_API_ENABLED` on. **실증(로컬·비-컨테이너): live-PG seed→list_events/get_public_event + uvicorn `/api/events/timeline`(내부ID/source_refs 미노출) + Next.js `next dev`+Playwright 브라우저 스크린샷(목록 4카드·상세 4 update+evidence) + `/events` event_cards graceful 회귀 → 제품 북극성("웹에서 Event 타임라인을 본다")의 첫 실거동 가시화(full compose 빌드 E2E 는 잔여).** **✅ REAL_SOURCE_LOOP_AUDIT(ADR#28, 2026-06-23, 3-agent 전수):** 경로 A(수집→raw_events; raw_events→event_cards) 실데이터 **PROVEN**(live probe·`_prod_orch.log` 653건·ap_news 100→event_cards[전량 hold]); 경로 B(수집→cross_source_dedup→event_ingest→resolution→event_timeline→API→frontend) **코드 배선 완료이나 실데이터 0회**(전 입증=fake session/하드코딩 synthetic record/example.com seed; 최신 prod-validation=mirror sink, event_resolution 미주입; delta_summary 실경로=디버그 라벨). **D-2c=화면 렌더 능력 검증≠실 파이프라인 검증** → **R-RealSourceLoopUnproven(MEDIUM) 신규.** **✅ 실 소스 production-validation(ADR#29, 2026-06-23):** keyless 뉴스 10소스 live fetch(0 error)·**411 real records**→cross_source_dedup **2 클러스터**→resolver **CREATE 2 + HOLD 3**(약신호 corroborator 보류=R-FalseMerge 실데이터 작동)→`/api/events/timeline` **2 실 Event non-empty**→`/events/timeline` 브라우저 렌더(yna `코스피 서킷브레이커`·매경 `대우건설 중동재건 TF`). **경로 B 가 실 웹 데이터로 Event 생성·화면 노출 최초 입증 → R-RealSourceLoopUnproven MEDIUM→LOW 부분종결.** 발견: Event 생성=cross-source 겹침 필요(작은 fetch→클러스터 0), CREATE genesis=updates 0(evidence APPEND 에서만), delta_summary 실경로=디버그 라벨. **✅ delta_summary deterministic 자연어화(ADR#30, 2026-06-23):** `build_delta_summary`(LLM 0·distinct 정합)가 `event_ingest_pipeline.candidate_from_cluster` 에 적용 → 실경로 디버그 라벨 제거. **✅ CREATE genesis update(ADR#31, 2026-06-23):** `apply_routing` clean-win CREATE 에 genesis update 1행(생성 근거) 추가 — "CREATE는 update 0" 불변식 의도적 개정(마이그레이션 0; event_updates="append-only 관측 이력"; 멱등=create_event 1회성) → CREATE-only Event 빈 상세 해소. 불변식 의존 21단언 의도적 갱신(backend 268 green·live-PG 21). 실 파이프라인 CREATE→`/events/timeline/{id}` 화면 genesis 자연어("…동일 식별자로 확인된 사건입니다")+evidence 렌더 **1회 관측(Playwright)** → **R-EventTimelineRenderHardening 완전 종결(①②③).** ****✅ 비뉴스 타입 라우팅·fidelity 검증(ADR#32, 2026-06-23):** 결정론(실 파이프라인 5 시나리오)+실 fetch(probe). resolver type-blind(signal 강도) — official+news→CREATE(evidence official+article)·structured→0 Event(signal-only)·community+news→CREATE 저신뢰+community HELD·pure-community→발행 Event(gap). 실 fetch federal_register 10000·sec_edgar 100·hacker_news 3 LIVE. → **R-SourceTypeFidelityGate 신규(LOW)**, 코드 무변경. ****✅ source-type publish gate(ADR#33, 2026-06-23):** `resolve_routing` 에 `member_source_types`+신규 `ACTION_WITHHELD` — pure community/search/structured 단독 cross-source 직접 발행 차단(미매핑 CREATE 인데 publishable=official/article 0이면 WITHHELD·미영속·멱등). S5/S6/S7 withheld 재현(투자조언 경계 S6)·단위 12+ingest 3+live-PG 2. **R-SourceTypeFidelityGate MEDIUM→LOW 부분종결**(핵심 발행 차단 done·primary-authority 잔여). **다음 우선순위: (1) primary-authority(official>news>community, candidate primary 선정)→(2) 실 cross-source 비뉴스 Event 관측→(3) 실 fetch APPEND→(4) full `docker compose up --build` 빌드 E2E→(5) 주기 auto-trigger(Phase 2)→(6) event_cards↔Event 자동연결.**
- **S1 스코프(최소 토대, 2026-06-22 확정):** `events`(canonical_title/status/first_seen/last_update/heat/domains/tags/primary_entity_ids/snapshot_card_id) +
  `event_updates`(append-only: observed_at/delta_summary/evidence/added_domains/source_refs/heat_delta) +
  `event_cards.event_id` nullable FK. domains = 닫힌 8섹터 → **열린 2층(통제어휘 ~20 + free-form tags)**. heat = 시계열 활성도(half-life 감쇠).
- **S2a 구현됨:** `cluster_event_map`(cluster_id→event_id 라우팅, 단일 진실원천) + `event_links`(possible/confirmed/rejected/merged)는 **alembic 0005(S2a, 2026-06-22)에서 생성**(S1=0004 분리 유지). S2c event_resolver 가 라우팅을, S2d `apply_routing` 이 영속(map_cluster=단일출처, hold_link=possible)을 적용. 경계 권위 = `19 §2.2`.
- Why first(임계경로): 카드 알맹이 AI 품질을 올리기 전에 토대 형태를 고정 안 하면 곧 폐기될 1회성 스키마 위에 쌓인다(코딩 전 판단 원칙).
- Acceptance: alembic 0004(**additive**, nullable/신규 테이블, downgrade 제공), "2번째 보도 → 기존 Event Update append" E2E,
  **3엔진(PG/Milvus/OpenSearch) 동일 card_id 정합성 불변식 테스트 + 미전파 카드 메트릭(outbox SLO)**, 1517 green 무조건.
- Risks: 카드↔Event 이중쓰기 정합성 드리프트(R-EventModelMigration), Union-Find 오병합 영속화(R-FalseMerge). Complexity: 상.
- 상세: `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §1·§2`(NET-NEW, 00_INDEX 순위 #17) + `5_REFERENCE/EVENT_SCHEMA.md`(DDL) + `12`(개정).

## Phase 4 — Search API expansion layer (tiered + budget + gate + Change Detection)
- Goal: provider-agnostic tiered router(무료→유료), event 트리거 enrichment. **LAYER P(LLM 확장쿼리) → LAYER G(게이트) → LAYER F(fetch)** 분리(ADR#14).
- Net-new(미배선): `query_generator.generate()`(현 `NotImplementedError`), `expansion_router.py`(tiered + per-event/월 budget guard + SSRF allowlist 14 §3), Change Detection(ETag/Last-Modified/norm_hash→SKIP verdict — **S1과 동시 착수 권장**, 비용 지렛대 선점).
- Acceptance: candidate→확장→dedup→**Event append**(카드 아님), per-event/월 예산 guard 강제, 다중 fallback, **batch 1후보 실패가 나머지 확장 차단 안 함**(R-ExpansionPartialFailure 격리). Complexity: 중.

## Phase 5 — hybrid search + reranker + nori (indexing)
- Goal: RRF hybrid → cross-encoder rerank → nori.
- Acceptance: golden set nDCG/Recall@k 베이스라인, p99 내, fusion-only 폴백. Complexity: 중.

## Phase 6 — LLM SourceSupervisor 실 provider 연결 (P/G/F + unsafe gate + audit, ADR#14)
- Goal: `llm_propose` 콜백 실연결(LAYER P, allowed 게이트 LAYER G 강제, 끄면 규칙기반 동작). **사건유형 → role 매핑**(source_role.py 7역할 재사용).
- Net-new(미배선): `source_supervisor.decide(llm_propose=create_judge_client 래퍼, llm_available=LLM_PROVIDER≠"")` 실 provider 배선 + **audit trace 구조화**(제안·채택·거부) — 현 `source_supervisor.py:104`는 허용 밖 제안을 *침묵 폐기*(R-LLMCollectBoundary).
- Acceptance: 옵션 on/off 모두 동작, **LLM 동적 unsafe 제안이 반환값+로그에 명시되는 회귀**, 월 예산 상한 강제, fallback 100%, eval CI. Complexity: 중.

## Phase 7 — Event clustering / ranking / timeline 완성 (heat + FSD)
- Goal: 4신호 랭킹(freshness/corroboration/diversity/impact) + timeline(FSD) + **heat 시계열 활성도(half-life 감쇠)**.
- 의존: Event 토대 Phase(S1). 랭킹·timeline은 카드가 아니라 **Event/Update 객체** 위에서 동작.
- Acceptance: 설명가능 랭킹, timeline 단조 정렬, corroboration precision 측정, **heat 우선순위 큐가 발견 triage 예산을 굶기지 않음**(R-DiscoveryCostStarvation: budget 3축화). Complexity: 중상.

## Phase 8 — KG-RAG / GraphRAG (조건부) + Evidence Graph
- Goal: vector RAG로 못 푸는 multi-hop use case 한정 PoC + **EvidenceNode(증거 그래프, 09 경계 유지)**.
- Why now: mock 엔티티 제거 + vector RAG 커버리지 실측 이후에만.
- 불변(ADR#15): evidence graph **직접 판매(구독)는 닫힌 길** — 검증 위젯/SEO 허브/Live Index로 트래픽 증폭만(전문·구독·투자조언 저촉 금지).
- Acceptance: PoC 게이트(사전 성공기준) 통과, 근거 노드 인용, ROI 추적. Complexity: 상. Do-not-do: <1000 엔티티에 도입, mock 위 그래프.

## Phase 9 — 수익화 전환: 트래픽 × 광고 × 커뮤니티 (구독 폐기, ADR#15)
- **방향 전환:** 레거시 "B2B alert/report/API **구독** 4티어"는 **폐기**. 수익 = **트래픽 기반 광고 + 커뮤니티식 운영**(구독형 진화 안 함). 성장 루프 = 고품질 사건추적(시계열·다분야) + 에이전트 해설/논쟁 + 유저 상호작용 → 체류↑·재방문↑ → 페이지뷰↑ → 광고 노출↑.
- 선행 필수: **Event 토대(S1) + 실데이터** 이후(그 전엔 영업이 모래성, 00_ROADMAP_INDEX §4).
- Net-new(미배선, 제품 표면 0): 광고 인벤토리 4종(self-serve 수요측 도메인 직판 포함) + 커뮤니티(`comment.py` 확장 + Agent Debate, 아래 PD) + Live Index/SEO 허브/검증 위젯(트래픽 증폭) + KPI 계측.
- KPI(구독 LOI3/유료30 **폐기**): **북극성 = Monetizable Dwell**(도메인 RPM 비대칭) + **광고주 갱신율**(수요측). 신뢰 트래픽 등급제(봇/AI콘텐츠 방어) + 페이지 비전문비율 게이트(광고 정당성 측정·강제).
- 불변: 정보제공(투자조언 0) · 전문저장 0 · finance 광고는 비투자 B2B 화이트리스트만 · evidence graph 직접 판매(구독) 금지.
- Acceptance: 단일 vertical 라이브 → 광고 인벤토리 1종 가동 → 활성 광고주 N + 갱신율 X% + Monetizable Dwell 계측. Complexity: 상. Risks: R-AdModelFragility(콜드스타트·봇·brand-safety·단일점).
- 상세: `docs/2_ROADMAP/13_COMMERCIALIZATION_AND_PRODUCT_STRATEGY.md`(상업화 단일출처, ADR#15 개정 반영).

## Phase Agent Debate (PD) — 페르소나 논쟁 + 발화 게이트 fail-closed (S9, NET-NEW)
- Goal: 에이전트 페르소나가 사건을 해설·반박하는 논쟁 레이어(커뮤니티 트래픽 루프의 핵심 콘텐츠, Phase 9 연결).
- Net-new(미배선): `comment.py` debate 컬럼 확장 + `agent_debate` 페르소나 논쟁 그래프 + **발화 게이트**(14 §2.2).
- 발화 게이트 fail-closed: ① `evidence_refs` 필수(없으면 게시 거부) ② 투자조언 톤 필터(`has_investment_advice`) ③ injection 방어(EvidenceGate 확장, 에이전트 출력=untrusted) ④ kill switch `DEBATE_ENABLED=false`.
- Acceptance: evidence 없는 에이전트 발화 거부 테스트 + 투자조언 표현 차단 회귀 + injection 차단 테스트. Risks: R-AgentDebateSafety(투자조언화·근거없는 단정·injection). Complexity: 중상.
- 상세: `docs/2_ROADMAP/19_WEB_INTELLIGENCE_IMPLEMENTATION_SPEC.md §9`(NET-NEW, 00_INDEX 순위 #17).

## Phase 10 — Enterprise-grade security / compliance
- Goal: Admin RBAC(빈토큰 bypass 해제), SSRF allowlist, retention TTL, PII 스크럽, 라이선스 매트릭스, prod docker/TLS.
- Acceptance: 상업 공개 선행조건(14 §7 (1)~(6) 전수) 충족, secret scan PASS. Complexity: 상.

---

## 의존 그래프 (Event 토대 임계경로 반영 — 00_ROADMAP_INDEX §4 정합)

```text
P1(배선) ─┬─> P2(큐/관측) ───────────────────────────────┐
          └─> P3(mock해제/dedup) ─┐                       │
                                  ▼                       ▼
                        S1(★Event/Update 토대★)[임계경로 최우선]
                        + S1.5 Change Detection(동시 착수, 비용 선점)
                                  │
                                  ▼
                        P4(검색확장: LAYER P/G/F + budget)
                                  │
            ┌─────────────────────┼─────────────────────┐
            ▼                     ▼                     ▼
   P5(hybrid/rerank)    P7(clustering/rank/heat)   P6(supervisor 실연결 + audit)
                                  │
                                  ▼
                        P8(GraphRAG, 조건부 <1000 금지) + Evidence Graph
                                  │
                                  ▼
                        P9(트래픽×광고×커뮤니티, 구독폐기) ──> PD(Agent Debate)
                                  │
                                  ▼
                        P10(enterprise 보안/컴플라이언스, 14 §7 (1)~(6))
```

> **S1이 선행:** Event 토대를 먼저 고정하지 않으면 Phase3 잔여(카드 AI 품질)·P4 확장이 곧 폐기될 1회성 카드 스키마 위에 쌓인다(ADR#16). **선행 필수:** 상용화(P9)·검색고도화(P5)는 S1+실데이터 이후. 토대 없이 고급 layer 욕심 금지.
>
> **RISK 링크(`_RISK/RISK_REGISTER.md`):** S1=R-EventModelMigration·R-FalseMerge · P4=R-ExpansionPartialFailure·R-DiscoveryCostStarvation · P6=R-LLMCollectBoundary·R-PromptInjection(상향) · PD=R-AgentDebateSafety · P9=R-AdModelFragility. **불변(모든 Phase):** 우회 0 · 전문저장 0 · 투자조언 0 · `.env` 미열람 · 1517 green.
