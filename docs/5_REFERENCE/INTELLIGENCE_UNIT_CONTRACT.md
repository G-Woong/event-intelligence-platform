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

**community reaction layer(미래 reaction summarizer 의 정제 차원, agent 담당):** community 는 **사건 식별 anchor 가
아니라 reaction evidence** 다(semantic identity 후보의 merge anchor 불가 — `_PUBLISHABLE_SOURCE_TYPES` 에서 제외).
agent 는 community 를 ① 반응량 ② 논쟁 축 ③ 대표 질문 ④ 기대/불만 ⑤ 분위기 변화 ⑥ 루머/확인 분리 로 정제한다(원문 직노출
아님). 마찬가지로 market/numeric=signal evidence·catalog=entity enrichment·official/news=factual/authority evidence —
**final Intelligence Unit 은 raw source 가 아니라 curated synthesis.** semantic identity gold set 은 이 합성의 merge 안전장치다.

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
  shadow status(③)는 ADR#43 `export_identity_eval_pairs`(human-labeling 워크시트)로 소비 시작 — 실 병합·labeled 평가셋 전까지 "중복 해결" 아님.
- **identity evaluation gate(④ 전 선결)**: ③→④ 실 병합 전 **independent gold 대비 precision/FPR 측정**이 선결이다
  (`identity_eval_dataset.py`·MERGE_GATE: precision≥0.98·FPR≤0.01·hard-neg FP=0·언어별). 현재 deterministic
  adjudicator 진단 precision 0.57 → **gate 미달 → 자동 병합 금지**(R-IdentityEvalDataset·R-IdentityHumanLabeling).
  MERGE_GATE 충족돼도 자동 병합은 런타임 배선·adversarial 승인 전까지 OFF.
- **human-labeled gold workflow(ADR#44, ④ 전 선결)**: gold 는 self-label(adjudicator 출력)이 아니라 **사람이 검수한
  label** 이어야 한다 — `identity_human_labeling.py`(`GoldPair`: provenance reviewed_by/reviewed_at/review_status/
  label_confidence + dataset_source 분리자·`promote_worksheet_to_gold`=self-label 금지·`evaluate_gold_merge_readiness`=
  **live_derived gold만**·표본 floor·`auto_merge_enabled=False`). 워크시트(②③ 산출)→사람 라벨→gold→gold-only metric.
  **실 human-reviewed production gold·통계 규모·reviewer agreement 가 없으면 ④ 실 병합 금지**(LLM self-label 을 gold 로
  쓰는 것도 금지 — 옵션 C 거부). IU 합성기는 gold gate 통과 전까지 ③ shadow status 만 신뢰도 신호로 받는다.
- **reviewer agreement protocol(ADR#45, gold 신뢰의 선결)**: 단일 reviewer label 은 곧장 gold 가 아니다 —
  `resolve_gold_from_reviewers`(1명=insufficient_reviews·2+전원합의=agreed·불일치+사람 adjudication=adjudicated·
  **불일치=conflict[자동 gold 금지]**)·`_validate_adjudication`(LLM-as-judge 차단). gold 신뢰는 **다중 reviewer
  합의(또는 사람 adjudication)** 에서 온다. sampling bucket(대표성)·통계적 표본 floor(`estimate_sample_floor_*`:
  precision 0.98→~189·FPR 0.01→~381)로 한국어/hard-negative 를 평균 뒤에 숨기지 않는다. **실 reviewer 합의 실측·
  운영 절차(SLA)·대표 표본 이 없으면 ④ 금지**(R-ReviewerAgreement·R-GoldSamplingBias).
- **live-derived labeling packet(ADR#46, reviewer 검수의 운영 scaffold)**: live 후보(②③ 워크시트)→reviewer 배정
  packet 으로 변환하는 운영 단계 — `build_labeling_packet`(bucket 샘플링·동일 pair distinct ≥2명 배정)·
  **`labeler_facing_view`(model 판정 predicted_status/score/reason·sampling_bucket 차폐=bias 0)**·
  `summarize_packet_sampling`(bucket deficit/oversample·표본 floor 대조; **selection=무작위 아닌 결정론 정렬 cut-off**·
  대표성 미입증)·`adjudication_queue_from_resolved`(conflict→사람 lead 큐·LLM-as-judge 차단). packet 은 raw body/PII·
  model 판정을 **구조적으로 미포함**(internal-only ops artifact). community/market/catalog 는 packet 의 **guard bucket**
  (역할 검증)이지 merge anchor 가 아니다. **packet 은 reviewer label→gold 입력 도구일 뿐 gold 아님** — 실 reviewer
  검수·충원·대표성이 없으면 ④ 금지(R-ReviewerAgreement·R-GoldSamplingBias). labeler 에게는 `labeler_facing_view` 만
  제시한다(packet JSONL 의 bucket 노출 금지는 운영 약속).
- **live-derived labeling packet pilot(ADR#47, 운영 백로그 read + 옵션 D 표집)**: `build_live_identity_labeling_packet.py`
  (**read-only**·DB write 0)가 위 packet 운영을 **synthetic fixture 가 아니라 live-PG adjudication 백로그**에 적용 —
  `collect_live_identity_candidates`(backlog/exclusion report)·`generate_live_packet_report`(Event count before/after 로
  자동 병합 0 입증·`auto_merge_enabled=False`). 옵션 D `deterministic_bucket_hash_cap`(sha256 정렬·정렬 편향 완화·재현).
  **정직 경계**: live_selected 는 **실 파이프라인(결정론) 유래 1**이고, **운영 자동 백로그는 0**(단계 ③ adjudication
  live 루프 미배선·운영 DB 미마이그레이션 → `exclusion_reasons.semantic_link_without_adjudication` 로 표면화·R-LiveIdentityBacklog).
  packet 은 여전히 **gold 가 아니다** — 실 reviewer 합의·운영 백로그 누적 전 ④ 금지.
- **stage③ operational wiring(ADR#48, 운영 백로그 자동 누적의 배선)**: `ingest_records_to_events(adjudicate_semantic=)` 가
  배치 뒤 flag(`EVENT_SEMANTIC_ADJUDICATION_ENABLED`·**off-by-default**) on 이면 단계 ③ `adjudicate_semantic_links` 를
  자동 실행해 `event_identity_adjudication` 백로그를 누적한다 — 그래야 위 packet pilot 이 **synthetic/수동 주입 없이**
  운영 후보를 읽는다(자동 병합 0·shadow write only·멱등). `identity_backlog_readiness`(read-only)가 운영 DB migration
  gap(0003 vs head 0009·6 뒤·non-destructive)을 진단. **정직 경계**: 이는 **배선(능력)**이고, 운영 DB upgrade 미적용·
  실 fetch 0 → **production 백로그는 여전히 0**(R-LiveIdentityBacklog OPEN). 배선 ≠ 운영 가동.
- **incremental / no-cluster backfill(ADR#49, 운영 비용·backfill 안전)**: stage③ 가 매 배치 전수 재판정(O(N)) 하던 비용을
  `adjudicate_semantic_links(only_unadjudicated=,limit=)` 로 **미판정 link 한정**(비싼 Event view load 만 bounded·ambiguity
  정확성은 전체 cand_targets 로 불변). `if not clusters: return` 제거 → 클러스터 0 배치도 pending backfill. 신규
  `backfill_semantic_adjudications.py`(dry-run·bounded·read+adjudication upsert only·자동 병합 0)가 누적 백로그를 주기
  job/수동으로 따라잡는 entry. 운영 DB 0003→0009 배포 **runbook** 문서화(`15_ROADMAP §`·실행 미승인). **정직 경계**:
  여전히 cheap id-only 전수 스캔은 O(all-links)(대형 백로그 keyset 필요)·동시 backfill 직렬화 미명세(멱등이라 안전)·
  운영 가동(DB 배포·실 fetch·주기 스케줄러) 잔여. backfill 은 **능력**이고 production 백로그는 0(R-LiveIdentityBacklog OPEN).
- **backfill operation hardening + deploy checklist(ADR#50, merge safety substrate 의 운영 준비)**: backfill/scheduler 는
  Intelligence Unit **merge safety substrate** — 잘못된 자동 병합을 막기 위한 백로그·평가 준비이지, 그 자체가 public 단위가
  아니다. ADR#49 가 남긴 cheap O(전체) scan 을 **bounded run 한정 keyset 으로 완화**: `_semantic_links`/`adjudicate_semantic_links(after_link_id=)`
  가 `WHERE id>cursor·NOT IN adjudication·LIMIT` 을 SQL 로 push(페이지만 적재)·**ambiguity 는 page candidate 한정
  GROUP BY(`_candidate_target_counts`)로 link별 status 동작 보존**. `backfill_semantic_adjudications` 운영 CLI(`--limit/
  --after-link-id/--dry-run`·safe-target 가드·next_cursor/full_scan/idempotent_persist report·**lock 과대주장 0**)·
  `build_operational_deploy_checklist`(0003→head 명령·backup_required·**executed=False**·미실행). **정직 경계**: ⓐ cursor 는
  **UUIDv4 byte 순서(시간순 아님)** — 재현 가능 페이지 경계일 뿐, 백로그 진행/완전성 보장은 cursor 가 아니라 `only_unadjudicated`
  (limit/cursor 미지정 전수 경로는 `full_scan=True` 로 표면화). ⓑ 주기 가동은 기존 `run_recovery_scheduler --once` 관용구
  **재사용 가능(설계)**일 뿐 실제 docker 서비스는 운영 DB migration 후 게이트(**미배선**). ⓒ 교차 backfill 은 link_id PK upsert 로
  **중복행 0(데이터 안전)**이나 lock 은 없음(중복 work 가능·OS-병렬 race 미stress-test). 여전히 **능력**·production 0.
- **backfill scheduler operationalization(ADR#51, substrate 운영 준비 심화)**: backfill 을 주기 운영 job 으로 안전 연결 —
  preflight gate(`backfill_preflight`/`run_backfill_with_preflight`·ready_for_stage3 **hard gate**[운영 DB 0003 adjudication
  테이블 부재 시 dry-run 포함 차단·NOT IN 쿼리 크래시 방지]+flag persist gate[`EVENT_SEMANTIC_ADJUDICATION_ENABLED` off→persist
  만 차단·dry-run 허용·`allow_flag_off` 우회])·deterministic exit code(`decide_exit_code` 0=성공/1=blocked/2=runtime/3=dry-run
  pending·scheduler/cron 결정론 관측)·**`created_at` 시간순 cursor**(`cursor_mode='created_at'`·`or_(created_at>cur,
  and_(created_at==cur, id>after_link_id))` 컬럼 비교[행값 `tuple_` 는 우변 UUID 타입강제 실패 'uuid>varchar'→교체·동치]·
  `next_created_at` → 오래된 백로그 우선)·scheduler 스크립트(`workers/tools/run_semantic_backfill_scheduler.py`·recovery-scheduler
  관용구 복제·gated·**dry-run default·--limit 기본 100·docker 미배선·미가동**). **정직 경계**: created_at 은 **배치 간**만 시간순
  정확(동일 배치 intra-txn 동일 timestamp→id tie-break·임의)·created_at 인덱스 없어 정렬 비용·scheduler 실가동 0·advisory lock
  미구현(중복 work 가능). adversarial 기술계약 VALID(자동 병합 0·dry-run default·미배선·lock 미과대주장). 여전히 **능력**·production 0.
- **production scheduler activation readiness(ADR#52, substrate 운영 배선)**: merge safety substrate 의 주기 운영을 docker 로
  배선 — scheduler 가 compose 서비스 `semantic-backfill-scheduler`(**`profiles:["backfill"]` 기본 미기동·dry-run default[command
  --persist 부재]·preflight gated·단일 instance[replicas 미설정·restart "no"]**·backend 이미지 재사용[worker 이미지는 services/
  tools/models 미COPY→import 불가]·entrypoint override[entrypoint.sh 의 alembic+uvicorn 대신 scheduler 모듈]). **정직 경계**:
  옵션 C(created_at index)·D(advisory lock)는 근거와 함께 DEFER(backlog 0·prod 0003 에서 순수 미래-스케일 최적화·test churn 회피 —
  index DDL/single-instance 요건은 runbook 문서화)·**코드 변경 0**(compose+일관성 테스트 5)·docker build/up 미검증(정적 일관성 테스트만)·
  scheduler **실가동 0**(profile 비활성·운영 DB 0003·flag off). docker scaffold 는 운영 준비(능력)≠운영 가동·production 백로그 여전히 0.
- **production scheduler activation VALIDATION(ADR#53, substrate docker 실행성 실측)**: ADR#52 의 "정적만" 한계를 실 docker 로 해소 —
  `build` 성공·`run --once` **3경로 실측**(DB down→graceful exit 2·미마이그레이션→`BLOCKED readiness` exit 1·dev DB head→`dry_run=True
  event_count 0->0 auto_merge=False` exit 0). **🔴 정적 config/build 가 못 잡은 런타임 버그 발견·수정**: backend 이미지 `ingestion/` 미COPY→
  adjudicator 의 `ingestion.orchestration.cross_source_dedup` 전이 import `ModuleNotFoundError`→`COPY ingestion/`+회귀 테스트 2. **live-PG 91
  passed 재실행**(ADR#52 미실행). **정직 경계**: run#3 0->0 은 빈 dev DB 라 read-only 미입증(입증=코드 adjudication-only+live-PG)·live-PG 91=
  adjudicator/backfill **DB orchestration 정확성**(scheduler 주기 가동 아님)·검증 위해 dev event_intel head 마이그레이션(운영 DB 아님·additive)·
  C/D 계속 DEFER(backlog 0·test churn 실측)·adversarial **CONDITIONAL VALID**(코드·안전계약 VALID·HIGH-1 문서 미반영 정정 해소). docker
  실행성 입증(능력)≠운영 가동·**scheduler 실가동 0**·production 백로그 0.
- **production activation preflight + real-source smoke(ADR#54, 가동 전 점검 + 단계별 진단)**: `production_activation_preflight`
  (read-only·DDL/upgrade/persist 0)가 readiness+flag+safe_target+`classify_write_target`(named 분류·APP_ENV↔URL mismatch)를
  **17필드 한 report** 로 묶어 `can_persist` 게이트(`persist ∧ ready ∧ flag ∧ safe_target ∧ ¬destructive ∧ consistent`)·`block_reasons`·
  `next_required_actions` 산출 — dev event_intel safe-target **no-op(MEDIUM-1)을 warning 으로 표면화**(은폐 금지)·DATABASE_URL fingerprint 만.
  `real_source_identity_smoke`(기본 offline fake·network 0·DB 0·결정론)가 fetch→cluster→candidate 단계별 실패 분류(body_missing/
  non_publishable_role 등)+source_role_distribution 진단·DB 단계 offline None·`--live-db`(safe-target gated·test/dev)는 opt-in.
  **정직 경계**: 점검/진단(능력)≠가동·real_fetch 0(기본 fake)·운영 DB 무변경·production 백로그 0 불변. LLM/Agent 진입 9조건은
  `RAG_KG_AGENT_READINESS §6b`(현재 No-Go·본경로 구현 0).
  community=reaction evidence·market=signal·catalog=entity enrichment·official/news=factual/authority — semantic merge(④)
  검증 전까지 final Intelligence Unit merge 도 보수적(merge anchor 는 publishable core 만). **최종 주관은 Agent 가 하되 Agent 는 source
  role·identity·gold·MERGE_GATE·uncertainty 를 따라야 하며 LLM 판단은 orchestration loop 내부에서 evidence·guard 에 묶인다**(raw source
  즉시 요약 public output 금지).
- **real-source live-db smoke + source quality matrix(ADR#55, fake→실 fetch→실 DB 한 단계 진전)**: `real_source_identity_smoke`
  에 **live_network**(key-free official JSON API[federal_register]·bounded·opt-in·CI 아님·**본문 미저장**[headline/canonical/published_at 만])
  + **live_db**(disposable test/dev DB·safe-target gated)를 추가. 실 federal_register fetch 5 official records → `event_intel_test`(head 0009)
  ingest: **created 1 + identity_link 1(held member)·adjudications 0·packet_eligible 0·no_auto_merge·event_count 4→6**. `real_source_smoke_report`
  가 §4 activation report + **source quality matrix**(source별 body/canonical/published/identity readiness — Agent 가 source 처리전략 선택할 substrate)
  + agent readiness 9조건(결정론·단일 출처)을 조립. **정직 분해**: adjudications 0 은 held-member link 의 reason 이 `new_event_low_confidence`
  이지 `semantic_cross_batch_candidate` 가 아니라서(stage③은 semantic 후보 link 만 처리) — 실 Event 는 형성되나 cross-batch adjudication substrate 는
  **동일사건 다중소스/시계열 fingerprint 중첩**이 필요(single bounded single-source = source scarcity). community/market/catalog 는 `guard_only`(anchor 금지).
  **정직 경계**: live_network 는 opt-in tool/report(CI 아님)·live_db 는 disposable test DB(production 아님)·실 cross-source 비뉴스 Event/실 adjudication backlog/reviewer·gold·merge 잔여.
- **time-series replay smoke + adjudication block-reason 분해(ADR#56, cross-batch adjudication substrate 실데이터 입증)**: ADR#55 단일소스
  adjudications 0 의 원인을 정밀 분해(distinct document=distinct URL=distinct fingerprint → 같은-사건·다른-URL 후보 **구조적 불가**=source scarcity)하고,
  `run_time_series_replay_smoke`(safe-target gated·`--time-series-replay`·**artificial** 2배치: 배치 A 같은 URL 2 record→CREATE E1+fingerprint F·배치 B
  **다른 URL** 2 record[같은 제목·날짜=같은 F]→CREATE E2→`semantic_cross_batch_candidate` link→stage③ likely_same)로 **substrate 가 같은-사건·다른-URL·
  교차배치 데이터에서 닫힘을 실데이터 입증**: `event_intel_test`(head 0009) → **semantic_cross_batch_candidate 1·adjudications 1(likely_same_event)·
  event_count 0→2·no_auto_merge=True**(live-PG 잠금). `classify_adjudication_block_reason`(§5 순수: `db_not_reached`/`none`/`semantic_link_without_adjudication`/
  `non_publishable_role`/`no_fingerprint_overlap`/`no_cross_batch_overlap`)가 "왜 adjudication 0/N 인가"를 source/data/fingerprint/cross-batch 단계로 귀속
  (조용한 0 금지). **정직 경계**: `artificial_replay=True`(실 source behavior 아님 — 실 동일사건 다중소스/시계열 fetch 로 재확인 필요)·옵션 A(multi-source 실 fetch)는
  key-free 공식 단독 cross-source overlap 희소로 정직 분해만(스크레이퍼 미구현)·운영 DB 배포/reviewer/gold/merge 여전히 잔여·production 백로그 0 불변.
- **source overlap discovery + agent orchestration substrate(ADR#57, 실 cross-source overlap 다입도 분해·LLM 호출 0)**: 신규 `source_overlap_discovery.py`(write-free·no-DB·**no-merge**)가
  record 다입도 overlap 을 `fingerprint_overlap`(정확 token-set 일치 → deterministic 검출 → 교차배치 시 `semantic_cross_batch_candidate`) vs `near_match_below_fingerprint`
  (paraphrase overlap → **deterministic 사각지대**·미래 semantic adjudicator[embedding/LLM/KG] 영역·MERGE_GATE·gold 미충족이면 병합 금지)로 분해. **이것이 제품 계약의 핵심 경계**:
  Agent 는 overlap discovery 를 *주관/계획* 할 수 있으나(`build_agent_orchestration_schema`: recommended_source_pairs·expected_overlap_reason·source_role_constraints[merge anchor=publishable core 만·
  community=reaction layer]·uncertainty·**`no_merge_without_gate=True`·`no_public_intelligence_unit=True`·`llm_invoked=False`**) **MERGE_GATE·gold 없이 같은 사건이라고 단정하거나 병합하거나 public IU 를
  생성할 수 없다**. 실 GDELT bounded fetch(key-free·opt-in·`--live-gdelt`) 시도 → **429(R-Gdelt429) → captured fixture fallback**(`real_fetch=False` 표면화); fixture 6 possible overlap 중
  deterministic 1(verbatim wire)만 검출·5(paraphrase)는 adjudicator-zone → **실 cross-source overlap 의 다수는 결정론 사각지대**(R-SourceOverlapScarcity 신규). community/market/catalog anchor 금지·
  `real_source_smoke_report` §8 overlap_potential/utility 로 source 별 처리전략(merge_anchor/reaction_layer/market_signal/entity_enrichment) substrate 노출. **합성≠실 source·실 overlap 미관측**.
- **real overlap acquisition strategy + near-match reviewer route(ADR#58, 실 RSS governed fetch·near-match→reviewer/gold·LLM 호출 0)**: ADR#57 GDELT 429 의 근인이 **이 backend 도구의 기존 governance 우회 raw httpx** 임을 규명하고
  시정한다 — `gdelt_provider_status`(read-only preflight·HostRateGate+rate_limit_policy+in_cooldown honor·network/write 0)+`fetch_gdelt_overlap_records` short-circuit(provider_status≠ok→network 미시도·no tight retry). **key-free RSS 함대 governed 실 fetch**
  (`fetch_rss_overlap_records`·`_SERVICE_CONFIGS` endpoint auth=none·shared host gate 참여·bounded·본문 미저장) **실측: bbc/aljazeera/the_verge/techcrunch 55 record(429 0)→cross-source overlap 0(`no_title_overlap`)·same-beat 30 record 도 0** → governance 재사용은
  검증(RSS 는 429 안 남·GDELT 우회와 대조)되었으나 **실 same-event overlap 은 untargeted feed 에서 구조적으로 희소**(fetch 성공≠overlap 확보·R-SourceOverlapScarcity 실데이터 확증). **제품 계약의 핵심 진전 = near-match reviewer route**: paraphrase near-match(deterministic 사각지대)를
  `build_near_match_reviewer_candidates` 가 **버리지도 병합하지도 않고** reviewer/gold worksheet 로 export(기존 `collect_adjudication_eval_pairs`→`build_labeling_packet` 스키마 재사용·label=unlabeled·**predicted_status 미포함**=bias 0·publishable×publishable 만·`no_merge_without_gold`).
  즉 IU 의 same-event 묶음은 결정론이 못 잡는 영역에서 **reviewer/gold/MERGE_GATE 통과 후에만** 가능하며, 그 전까지 near-match 는 hint/큐일 뿐 병합·public IU 가 아니다. `build_acquisition_plan`(source_pair/topic/time plan·LLM 0)+§9 source quality matrix(overlap_acquisition_utility/title_paraphrase_risk/provider_accessibility/rate_limit_risk).
  다음 게이트 = **targeted same-event acquisition**(query-capable provider)→detection 레이어(embedding/LLM adjudicator+gold). **실 cross-source overlap 미관측·합성/transport ≠ 실 source·운영 DB/gold/merge 잔여**.
- **near-match reviewer/gold queue operationalization(ADR#59, near-match→reviewer/gold 운영 큐·병합 0·LLM 0)**: ADR#58 의 통로(`build_near_match_reviewer_candidates`)를 **운영 큐로 물질화** — `near_match_reviewer_queue.build_near_match_reviewer_queue` 가 near positive(paraphrase) + hard negative 를 기존 `build_labeling_packet`/`validate_labeling_packet`/`resolve_gold_from_reviewers` 머신으로 보내 검증된 reviewer packet(predicted_status 미포함·`labeler_facing_view` bias 0·LLM 0)·`build_gold_seed_report`(gold_ready 실 gold만·merge_allowed False)·`resolve_queue_gold`(gold/conflict adjudication queue/agreement connector)·`build_reviewer_queue_acquisition_linkage`(source_pair별 near_match_yield/reviewer/gold value→목적 기반 수집)를 산출. embedding/LLM adjudicator 는 `EMBEDDING_LLM_ADJUDICATOR_INTERFACE`(output=provisional_score only·requires=gold+MERGE_GATE+adversarial·**status No-Go**·`semantic_score` seam)로 인터페이스만 고정.
  즉 IU 의 same-event 묶음을 위한 paraphrase 검출은 **reviewer/gold→MERGE_GATE→(미래)embedding-LLM adjudicator** 순으로만 닫히며, 그 전까지 near-match 는 reviewer 큐일 뿐 병합·public IU 가 아니다. **실 reviewer/gold 0**(큐는 substrate·detection 레이어 미구현·완전종결 금지).
- **targeted same-event acquisition → operating readiness(ADR#60, captured fixture 큐→targeted acquisition·병합 0·LLM 0·production_gold 0)**: ADR#59 큐를 `targeted_same_event_acquisition.py` 가 targeted acquisition(source-pair·topic·time-window)과 연결 — `build_reviewer_operating_checklist`(reviewer instruction: 같은 사건 판단하되 **모델 예측 숨김**·title/canonical/source role 만·확신 없으면 ambiguous/insufficient·**community 는 reaction layer·market/catalog 도 anchor 아님**·gold 전 병합 없음·allowed_labels·merge_policy=prohibited until MERGE_GATE)·`simulate_gold_calibration`(synthetic 5경로 unanimous/conflict/single/adjudicated·**production_gold_count=0**)·`build_provider_capability_matrix`(오늘 query-capable key-free provider 사실상 0[GDELT 429·RSS topic 불가]→실 targeted near-match yield 낮음 정직). 즉 IU 의 same-event 묶음을 위한 reviewer/gold 운영 준비는 닫혔으나, **실 near-match 후보·실 reviewer/gold 0**(fixture=경로 입증·운영 readiness≠실 gold·embedding/LLM adjudicator No-Go 유지).
- **query-capable provider acquisition readiness gate(ADR#61, provider 가용성 분류+optional live query·병합 0·LLM 0·운영 DB 0)**: ADR#60 의 "다음 게이트=query-capable provider" 를 `provider_readiness.py` 가 운영 gate 로 물질화 — provider 를 key_free_query/key_required_query/key_free_non_query/blocked/unknown 분류 + credential(`env_status` **secret-safe** present/missing·값 0)·host_gate cooldown·**`fetch_implemented` gate**(실 fetcher=gdelt/rss 만→미배선 provider 는 credential-ready 여도 `fetcher_not_wired`·opt-in live query 시 fixture 둔갑 **코드 차단**·dataset_source None) + optional bounded live query(opt-in·gated→live_derived 후보 시 near-match queue 연결·없으면 block_reason+next_action). 즉 IU same-event 묶음의 입력(실 near-match 후보)을 채울 provider 가 무엇이 막는지(credential/cooldown/wiring)를 정확히 표면화하나, **실 wired+working key-free provider=gdelt[429]만→실 near-match 후보·reviewer/gold 0**(provider readiness=능력 표면화·실 후보 아님·community/market/catalog anchor 금지·embedding/LLM No-Go 유지).
- **provider query adapter contract + 첫 wired adapter(ADR#62, fetcher 배선·병합 0·LLM 0·운영 DB 0)**: ADR#61 의 `fetcher_not_wired` 병목을 `provider_query_adapters.py`(ProviderQueryAdapter/ProviderQueryResult 공통 contract + **Guardian Content API 실 adapter**·key-required·news·공식 shape·**본문 미저장**)로 한 단계 축소 — IU same-event 묶음의 입력(실 near-match 후보)을 만들 query provider fetch 가 따라야 할 계약을 정하고 첫 provider 를 wire. adapter records 는 ADR#60 `records=` 주입(real_fetch=True·**fixture 둔갑 0**)으로 near-match queue 까지만 연결되며 같은 사건 단정·병합·public IU 생성 0(reviewer/gold/MERGE_GATE 전). secret-safe(env_status present/missing·key httpx params 전용·url keyless). **단 실 key 미주입·fake transport 만→실 후보 0·미배선 9종 잔여**(adapter=능력·실 데이터 아님·community/market/catalog anchor 금지·embedding/LLM No-Go 유지).
- **secret-safe Guardian live query smoke + live-derived queue population gate(ADR#63, 실 key live 경로 실증·병합 0·LLM 0·운영 DB 0)**: ADR#62 adapter 의 실 network 직전 경계를 `guardian_live_query_smoke.py`(§4 smoke 계약·**env_not_loaded vs missing_credentials 구분**·`probe_env_var` 값 미열람·`run_optional_live_query` 위임)로 검증 — **실 Guardian 호출 2회**(opt-in·governed·secret-safe·Ukraine/earthquake 7d→각 records 10·candidate 0·`no_title_overlap`·dataset_source live_derived·**secret_exposed False·env_file_read False**·host_gate passed)로 IU same-event 묶음의 입력(실 near-match 후보) 생산 경로를 **실 key 로 실증**했으나 **단일 소스(Guardian) 내 same-event overlap 0**(구조적·같은 날 제목 Jaccard<near·recall 한계 포함·deterministic near-match=cross-source 설계). 즉 IU 입력의 다음 unblock=**2번째 publishable provider(cross-source)**. **live query 능력·실증≠실 near-match 후보**(queue_pop 0·reviewer/gold 0·community/market/catalog anchor 금지·embedding/LLM No-Go 유지).
- **2nd publishable provider(NYT) + cross-source live overlap smoke(ADR#64, cross-source pair 실증·병합 0·LLM 0·운영 DB 0)**: ADR#63 의 단일 소스 한계를 `provider_query_adapters` 에 **NYT adapter** wire(`api-key` param=Guardian 동일·본문 미저장)+`cross_source_live_overlap_smoke.py`(둘 다 성공만 cross-source 인정·near/hard pair 를 source_id 상이만 필터해 ADR#59 queue 충원)로 해소 — **실 Guardian+NYT 호출 4회**(Ukraine/earthquake 7d→각 combined 20·**cross_source_pair_count 100**·fingerprint 0·near 0·hard 0·`no_title_overlap`·dataset_source live_derived). 즉 IU same-event 묶음의 입력(cross-source pair)은 **단일 소스 구조적 0→100 으로 실증 생성**됐으나 **deterministic title-Jaccard(near 0.5)가 100 쌍 중 0 검출**(hard band 0.2 까지 0) — 이 0 은 deterministic paraphrase recall 한계 **또는** 두 매체의 **다른-사건 보도**(real scarcity) 둘 다 가능·n=2 미구분(100=비교 대상·match 아님). IU 입력의 수집/source/key/fetch 능력은 입증(단일 0→cross 100)됐고, 다음 방향은 **paraphrase 를 묶는 embedding/LLM semantic adjudicator**(reviewer/gold→MERGE_GATE→adjudicator 순·deterministic precision 0.57<0.98 **별도 근거**). **cross-source 능력·pair 생성≠검출·후보**(queue_pop 0·reviewer/gold 0·community/market/catalog anchor 금지·embedding/LLM No-Go 유지).
- **offline/gated semantic candidate scorer(ADR#65, detection scarcity 재분해·병합 0·LLM 0·embedding 실호출 0)**: ADR#64 의 "cross-source pair 100·deterministic 0 검출"을 다루는 첫 scorer 층 `semantic_candidate_scorer.py`(§5 `SemanticPairInput/SemanticPairScore` contract·`scorer_mode` deterministic_scaffold/fake_semantic/embedding_opt_in/llm_opt_in·`discover_overlap(emit_candidate_pairs)` 가 near floor 무관 전 cross-source pair 노출). score 는 **top-k rank**(threshold 아님)로 reviewer queue prioritization 으로만 — **score/rationale/model metadata 는 internal-only**(labeler_facing_view 숨김·`validate_labeling_packet` fail-loud)·`merge_allowed=False`·`requires_gold/merge_gate=True`·`production_gold_count=0`. embedding/LLM 은 **injection-only**(실 client 미배선=No-Go·`create_embedding_client`/`create_llm_client` 미래 seam·secret-safe `probe_env_var` gate·실호출 0). 즉 IU 입력의 **검출 우선순위 substrate**는 생겼으나 **validated adjudicator 아님**(deterministic_scaffold=ADR#64 의 0 신호와 동일·recall 개선 0·fake_semantic=배관 scaffold·실 embedding 아님). **score≠truth·prioritization≠검출·reviewer/gold 0·MERGE_GATE 미충족·community/market/catalog anchor 금지**.
- **reviewer label operations + gold calibration preflight(ADR#66, reviewer/gold operational readiness·병합 0·LLM 0·embedding 0·운영 DB 0)**: ADR#65 scorer top-k reviewer queue 를 `reviewer_label_operations.py`(DB-free orchestrator)가 **실 사람 라벨 운영**으로 연결 — packet export(labeler_view score/rationale/predicted_status 0)→label import(파일 없음→**no_labels graceful**·forbidden field[score/rationale/raw body/secret] allowlist fail-loud·reviewer_id **pseudonymization**[raw PII 미노출])→agreement/conflict/adjudication(single=insufficient·2+만장일치=agreed·conflict+human adjudication=adjudicated·LLM-as-judge 봉인)→**production/synthetic gold 분리**(production=label_source production AND dataset_source live_derived·synthetic/test=simulated only)→gold calibration preflight(precision/FPR denominator readiness·top_k_bias_warning·korean floor·merge_gate_ready False). 즉 IU same-event 묶음을 사람이 검증해 gold 로 승격하는 **운영 경로(export→label→agreement→gold→calibration)**가 닫혔으나 **실 production reviewer label·실 gold 여전히 0**(production_gold_count 0·calibration_ready/merge_gate_ready False·embedding/LLM 실호출 0·public IU 0·community/market/catalog anchor 금지). **진전=reviewer/gold operational readiness substrate·실 gold 아님·score≠truth·다음 hard blocker=real reviewer 충원**.
- **reviewer batch launch pack + intake validation loop(ADR#67, batch launch readiness·병합 0·LLM 0·embedding 0·운영 DB 0)**: ADR#66 reviewer label 운영 함수를 `reviewer_batch_launch.py` 가 **사람이 바로 라벨링을 시작할 운영 패키지**로 전환 — reviewer instruction(§6 4-라벨 정의/금지/권장·model score/rank 0)+label template(`REVIEWER_ALLOWED_KEYS` 빈 worksheet·reviewer_id pseudonym·score/bucket 0)+assignment manifest(pair 당 ≥2 reviewer·top-k+hard negative·capacity<2→`insufficient_reviewer_capacity`·raw roster 미commit)+intake plan(directory/expected files/validation command)+intake validation(import 前 dry-run·labeler vocab[unsure/needs_review]→canonical[insufficient/ambiguous] 정규화·forbidden/duplicate/unknown pair_id/model label 거부). 라벨 없음→**awaiting_labels**(정직·실패 아님)·실 라벨 시 `resolve_label_operations`+`build_calibration_preflight` 재사용·**decisive gold=same/different 만**(unsure/needs_review 는 gold 아님·`non_decisive_gold_count` 표면화). 즉 IU same-event 묶음을 사람이 검증할 **운영 패키지(batch pack→assignment→intake→agreement→gold→calibration)**가 닫혔으나 **실 production reviewer label·실 gold 여전히 0**(production_gold_count 0·calibration_ready/merge_gate_ready False·embedding/LLM 실호출 0·public IU 0·community/market/catalog anchor 금지). **진전=batch launch readiness substrate·실 gold 아님·다음 hard blocker=first production labels import**.
- **first production labels import pilot + intake/gold/calibration dry-run(ADR#68, first production label intake readiness·병합 0·LLM 0·embedding 0·운영 DB 0)**: ADR#67 batch pack 을 `production_label_intake.py` 가 **실 운영 intake 루프**로 연결 — intake_directory `*.jsonl` 다중파일 스캔(basename only·malformed fail-loud·부분 import 금지)→intake validation→`resolve_label_operations`+`build_calibration_preflight` 재사용(decisive gold only)→**calibration delta**(before/after gold·positive/negative/korean·precision/FPR/KO denominator readiness·`next_needed_for_merge_gate`). label 없음→**awaiting_production_labels**(정직·실패 아님)+operator no_labels_report(next_action checklist)·production gold=production AND live_derived decisive·`production_gold_provenance_verified` False(선언 기반·R-IdentityHumanLabeling)·`.gitignore` outputs/reviewer_batch/ PII 가드. 즉 IU same-event 묶음을 사람이 검증하는 **실 운영 intake(scan→validation→agreement→gold→calibration delta)**가 닫혔으나 **실 production reviewer label·실 gold 여전히 0**(production_gold_count 0·calibration_ready/merge_gate_ready False·embedding/LLM 실호출 0·public IU 0·community/market/catalog anchor 금지). **진전=first production label intake readiness substrate·실 gold 아님·다음 hard blocker=first production label file 회수(R-ReviewerFollowupOps)**.
- **reviewer follow-up operations + label collection status cockpit(ADR#69, reviewer follow-up readiness·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0)**: ADR#68 가 정직하게 드러낸 운영 병목(batch pack 발행됐으나 실 label 미회수→영구 awaiting)을 `reviewer_followup_ops.py` 가 **추적 가능한 운영 상태**로 전환 — assignment(expected) vs 회수(actual) coverage(reviewer pseudonym/pair 별 missing·pseudonym 공간·재pseudonymize 0)·7-state `followup_status`(not_launchable/no_labels/partial_labels/invalid_labels/conflict_pending/calibration_pending/imported_ready_for_merge_gate_review·invalid>partial fail-loud)·PII-safe reminder/escalation template(**전송 0**·pseudonym/basename/pair_id/validation command/allowed labels 만·raw name/email/score/rationale/predicted_status 0)·reviewer SLA/capacity. production_gold_count 은 intake **exact passthrough**(follow-up 만으로 미증가). 즉 IU same-event 검증의 **사람 루프(batch→assignment→follow-up→intake→agreement→gold→calibration)**가 운영적으로 추적 가능해졌으나 **실 production reviewer label·실 gold·실 label 회수 여전히 0**(production_gold_count 0·calibration_ready/merge_gate_ready False·실제 email/slack/webhook 전송 0·community/market/catalog anchor 금지). **진전=follow-up 운영 cockpit substrate·실 label 회수 아님·다음 hard blocker=actual reviewer contact/첫 returned labels(R-ReviewerFollowupOps)**.
- **actual reviewer pilot handoff + returned-label gate(ADR#70, reviewer pilot readiness·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0)**: ADR#69 follow-up cockpit 을 `reviewer_pilot_handoff.py`(followup 단일 호출 decorate)가 **실 reviewer pilot 을 시작 가능한 handoff** 로 — operator 가 실 reviewer 에게 그대로 배포할 **handoff bundle**(reviewer instruction·reviewer 별 assignment summary·label template schema·expected filename·intake dir·validation command·allowed labels·pseudonym only·재귀 forbidden-key 가드·**전송 0**)·**8-state pilot_status**(not_ready/ready_to_contact/awaiting_reviewer_return/partial_returned/invalid_returned/conflict_pending/calibration_pending/imported_ready·intake dir 존재로 접촉 전/회수 대기 분할)·**returned-label gate**(returned label 있으면 followup→intake end-to-end·없으면 정직)·correction/adjudication/calibration handoff(reason code only·human lead·자동 다수결 금지·전송 0)·**ops UI seed contract**(`OpsReviewBatchStatus`·미래 internal ops dashboard 가 읽을 workflow state·`flags{no_merge,no_public_iu,pii_safe,no_llm,no_db_write}`·**internal ≠ public IU**). production_gold_count 은 followup→intake **exact passthrough**(handoff 만으로 미증가·`actual_sending_performed`=False). 즉 IU same-event 검증의 사람 루프를 **실 pilot 운영으로 넘길 substrate(handoff bundle→returned-label gate→status→ops UI)**가 닫혔으나 **실 reviewer contact·첫 returned labels·실 gold 여전히 0**(production_gold_count 0·calibration_ready/merge_gate_ready False·실제 email/slack/webhook 전송 0·public IU UI No-Go·community/market/catalog anchor 금지). **진전=pilot handoff bundle+returned-label gate substrate·실 reviewer 실행 아님·다음 hard blocker=actual reviewer contact/첫 returned labels(R-ReviewerPilotExecution)·ops UI=internal workflow state≠public truth(R-OpsUIPrematureTruth)**.
- **reviewer pilot execution ledger + returned-labels monitor(ADR#71, pilot execution tracking·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0)**: ADR#70 handoff readiness 를 `reviewer_pilot_execution.py`(handoff 단일 호출 decorate)가 **실 pilot 실행 추적**으로 — operator 가 실제로 reviewer 에게 contact 했는지·첫 returned label 이 들어왔는지를 **PII-safe contact evidence ledger** 로 관리(operator 가 *수동으로 수행한* 접촉의 *기록*·시스템 전송 0·`real_reviewers_contacted`=roster ∩ contact_status=contacted 만·evidence 없으면 0·prepared/declined/unavailable 분리·둔갑 차단·allowlist 키+값-레벨 가드[pseudonym ASCII charset·due_hint ISO date-like·batch_id 교차검증])·**8-state execution_status**(not_started/awaiting_operator_contact/contacted_waiting_return + returned label 5종·pilot_status 의 회수 경로 축과 직교하는 contact 축)·**operator SLA/checklist**(reviewer 별 contact_status·returned_file_status·missing·overdue[as_of 기준·wall-clock 미커플링]·next_action)·**`InternalOpsPilotExecutionStatus`**(execution_status·contact_evidence_present 노출하되 `flags{internal_only,no_public_truth,…}`·same_event/label/verdict truth 미노출). production_gold_count 은 handoff **exact passthrough**(execution 만으로 미증가·`actual_sending_performed`/`merge_allowed`=False). 즉 IU same-event 검증의 사람 루프를 **실 pilot 실행 상태로 추적할 ledger(contact evidence→execution_status→returned-label monitor→SLA→ops UI)**가 닫혔으나 **실 reviewer contact·실 returned labels·실 gold 여전히 0**(contact evidence 는 operator 자기보고·production_gold_count 0·calibration_ready/merge_gate_ready False·실제 전송 0·public IU UI No-Go·community/market/catalog anchor 금지). **진전=pilot execution ledger+returned-labels monitor substrate·실 reviewer 실행 아님·다음 hard blocker=actual reviewer contact/첫 returned labels(R-ReviewerPilotExecution·R-ContactEvidenceIntegrity)·contact evidence raw PII 차단(R-ReviewerContactPII)**.
- **actual input gate + internal ops dashboard bridge(ADR#72, actual input gate + internal ops read-only·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0·입력 날조 0)**: ADR#71 ledger 를 `reviewer_actual_input_gate.py`(ledger 단일 호출 dispatch)가 **실 입력 게이트 + internal ops read-only 표면**으로 — gitignored `outputs/reviewer_batch/<batch>/` 를 **스캔만**(생성·날조 0)해 실 contact evidence/returned label 유무→5-state `actual_input_status`(no_actual_input/contact_evidence_only/returned_labels_present/invalid_returned_labels/labels_imported)·`external_input_required=production_gold_count==0` 정직·파일 존재 시 intake→followup→handoff end-to-end. backend read-only API(`GET /api/internal/ops/pilot-execution`·**이중 게이트** admin-token(prod fail-closed)+`INTERNAL_OPS_DASHBOARD_ENABLED` flag 404·sanitized `InternalOpsPilotExecutionStatus` 만·DB/LLM/embedding 0)·frontend seed(`/internal/ops-pilot`·server-env gate→`notFound()`·nav 미노출·**4중 게이트**·no-go 배너). 즉 reviewer pipeline 의 **운영 상태를 public truth 와 분리해 노출하는 internal ops read-only 표면**이 생겼으나 **실 reviewer 입력·실 gold 여전히 0**(production_gold_count 0·입력 디렉터리 부재→no_actual_input·실제 전송 0·**internal ops≠public IU**·same_event/score/rationale/predicted_status 미노출·community/market/catalog anchor 금지). **진전=actual input gate+internal ops read-only bridge substrate·실 reviewer 입력 아님·다음 hard blocker=actual returned labels(R-ReviewerPilotExecution)·internal ops auth/배포 경계(R-InternalOpsAuthBoundary)**. RAG/KG/Entity/LLM 은 gated roadmap(Stage R1~R7·merge No-Go).
- **internal ops auth/deploy preflight + R1~R7 readiness matrix(ADR#73, internal ops hardening + product bridge·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0·입력 날조 0·secret 값 미열람)**: ADR#72 internal ops 표면을 `internal_ops_preflight.py`(`run_actual_input_gate` 단일 호출 dispatch)가 **배포 안전성 preflight + gated readiness** 로 봉인 — `evaluate_internal_ops_posture`(순수·settings[admin token **존재 여부만**·값 미열람] 5-state: disabled_safe/enabled_internal_safe/**unsafe_public_exposure**[dev+flag+무토큰=무인증 reachable]/misconfigured/unknown·`deployment_proven=False` 불변)·`R1_R7_READINESS`(7-stage 머신리더블·gold→MERGE_GATE→embedding→entity→KG→GraphRAG→IU·`SOURCE_ROLE_INVARIANTS` community=reaction/market=signal/catalog=enrichment/search=URL/unknown=fail-closed/KG edge=provenance 필수/public IU=No-Go)·`run_internal_ops_preflight`(actual input 재확인+posture+readiness)·`GET /api/internal/ops/preflight`(이중 게이트·read-only·sanitized·admin token 값 필드 부재)·frontend posture/warnings/R1~R7/next-action 표시. 즉 internal ops 표면의 **auth/deploy posture 와 RAG/KG 미래 roadmap 을 테스트 가능·read-only 로 봉인**했으나 **실 reviewer 입력·실 gold 여전히 0**(production_gold_count 0·external_input_required·`deployment_proven=False`[per-user auth 미구현·물리 reachability 미증명]·merge/전송/입력 날조/secret 값 노출 0·**internal ops≠public IU**·community/market/catalog anchor 금지). **진전=internal ops auth/deploy preflight+read-only product bridge·실 reviewer 입력 아님·다음 hard blocker=actual returned labels(R1·R-ReviewerPilotExecution)·per-user auth+실 배포 경계(R-InternalOpsAuthBoundary)·RAG/KG 조기 build 규율(R-RagKgPrematureBuild)**. RAG/KG/Entity/LLM 은 gated roadmap(Stage R1~R7 matrix·merge No-Go).
- **R1 gold acquisition operating plan + internal ops R1 gap + source storage strategy(ADR#74, R1 acquisition·병합 0·LLM 0·embedding 0·운영 DB 0·전송 0·입력 날조 0·secret 값 미열람)**: ADR#73 readiness matrix 의 R1(FAIL) 행을 `r1_gold_acquisition_plan.py`(`run_actual_input_gate` 단일 호출 dispatch)가 **실 라벨 수집 운영 plan** 으로 — actual input 재확인→`r1_status` 4-state(blocked_no_labels[현재]/collecting/partially_satisfied/satisfied)·gold floor **gap 산술**(required−current·target=canonical live≥200/KO≥50/reviewer≥2 재사용+파생 positive≥67/negative≥67/hard-negative≥20·balance ratio≥0.5·FP=0 표본)·operator next_manual_actions(reviewer recruitment·handoff 배포·gitignored intake 적재·human-only adjudication·**전송 0·파일 생성 0**)·`GET /api/internal/ops/r1-gold-acquisition`(이중 게이트·read-only·sanitized)·frontend R1 gap 패널. **source-specific storage strategy**(§6b-S·docs only): official/news=anchor·community=reaction·market=signal·catalog=enrichment·search=URL·unknown=fail-closed·모든 KG edge=provenance 필수·GraphRAG=verified graph 전 금지·storage runtime=R4~R5 gate 전 미구현. 즉 IU same-event 검증의 R1 gold floor 를 **gap 산술·operator action 으로 운영화**했으나 **실 reviewer 입력·실 gold 여전히 0**(production_gold_count 0·gate exact passthrough·plan 만으로 미증가·**target=operating floor≠production truth**·R1 satisfied 는 calibration_ready 일 때만·synthetic/test/model→production gold 0·실제 전송 0·**internal ops≠public IU**·community/market/catalog anchor 금지). **진전=R1 acquisition operating plan+R1 gap 가시화+source storage 전략·실 reviewer 입력 아님·다음 hard blocker=actual returned labels(R1·R-ReviewerPilotExecution·R-GoldAcquisitionPlanOnly)**. RAG/KG/Entity/LLM 은 gated roadmap(Stage R1~R7 matrix·merge No-Go).

## 5. 정직 경계 (over-claim 방지)

- cross-batch 후보 LINK 는 **중복 Event count 를 줄이지 않는다**(실 병합 아님).
- LLM/RAG/KG/Entity/Agent 는 **미구축**(mock-default). Intelligence Unit 은 아직 substrate 단계.
- 이 문서는 **계약**이지 구현 증거가 아니다 — 구현 상태는 `RAG_KG_AGENT_READINESS.md` 가 단일 출처.
