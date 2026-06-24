# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "같은 사건 판정기"를 미래에 **자동으로 합치게 허락하기 전 마지막 안전장치** — "사람이 직접 검수한 정답(gold) 데이터"를 만들고 채점하는 **작업 흐름(workflow)**을 구축했습니다. 기계가 뽑은 후보를 사람이 "같은 사건/다른 사건/모호/판단불가"로 라벨링해 정답으로 승격하고, 그 정답으로만 판정기를 채점합니다. **기계가 스스로 단 라벨(self-label)은 정답으로 인정하지 않습니다.** 자동 병합은 여전히 OFF입니다.
- **이번 턴에 실제로 끝낸 것:** ADR#43 커밋(`830d918`) → **ADR#44 구현**: `identity_human_labeling.py`(gold schema+provenance+승격+gold 전용 채점+병합준비도) + `identity_gold_pairs.sample.jsonl`(13행 **시연용** 샘플). 측정: **backend 비-live 378p/4s · live-PG 52p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial 수동 전수 재현 **JUSTIFIED·BUG 0**.
- **정직한 한계:** 이번 턴은 **작업 흐름(코드)을 만든 것**이지 **실제 사람이 검수한 운영 정답 데이터는 0**입니다(샘플은 제가 손으로 만든 시연용). 검수 담당/절차/합의도 없습니다. sample gold precision 0.6(병합 기준 0.98 미달)·한국어 0.5 — 자동 병합 기준 미달이 또 데이터로 확인됐습니다. 실 병합·중복 사건 감소는 여전히 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `830d918`**(ADR#43, 본 턴 첫 커밋) 위 **ADR#44 = 미커밋 code 1(신규 `identity_human_labeling.py`) + fixture 1(신규 `identity_gold_pairs.sample.jsonl`) + tests 2(신규 `test_identity_human_labeling.py` + `test_event_resolution_live_pg`(+gold 3)) + docs 8**. **migration 없음**(JSONL 기반).
- code: `identity_human_labeling(신규: GoldPair·load_gold_pairs·promote_worksheet_to_gold·evaluate_adjudicator_on_gold·generate_gold_eval_report·compare_fixture_vs_gold_metrics·summarize_labeling_backlog·evaluate_gold_merge_readiness)`. `identity_eval_dataset`·`export_identity_eval_pairs`는 **무변경**(import만 — ADR#43 회귀 0). docs: ADR#44(`_DECISIONS`)·RISK_REGISTER(R-IdentityHumanLabeling 부분종결·R-IdentityEvalDataset gold loader 부분진전·R-SemanticIdentityAdjudicator gap④)·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-IdentityHumanLabeling **workflow 부분종결**(open: 실 production gold 0) · R-IdentityEvalDataset **gold loader 부분진전**(open) · R-SemanticIdentityAdjudicator·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (human-labeled gold workflow — ADR#44)
- **① ADR#43 커밋**: 14파일 → `830d918`(secret PASS·docs_lifecycle 0·closeout 검증 후, push 0).
- **② gold workflow**(옵션 A=JSONL roundtrip, B[DB queue]=future·C[LLM self-label]=금지): 신규 `identity_human_labeling.py` — `GoldPair`(EvalPair + provenance reviewed_by/reviewed_at/review_status/label_confidence + `dataset_source` synthetic|live 분리자)·`load_gold_pairs`(provenance 필수·enum·reviewed_at ISO·중복·**raw body/PII/워크시트 보조키 차단**)·`promote_worksheet_to_gold`(보조키 제거·**사람이 label 강제=self-label 금지**)·`evaluate_adjudicator_on_gold`(review_status='gold'만; needs_review/rejected 제외).
- **③ gold metric harness**: `generate_gold_eval_report`(gold_precision/fpr/recall/coverage/hard-neg + by_language/source_type/risk_tag + backlog + readiness)·`compare_fixture_vs_gold_metrics`(fixture·gold **따로** 평가·delta)·`summarize_labeling_backlog`(labeled_gold/needs_review/rejected)·`evaluate_gold_merge_readiness`(**live_derived gold만** MERGE_GATE + 표본 floor·`auto_merge_enabled=False` 불변).
- **④ 측정 결과(정직)**: sample gold(review_status=gold 11행·synthetic 포함) precision **0.6**·FPR **0.33**·recall **0.6**·hard-neg FP **2**·KO precision **0.5**. merge readiness=**live_derived gold(10행)만** → precision **0.5**·표본 floor(live 200/KO 50) **미달** → `merge_ready=False`·자동 병합 OFF. synthetic 은 readiness precision/표본 어느 쪽도 부풀리지 못함(분리 입증).
- **adversarial 평결(동일 critic)**: safety(events/updates/map write 0·자동 병합 경로 0·`auto_merge_enabled` 하드코딩 False)·provenance(self-label 금지·predicted_status 제거)·PII 차단·**metric 11행 토큰화 수동 전수 재현 일치**·오라벨 0·정직 표기 **JUSTIFIED·BUG 0**. 잔여 2(비차단·정직 표기): **MEDIUM**(실 human gold 0→dead-data 미해소·부분종결만)·**LOW**(표본 floor 200/50=draft placeholder).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40·실 병합) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43 harness: 진단 precision 0.57) **+ human-labeled gold workflow**(ADR#44: gold 승격·gold-only metric·readiness — sample precision 0.6·KO 0.5·**merge gate 미달**).
- **⚠ 미해소(OPEN):** 실 병합 0(중복 count 미감소)·**실 human-reviewed production gold set 0**(샘플은 시연)·SLA/reviewer agreement 0·한국어 실 캘리브레이션·MERGE_GATE 런타임 배선·표본 floor 재유도. "workflow 코드 ≠ 실 gold" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=**반응 evidence**(반응량/논쟁/대표질문/기대·불만/분위기/루머·확인 — merge anchor 불가)·market=signal·catalog=entity enrichment·search=URL 후보·unknown=fail-closed.
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` 에 human-labeled gold workflow gate 추가(gold=사람 검수 label·self-label/LLM-label 금지·실 production gold 전까지 ④ 병합 금지). §3 community reaction layer 정제 차원 명문화. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **workflow 부분종결: R-IdentityHumanLabeling**(승격 workflow 코드·schema·provenance·라운드트립·sample DONE; **실 human-reviewed production gold·SLA·reviewer agreement·주기 루프 OPEN** — 완전종결=OVERCLAIM).
- **gold loader 부분진전: R-IdentityEvalDataset**(gold loader/evaluator·fixture vs gold 분리·readiness 산출 DONE; production 규모·한국어 캘리브레이션·표본 floor 재유도·MERGE_GATE 배선 OPEN).
- **갱신: R-SemanticIdentityAdjudicator**(gap④ 평가셋 부분 해소[ADR#43+#44]·①②③ 진전 0·실 병합 미입증·OPEN).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + MERGE_GATE 충족 필요·미구축.
- **실 human-reviewed production gold set**: human labeling 운영(담당/SLA/reviewer agreement) 필요 → workflow 코드는 ADR#44 DONE·실 라벨 0(R-IdentityHumanLabeling).
- **한국어 실 캘리브레이션**: 측정(KO precision gold 0.5·진단 0.67)만·stopword 영어전용·어절 임계 교정 미이행.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: 실 병합 허용 기준(production precision·실 human-labeled gold·한국어 캘리브레이션·MERGE_GATE 배선·표본 floor 통계 재유도) → R-IdentityEvalDataset·R-IdentityHumanLabeling 선결. fragment-strip same-URL 모니터링(ADR#40 잔여).

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#44 code 1 + fixture 1 + tests 2 + docs 8 (총 12파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** 실 live-derived candidate 의 human labeling 운영(담당/SLA/reviewer agreement) + 실 gold 누적 → 표본 floor 통계 재유도 → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `830d918`(ADR#43). 코드: `identity_human_labeling`(신규)·`identity_gold_pairs.sample.jsonl`(신규).
- 검증: backend 비-live **378p/4s** · live-PG **52p**(gold 3) · ingestion **1353p** · frontend tsc0/test12/lint0. 측정: sample gold precision 0.6·FPR 0.33·KO 0.5·hard-neg FP 2(merge gate 미달·readiness False).
- 문서: ADR#44(`_DECISIONS`)·R-IdentityHumanLabeling 부분종결+R-IdentityEvalDataset gold loader 부분진전(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4·§3`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#44 human-labeled gold workflow + gold metric harness — 신규 `identity_human_labeling.py`(GoldPair[provenance reviewed_by/reviewed_at/review_status/label_confidence + dataset_source synthetic|live 분리자]·`load_gold_pairs`[provenance 필수·enum·reviewed_at ISO·raw body/PII/보조키 차단]·`promote_worksheet_to_gold`[보조키 제거·self-label 금지]·`evaluate_adjudicator_on_gold`[gold만]·`generate_gold_eval_report`·`compare_fixture_vs_gold_metrics`·`evaluate_gold_merge_readiness`[live gold만·표본 floor·auto-merge OFF])·`fixtures/identity_gold_pairs.sample.jsonl`(13행 **시연 샘플**·운영 gold 아님). `identity_eval_dataset`·`export_identity_eval_pairs` **무변경**. **측정(정직): sample gold precision 0.6·FPR 0.33·hard-neg FP 2·KO 0.5·merge readiness False·auto_merge_enabled=False**. 옵션 A(JSONL roundtrip) 채택·B(DB queue)=future·C(LLM self-label)=금지. adversarial JUSTIFIED(safety·provenance·PII·metric 수동 재현 일치·오라벨 0·**BUG 0**)·정직 잔여(실 production gold 0=부분종결·표본 floor draft). **R-IdentityHumanLabeling workflow 부분종결·R-IdentityEvalDataset gold loader 부분진전·R-SemanticIdentityAdjudicator gap④ 진전·OPEN 유지**·완전종결=OVERCLAIM. **backend 비-live 378p/4s · live-PG 52p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#43 커밋 `830d918` 위 ADR#44 미커밋(code 1+fixture 1+tests 2+docs 8=12파일)·커밋 지시 대기·push 안 함._
