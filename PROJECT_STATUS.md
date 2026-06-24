# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "정답(gold) 데이터"를 **실제로 검수자에게 배정 가능한 작업지(labeling packet)** 로 만드는 운영 도구를 추가했습니다 — 라이브 후보를 종류별(bucket)로 골라, **같은 건을 최소 2명에게 배정**하고, **모델이 추정한 정답(predicted_status)을 검수자에게 숨겨(편향 차단)** 작업지를 만듭니다. 검수자가 갈리면(conflict) **사람 책임자에게 가는 별도 큐**로 보내고, 자동으로 정답이 되지 않습니다. 자동 병합은 여전히 OFF입니다.
- **이번 턴에 실제로 끝낸 것:** ADR#45 커밋(`9db15cf`) → **ADR#46 구현**: `identity_human_labeling.py` 확장(labeling packet 생성·bucket 샘플링·reviewer 배정·predicted_status 차폐·sampling deficit/표본 floor report·conflict 큐) + `identity_labeling_candidates.sample.jsonl`(16행 **시연용**). 측정: **backend 비-live 435p/4s · live-PG 61p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial **JUSTIFIED·HIGH 1 수정·MEDIUM 2 보완**.
- **정직한 한계:** 이번 턴은 **검수 운영 도구(scaffold)** 를 만든 것이지 **실제 검수자 배정·합의·대표 표본은 0**입니다(샘플은 시연용). 후보 선택도 무작위가 아니라 정렬 cut-off라 대표성은 미입증입니다. 실 병합·중복 사건 감소는 여전히 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `9db15cf`**(ADR#45, 본 턴 첫 커밋) 위 **ADR#46 = 미커밋 code 2(`identity_human_labeling.py` 확장 + `export_identity_eval_pairs.py` signal→market 정규화) + fixture 1(신규 `identity_labeling_candidates.sample.jsonl`) + tests 3(신규 `test_identity_labeling_packet.py` + `test_identity_eval_dataset`(+1) + `test_event_resolution_live_pg`(+packet 5)) + docs 8**. **migration 없음**(JSONL).
- code: `identity_human_labeling` 확장(신규: assign_candidate_bucket[15 bucket]·build_labeling_packet[reviewer ≥2 배정·predicted_status 차폐]·validate_labeling_packet[verdict 누출·PII fail-loud]·labeler_facing_view·summarize_packet_sampling[deficit/oversample·floor 대조·selection_method]·adjudication_queue_from_resolved[conflict→human-only]·generate_packet_ops_report). `export_identity_eval_pairs._to_eval_source_type`(adversarial HIGH 수정). ADR#44/#45 무변경(append). docs: ADR#46(`_DECISIONS`)·RISK_REGISTER(R-ReviewerAgreement·R-GoldSamplingBias packet 부분진전·R-IdentityHumanLabeling)·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-ReviewerAgreement **packet scaffold 부분진전**(실 합의 0) · R-GoldSamplingBias **packet sampling 부분진전**(실 충원/대표성 0) · R-IdentityHumanLabeling(protocol+packet 부분진전·실 gold 0) · R-IdentityEvalDataset·R-SemanticIdentityAdjudicator·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (live-derived labeling packet — ADR#46)
- **① ADR#45 커밋**: 12파일 → `9db15cf`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② labeling packet generator**(옵션 A=JSONL packet, B[DB queue]=future·C[synthetic-only]=금지): `build_labeling_packet`(live 워크시트→bucket 샘플링→**동일 pair distinct ≥2명 배정**→`predicted_status/score/reason/label` **구조적 차폐**=bias 0)·`validate_labeling_packet`(verdict 누출·raw body/PII·enum·중복 fail-loud)·`labeler_facing_view`(bucket+판정 제거 — labeler 가 보는 view)·`write_labeling_packet_jsonl`(internal-only artifact).
- **③ candidate bucket 샘플링 + 표본 floor 대조**: `assign_candidate_bucket`(라벨 전 15 bucket·가드 우선·*_predicted/*_guard)·`summarize_packet_sampling`(selected/deficit/oversampled/underfilled·by_language/source_type·live_vs_synthetic·표본 floor 대조[189/381]·hard_negative/ambiguous/KO **oversample target**·`selection_method='deterministic_pair_id_order_cap'`)·`adjudication_queue_from_resolved`(conflict만·label 미탑재·human adjudicator only).
- **④ 측정 결과(정직)**: sample candidate(16행·15 bucket) selected 16·packet item 32(2 reviewer)·unclassified 0·**live_selected 0**(synthetic 은 live floor 미부풀림)·floor deficit positive 189-1·negative 381-0(전부 floor 미달 정직 노출)·gold_resolved 0(라벨 전)·auto_merged 0.
- **adversarial 평결(동일 critic)**: no-bias(verdict 구조적 미포함·labeler_view bucket 제거)·no-auto-merge(events write 0·live Event 불변)·sampling 정직(deficit 숫자·synthetic 미부풀림·build↔report drift 0)·distinct reviewer(수학적 보장)·conflict→human-only **JUSTIFIED**. **수정 HIGH 1**: evidence 'signal' vs eval 'market' 불일치(라이브 market 후보 packet 진입 불가) → `_to_eval_source_type` export 정규화 + 회귀 테스트. **보완 MEDIUM 2**: bucket 미노출=운영 약속(docstring 경고)·sampling=결정론 정렬 cut-off(`selection_method` 명시).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43) **+ human gold workflow**(ADR#44) **+ reviewer agreement protocol**(ADR#45) **+ live-derived labeling packet**(ADR#46: bucket 샘플링·reviewer 배정·predicted_status 차폐·conflict 큐·표본 floor 대조).
- **⚠ 미해소(OPEN):** 실 병합 0·실 human-reviewed production gold 0·**reviewer 배정/합의 실측 0**·sampling 대표성 실데이터 0(selection=정렬 cut-off)·한국어 캘리브레이션·MERGE_GATE 런타임 배선. "packet scaffold ≠ 실 gold/agreement" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=**반응 evidence**(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` 에 labeling packet gate 추가(reviewer 검수 scaffold·model 판정/bucket 차폐=bias 0·community/market/catalog=guard bucket[merge anchor 아님]·labeler 에게 `labeler_facing_view` 만·packet 은 gold 입력 도구일 뿐 gold 아님). final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **packet scaffold 부분진전: R-ReviewerAgreement**(reviewer 배정 packet·conflict→adjudication 큐·roundtrip DONE; 실 합의 데이터 0; 완전종결 금지).
- **packet sampling 부분진전: R-GoldSamplingBias**(candidate bucket 샘플링·deficit/oversample/floor 대조 DONE; 실 충원/대표성 0·selection=정렬 cut-off; 완전종결 금지).
- **갱신: R-IdentityHumanLabeling**(packet 운영 scaffold 부분진전·실 gold 0).
- **R-LabelingPacketOps 미등록**(packet 은 위 두 RISK 의 운영 도구·별도 blocker 아님 — RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + MERGE_GATE 충족 필요·미구축.
- **실 reviewer 배정/합의 gold**: 다중 reviewer 운영(충원/SLA/adjudication 담당) 필요 → packet scaffold ADR#46 DONE·실 배정/합의 0(R-ReviewerAgreement).
- **sampling 대표성**: live 데이터로 bucket 충원·무작위/층화 표집 필요 → bucket/packet 코드 DONE·실데이터 0·selection=정렬 cut-off(R-GoldSamplingBias).
- **한국어 실 캘리브레이션**: 측정만·어절 임계 교정 미이행.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: 실 병합 허용 기준(production precision·실 human-labeled gold·reviewer 합의 실측·sampling 대표성·한국어 캘리브레이션·MERGE_GATE 배선) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#46 code 2 + fixture 1 + tests 3 + docs 8 (총 14파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** 실 live-derived 후보의 다중 reviewer 배정·검수 운영(충원/SLA/adjudication 담당) + 실 합의 gold 누적 → sampling bucket 충원(hard-negative/KO oversample·무작위/층화 표집) → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `9db15cf`(ADR#45). 코드: `identity_human_labeling`(확장)·`export_identity_eval_pairs`(signal→market)·`identity_labeling_candidates.sample.jsonl`(신규).
- 검증: backend 비-live **435p/4s** · live-PG **61p**(packet 5) · ingestion **1353p** · frontend tsc0/test12/lint0. 측정: selected 16·packet item 32·live_selected 0·gold_resolved 0·floor 189/381 deficit 정직 노출.
- 문서: ADR#46(`_DECISIONS`)·R-ReviewerAgreement+R-GoldSamplingBias packet 부분진전+R-IdentityHumanLabeling(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#46 live-derived labeling packet + sampling operationalization. `identity_human_labeling.py` 확장(assign_candidate_bucket[15 candidate bucket·가드 우선]·build_labeling_packet[bucket 샘플링·동일 pair distinct ≥2명 배정·**predicted_status/score/reason/label 구조적 차폐**=bias 0]·validate_labeling_packet[verdict 누출·raw body/PII·enum·중복 fail-loud]·labeler_facing_view[bucket+판정 제거]·write_labeling_packet_jsonl[internal-only]·summarize_packet_sampling[selected/deficit/oversampled/underfilled·live_vs_synthetic·표본 floor 대조 189/381·`selection_method=deterministic_pair_id_order_cap`]·adjudication_queue_from_resolved[conflict→human-only·label 미탑재]·generate_packet_ops_report)·`export_identity_eval_pairs._to_eval_source_type`(evidence 'signal'→eval 'market' 정규화)·`fixtures/identity_labeling_candidates.sample.jsonl`(16행·15 bucket 시연). ADR#44/#45 gold workflow 무변경(append). **측정(정직): selected 16·packet item 32·unclassified 0·live_selected 0(synthetic 미부풀림)·gold_resolved 0(라벨 전)·auto_merged 0·floor deficit positive 189-1·negative 381-0**. 옵션 A(JSONL packet) 채택·B(DB queue)=future·C(synthetic-only)=금지. adversarial JUSTIFIED(no-bias·no-auto-merge·no-auto-gold·distinct reviewer·conflict→human-only)·**HIGH 1 수정**(signal→market enum 불일치=라이브 market 후보 packet 진입 불가)·**MEDIUM 2 보완**(bucket 미노출=운영 약속·sampling=정렬 cut-off). **R-ReviewerAgreement·R-GoldSamplingBias packet scaffold 부분진전·R-IdentityHumanLabeling 부분진전**·완전종결=OVERCLAIM·R-LabelingPacketOps 미등록(RISK 남발 금지). **backend 비-live 435p/4s · live-PG 61p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#45 커밋 `9db15cf` 위 ADR#46 미커밋(code 2+fixture 1+tests 3+docs 8=14파일)·커밋 지시 대기·push 안 함._
