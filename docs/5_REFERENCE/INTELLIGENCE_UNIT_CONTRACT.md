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
  community=reaction evidence·market=signal·catalog=entity enrichment·official/news=factual/authority — semantic merge(④)
  검증 전까지 final Intelligence Unit merge 도 보수적(merge anchor 는 publishable core 만).

## 5. 정직 경계 (over-claim 방지)

- cross-batch 후보 LINK 는 **중복 Event count 를 줄이지 않는다**(실 병합 아님).
- LLM/RAG/KG/Entity/Agent 는 **미구축**(mock-default). Intelligence Unit 은 아직 substrate 단계.
- 이 문서는 **계약**이지 구현 증거가 아니다 — 구현 상태는 `RAG_KG_AGENT_READINESS.md` 가 단일 출처.
