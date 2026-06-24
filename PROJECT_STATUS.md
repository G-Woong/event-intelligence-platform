# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 검수 작업지(labeling packet)를 **시연용 가짜 데이터가 아니라 실제 운영 DB(live-PG)의 후보**에서 만드는 도구를 추가했습니다. 동시에 **"왜 라이브 후보가 0인지"를 수치로 보여주는 진단**(어떤 후보가 어떤 이유로 빠졌는지)도 같이 냅니다. 도구는 **읽기 전용**이라 사건을 자동으로 합치지 않습니다.
- **이번 턴에 실제로 끝낸 것:** ADR#46 커밋(`ac636e7`) → **ADR#47 구현**: 신규 `build_live_identity_labeling_packet.py`(live-PG 백로그 read→packet·backlog/exclusion report·event count 전후 불변 입증) + 표집 옵션 D(`deterministic_bucket_hash_cap`·정렬 편향 완화·재현). 측정: **backend 비-live 447p/4s · live-PG 66p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial **JUSTIFIED**(안전 토대 견고·MEDIUM 1=본 docs 동기화로 해소).
- **정직한 한계:** live 후보(live_selected)는 **실 파이프라인(결정론) 유래 1건**이고, **운영 자동 백로그는 0**입니다 — 운영 DB가 아직 마이그레이션 안 됐고, 단계 ③(adjudication)이 운영 루프에 배선 안 돼 있기 때문(R-LiveIdentityBacklog 신규). 실 reviewer 합의·대표성·실 병합은 여전히 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `ac636e7`**(ADR#46, 본 턴 첫 커밋) 위 **ADR#47 = 미커밋 code 2(신규 `build_live_identity_labeling_packet.py` + `identity_human_labeling.py` 옵션 D 추가) + tests 2(신규 `test_live_identity_labeling_packet.py` + `test_event_resolution_live_pg`[+live tool 5]) + docs 8**. **migration 없음**.
- code: 신규 `build_live_identity_labeling_packet.py`(read-only·DB write 0: `collect_live_identity_candidates`[backlog/exclusion]·`generate_live_packet_report`[event count before/after·auto_merge_enabled False]·`assemble_live_packet_report`[순수]·`build_live_labeling_packet`·`write_live_labeling_packet_jsonl`). `identity_human_labeling`: 옵션 D `SELECTION_BUCKET_HASH`(sha256(pair_id) 정렬) + `_sample_candidate_pairs`/`build_labeling_packet`/`summarize_packet_sampling` 에 `selection_method` 인자(ADR#46 기본 하위호환). docs: ADR#47(`_DECISIONS`)·RISK_REGISTER(R-ReviewerAgreement·R-GoldSamplingBias 부분진전·**R-LiveIdentityBacklog 신규**·R-RealSourceLoopUnproven 연결)·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-ReviewerAgreement **부분진전**(live 백로그 적용·실 합의 0) · R-GoldSamplingBias **부분진전**(옵션 D·실 대표성 0) · **R-LiveIdentityBacklog 신규**(운영 DB 미마이그레이션+단계 ③ 미배선=실 백로그 0) · R-IdentityHumanLabeling·R-IdentityEvalDataset·R-SemanticIdentityAdjudicator·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (live-derived labeling packet pilot — ADR#47)
- **① ADR#46 커밋**: 14파일 → `ac636e7`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석(probe)으로 live_selected=0 원인 3중 확정**: ⓐ 운영 DB `event_intel` **미마이그레이션**(relation 없음) ⓑ 단계 ③ shadow adjudication(`adjudicate_semantic_links`) **live 루프 미배선**(production 호출자 0 — `apply_routing` 은 ①anchor·②fingerprint/link 까지만) ⓒ ADR#46 헤드라인 측정은 synthetic fixture 기반. → 단일 버그 아닌 **백로그 부재**.
- **③ live packet pilot 도구**(옵션 A=live-PG backlog read + 옵션 D=bucket-hash 표집; B[real source loop]=보류·C[synthetic-only]=금지): `collect_live_identity_candidates`(worksheet rows + backlog_stats[total_candidate_links·total_adjudications·eligible·**exclusion_reasons**{semantic_link_without_adjudication·adjudication_event_missing}])·`generate_live_packet_report`(전 필드 + event count before/after·`auto_merge_enabled=False`)·`write_live_labeling_packet_jsonl`(internal artifact). **read-only**(session.add/commit/insert 0).
- **④ 옵션 D bucket-hash 표집**: `SELECTION_BUCKET_HASH`(sha256(pair_id) 정렬·정렬 편향 완화·재현 가능)·ADR#46 기본(`deterministic_pair_id_order_cap`) **하위호환**. over-cap 에서 order≠hash 선택(편향 완화 실재·테스트 입증)·cap 미만 현 규모 효과 nil(정직).
- **⑤ 측정 결과(정직)**: live-PG 실 파이프라인 유래 — semantic link 1+adjudication 1 → eligible 1·**live_selected 1**(synthetic 아님)·selected 1·reviewer item 2·Event 불변(자동 병합 0)·live_deficit>0. adjudication 미실행 시 eligible 0·exclusion `semantic_link_without_adjudication=1`(운영 자동 백로그 0 표면화). 운영 DB 미마이그레이션·실 network fetch 백로그 0.
- **adversarial 평결**: root-cause VALID(production 호출자 0)·no-bias(report dict verdict 키 0)·no-auto-merge/read-only(write 0·event count gard 는 tautology 아님)·옵션 D(over-cap divergence·재현·현 nil 정직) VALID·**어떤 RISK 도 CLOSE 안 함 확인**. MEDIUM 1=R-LiveIdentityBacklog 미등록+ADR#47 결정로그 미기록(critic 이 docs 전 검토 — 본 docs 동기화로 해소). LOW 2 문서화(live 1행=운영 자동 아님·`dataset_source` fail-open).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**live 루프 미배선=test/도구 수동만**) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43) **+ human gold workflow**(ADR#44) **+ reviewer agreement protocol**(ADR#45) **+ labeling packet**(ADR#46) **+ live packet pilot**(ADR#47: live-PG 백로그 read·exclusion 진단·옵션 D 표집).
- **⚠ 미해소(OPEN):** 실 병합 0·실 human-reviewed production gold 0·reviewer 합의 실측 0·sampling 대표성 0·한국어 캘리브레이션·MERGE_GATE 런타임 배선·**live identity 백로그 운영 배선**(운영 DB 마이그레이션+단계 ③ 배선). "도구 코드·1행 E2E ≠ 실 운영 백로그" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=**반응 evidence**(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` 에 live packet pilot gate 추가(read-only DB read·exclusion 진단·옵션 D 표집·live_selected 는 실 파이프라인 유래·운영 자동 백로그 0 표면화·packet 은 gold 아님). final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-ReviewerAgreement**(reviewer 배정/roundtrip 을 live-PG 백로그에 적용 DONE; 실 합의 0; 완전종결 금지).
- **부분진전: R-GoldSamplingBias**(옵션 D bucket-hash·live backlog/exclusion report DONE; 실 충원/대표성 0·효과 over-cap 한정; 완전종결 금지).
- **신규: R-LiveIdentityBacklog**(운영 DB 미마이그레이션+단계 ③ live 미배선=실 백로그 0·probe 확정 blocker; 경계: R-RealSourceLoopUnproven[운영 DB]·R-SemanticIdentityAdjudicator[단계 ③ 실 병합]와 교차 추적·중복 등재 아님).
- **갱신: R-RealSourceLoopUnproven**(운영 DB 미마이그레이션 잔여가 live labeling 백로그를 막음 — 연결 명시).
- **R-LivePacketOps·R-KoreanSemanticCalibration 미등록**(packet 도구=운영 수단·KO=R-IdentityEvalDataset gap — RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 운영 live 백로그**: 운영 DB(event_intel) alembic 마이그레이션 + 단계 ③ adjudication 운영 배선(결정론) 필요 → 도구 DONE·실 백로그 0(R-LiveIdentityBacklog).
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + MERGE_GATE 충족 필요·미구축.
- **실 reviewer 배정/합의 gold**: 다중 reviewer 운영(충원/SLA/adjudication 담당) 필요 → packet/live tool DONE·실 배정/합의 0(R-ReviewerAgreement).
- **sampling 대표성**: live 데이터로 bucket 충원·무작위/층화 표집 필요 → 옵션 D 코드 DONE·실데이터 0·효과 over-cap 한정(R-GoldSamplingBias).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 live 백로그 누적 = 운영 DB 마이그레이션 + 단계 ③ 운영 배선(결정론) 선결(R-LiveIdentityBacklog) — 이번 턴 범위 외(네트워크/배포 의존).
- UNKNOWN: 실 병합 허용 기준(production precision·실 human-labeled gold·reviewer 합의 실측·sampling 대표성·한국어 캘리브레이션·MERGE_GATE 배선) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#47 code 2 + tests 2 + docs 8 (총 12파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** 운영 DB(event_intel) alembic 마이그레이션 + 단계 ③ adjudication 운영/주기 배선(결정론) → 실 cross-source 후보 누적 → live packet pilot 으로 live_selected>0(synthetic/수동 주입 없이) → 다중 reviewer 배정·합의 gold 누적 → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `ac636e7`(ADR#46). 코드: `build_live_identity_labeling_packet.py`(신규)·`identity_human_labeling`(옵션 D).
- 검증: backend 비-live **447p/4s** · live-PG **66p**(live tool 5) · ingestion **1353p** · frontend tsc0/test12/lint0. 신규 17(결정론 12 + live-PG 5). 측정: eligible 1·live_selected 1·selected 1·운영 자동 백로그 0(exclusion 표면화)·event count 불변·auto_merge_enabled False.
- 문서: ADR#47(`_DECISIONS`)·R-ReviewerAgreement+R-GoldSamplingBias 부분진전+R-LiveIdentityBacklog 신규+R-RealSourceLoopUnproven(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#47 live-derived labeling packet pilot. 신규 `build_live_identity_labeling_packet.py`(read-only·DB write 0: `collect_live_identity_candidates`[live-PG backlog→worksheet rows + backlog_stats{total_candidate_links·total_adjudications·eligible·exclusion_reasons[semantic_link_without_adjudication·adjudication_event_missing]}]·`generate_live_packet_report`[event count before/after·auto_merge_enabled False]·`assemble_live_packet_report`[순수]·`build_live_labeling_packet`·`write_live_labeling_packet_jsonl`)·`identity_human_labeling` 옵션 D(`SELECTION_BUCKET_HASH`=sha256(pair_id) 정렬·정렬 편향 완화·재현·ADR#46 기본 `SELECTION_PAIR_ID_ORDER` 하위호환). **측정(정직): live-PG 실 파이프라인 유래 eligible 1·live_selected 1·selected 1·reviewer item 2·Event 불변·운영 자동 백로그 0(단계 ③ 미배선·운영 DB 미마이그레이션→exclusion semantic_link_without_adjudication 표면화)·over-cap order≠hash divergence 입증**. 옵션 A(live backlog read)+D(bucket-hash) 채택·B(real source loop)=보류·C(synthetic-only)=금지. adversarial JUSTIFIED(root-cause·no-bias·no-auto-merge·read-only·옵션 D·어떤 RISK 도 CLOSE 안 함)·MEDIUM 1=R-LiveIdentityBacklog 미등록+ADR#47 결정로그 미기록(docs 동기화로 해소)·LOW 2 문서화. **R-ReviewerAgreement·R-GoldSamplingBias 부분진전·R-LiveIdentityBacklog 신규**·완전종결=OVERCLAIM·R-LivePacketOps/R-KoreanSemanticCalibration 미등록(RISK 남발 금지). **backend 비-live 447p/4s · live-PG 66p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#46 커밋 `ac636e7` 위 ADR#47 미커밋(code 2+tests 2+docs 8=12파일)·커밋 지시 대기·push 안 함._
