# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "정답(gold) 데이터"의 신뢰를 한 단계 끌어올렸습니다 — 한 사람의 라벨을 곧장 정답으로 쓰던 것을, **여러 검수자의 합의(또는 사람 책임자의 판정)** 가 있어야 정답으로 인정하는 운영 절차(protocol)로 바꿨습니다. **검수자가 갈리면(conflict) 자동으로 정답이 되지 않고**, **한 명만 본 건 임시(provisional)** 이며, **기계/LLM이 단 라벨은 정답으로 못 들어옵니다.** 자동 병합은 여전히 OFF입니다.
- **이번 턴에 실제로 끝낸 것:** ADR#44 커밋(`56a2c83`) → **ADR#45 구현**: `identity_human_labeling.py` 확장(reviewer 합의·conflict 격리·sampling 대표성 추적·**표본 수의 통계적 근거** 추정) + `identity_reviewer_labels.sample.jsonl`(16행 **시연용**). 측정: **backend 비-live 408p/4s · live-PG 56p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial **JUSTIFIED·MEDIUM 2 수정·BUG 0**.
- **정직한 한계:** 이번 턴은 **운영 절차(코드)를 만든 것**이지 **실제 검수자가 합의한 운영 정답·합의 실측·SLA는 0**입니다(샘플은 시연용). reviewer 합의 gold라도 현재 판정기 precision 0.5(병합 기준 0.98 미달). 실 병합·중복 사건 감소는 여전히 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `56a2c83`**(ADR#44, 본 턴 첫 커밋) 위 **ADR#45 = 미커밋 code 1(`identity_human_labeling.py` 확장) + fixture 1(신규 `identity_reviewer_labels.sample.jsonl`) + tests 2(신규 `test_identity_reviewer_agreement.py` + `test_event_resolution_live_pg`(+reviewer 4)) + docs 8**. **migration 없음**(JSONL).
- code: `identity_human_labeling` 확장(신규: ReviewerLabel·load_reviewer_labels[model/self label 거부]·compute_reviewer_agreement·resolve_gold_from_reviewers[conflict 자동 gold 금지·`_validate_adjudication` LLM-as-judge 차단]·resolved_to_gold_pairs·assign/summarize_sampling_buckets·estimate_sample_floor_for_precision/fpr·generate_labeling_protocol_report). `identity_eval_dataset`·`export`·ADR#44 gold workflow **무변경**(append). docs: ADR#45(`_DECISIONS`)·RISK_REGISTER(R-IdentityHumanLabeling 부분진전·R-ReviewerAgreement·R-GoldSamplingBias 신규·R-IdentityEvalDataset floor 통계)·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-IdentityHumanLabeling **protocol 부분진전**(실 gold/agreement 0) · **R-ReviewerAgreement 신규** · **R-GoldSamplingBias 신규** · R-IdentityEvalDataset·R-SemanticIdentityAdjudicator·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (reviewer agreement protocol — ADR#45)
- **① ADR#44 커밋**: 12파일 → `56a2c83`(secret PASS·docs_lifecycle 0·closeout 검증 후, push 0).
- **② reviewer agreement protocol**(옵션 A=JSONL+agreement, B[DB queue]=future·C[LLM/self pseudo-gold]=금지): `ReviewerLabel`(reviewer_id·review_round·**reviewer_kind[human only]**)·`load_reviewer_labels`(model/self/llm/adjudicator label 거부·중복 거부·PII 차단)·`resolve_gold_from_reviewers`(1명=insufficient·2+전원합의=agreed·불일치+사람 adjudication=adjudicated·**불일치=conflict[자동 gold 금지]**·최신 round 적용).
- **③ sampling 대표성 + 통계적 표본 floor**: `assign_sampling_bucket`(12 bucket·미분류 경고·insufficient 라우팅)·`estimate_sample_floor_for_precision/fpr`(normal-approx: precision 0.98±0.02→**189**·FPR 0.01±0.01→**381**) → 기존 200/50 draft 가 placeholder 임을 정량화(KO 50 낙관적 명시)·`generate_labeling_protocol_report`.
- **④ 측정 결과(정직)**: sample reviewer(16 label·8 pair) agreement_rate **0.71**(5 agreed/7 multi)·conflict 1·insufficient 1·adjudicated 1. resolved gold(6) precision **0.5**·merge readiness **False**·`auto_merge_enabled=False`(불변).
- **adversarial 평결(동일 critic)**: safety(DB write 0·자동 병합 0·conflict→gold 누출 0·model label 거부·PII 차단·agreement 계산 정확·2:1→conflict[만장일치만 gold]) **JUSTIFIED·BUG 0**. **수정 MEDIUM 2**: ① adjudication 경로 LLM-as-judge 뒷문(`_validate_adjudication` fail-loud 추가) ② insufficient bucket 커버리지 공백(insufficient_generic 라우팅).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43 harness) **+ human gold workflow**(ADR#44) **+ reviewer agreement protocol**(ADR#45: 다중 합의=gold·conflict 자동 gold 금지·LLM adjudicator 차단·sampling·통계 floor).
- **⚠ 미해소(OPEN):** 실 병합 0·실 human-reviewed production gold 0·**reviewer 합의 실측 0**·sampling 대표성 실데이터 0·한국어 캘리브레이션·MERGE_GATE 런타임 배선. "protocol 코드 ≠ 실 gold/agreement" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=**반응 evidence**(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` 에 reviewer agreement protocol gate 추가(gold 신뢰=다중 합의/사람 adjudication·LLM-as-judge 금지·실 합의/대표 표본 전까지 ④ 금지). final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **protocol 부분진전: R-IdentityHumanLabeling**(reviewer agreement protocol·conflict no-auto-gold·sampling·floor 추정 DONE; 실 gold/agreement/SLA OPEN; 완전종결=OVERCLAIM).
- **신규 등록: R-ReviewerAgreement**(MEDIUM, OPEN) — 다중 reviewer 합의 실측·kappa·운영 절차 0.
- **신규 등록: R-GoldSamplingBias**(MEDIUM, OPEN) — gold sampling 대표성·oversampling 실데이터 0.
- **갱신: R-IdentityEvalDataset**(표본 floor 통계 추정 부분진전·실 gold OPEN).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + MERGE_GATE 충족 필요·미구축.
- **실 reviewer 합의 gold**: 다중 reviewer 운영(충원/SLA/adjudication 담당) 필요 → protocol 코드 ADR#45 DONE·실 합의 0(R-ReviewerAgreement).
- **sampling 대표성**: live 데이터로 bucket 충원·hard-negative/KO oversample 필요 → bucket 코드 DONE·실데이터 0(R-GoldSamplingBias).
- **한국어 실 캘리브레이션**: 측정만·어절 임계 교정 미이행.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: 실 병합 허용 기준(production precision·실 human-labeled gold·reviewer 합의 실측·sampling 대표성·한국어 캘리브레이션·MERGE_GATE 배선) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#45 code 1 + fixture 1 + tests 2 + docs 8 (총 12파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** 실 live-derived 후보의 다중 reviewer 검수 운영(충원/SLA/adjudication 담당) + 실 합의 gold 누적 → sampling bucket 충원(hard-negative/KO oversample) → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `56a2c83`(ADR#44). 코드: `identity_human_labeling`(확장)·`identity_reviewer_labels.sample.jsonl`(신규).
- 검증: backend 비-live **408p/4s** · live-PG **56p**(reviewer 4) · ingestion **1353p** · frontend tsc0/test12/lint0. 측정: sample reviewer agreement 0.71·resolved gold precision 0.5·merge readiness False·floor 추정 189/381.
- 문서: ADR#45(`_DECISIONS`)·R-IdentityHumanLabeling 부분진전+R-ReviewerAgreement+R-GoldSamplingBias 신규(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#45 production labeling protocol — reviewer agreement + sampling + 통계적 sample-floor. `identity_human_labeling.py` 확장(ReviewerLabel[reviewer_kind human only]·load_reviewer_labels[model/self label 거부·중복·PII 차단]·compute_reviewer_agreement·resolve_gold_from_reviewers[1명=insufficient·전원합의=agreed·불일치+사람 adjudication=adjudicated·**불일치=conflict 자동 gold 금지**·`_validate_adjudication` LLM-as-judge 차단·최신 round]·resolved_to_gold_pairs[agreed/adjudicated만]·assign/summarize_sampling_buckets[12 bucket·미분류 경고]·estimate_sample_floor_for_precision/fpr[normal-approx 189/381]·generate_labeling_protocol_report)·`fixtures/identity_reviewer_labels.sample.jsonl`(16행 시연). `identity_eval_dataset`·`export`·ADR#44 gold workflow 무변경(append). **측정(정직): sample reviewer agreement 0.71·conflict 1·insufficient 1·adjudicated 1·resolved gold precision 0.5·merge readiness False·auto_merge_enabled=False**. 옵션 A(JSONL+agreement) 채택·B(DB queue)=future·C(LLM/self pseudo-gold)=금지. adversarial JUSTIFIED(safety·conflict no-auto-gold·model label 거부·agreement 정확)·**MEDIUM 2 수정**(adjudication LLM 뒷문·insufficient bucket 공백)·**BUG 0**. **R-IdentityHumanLabeling protocol 부분진전·R-ReviewerAgreement·R-GoldSamplingBias 신규·R-IdentityEvalDataset floor 통계 부분진전**·완전종결=OVERCLAIM. **backend 비-live 408p/4s · live-PG 56p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#44 커밋 `56a2c83` 위 ADR#45 미커밋(code 1+fixture 1+tests 2+docs 8=12파일)·커밋 지시 대기·push 안 함._
