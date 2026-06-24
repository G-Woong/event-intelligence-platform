# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** "같은 사건 판정기"가 **실제로 믿을 만한지 숫자로 재는 평가 기반**을 만들었습니다. 정답이 붙은 비교쌍(같은사건/다른사건/모호/판단불가)을 만들어 현재 판정기를 채점했더니 — **정밀도 0.57 (병합 허용 기준 0.98에 한참 미달)**. 즉 "아직 자동으로 합치면 안 된다"는 걸 **데이터로 증명**했습니다. 자동 병합은 여전히 OFF입니다.
- **이번 턴에 실제로 끝낸 것:** ADR#42 커밋(`f0a7de9`) → **ADR#43 구현**: `identity_eval_dataset.py`(평가 harness) + `fixtures/identity_eval_pairs.jsonl`(정답 22쌍·4사분면·한/영/혼합) + `export_identity_eval_pairs.py`(판정 테이블→라벨링 워크시트 소비처). 측정: **backend 비-live 348p/4s · live-PG 49p · ingestion 1353p · frontend tsc0/test12/lint0**.
- **정직한 한계:** precision 0.57은 **진단(스트레스) 세트 수치**지 운영 정밀도가 아닙니다(표본 22쌍·대표성 없음). **사람이 라벨링한 실데이터 gold set이 0**이고, 워크시트→gold 승격 **workflow도 없습니다**(→R-IdentityHumanLabeling 신규). 한국어는 **측정만** 했지 임계 캘리브레이션은 미이행. 실 병합은 여전히 0(중복 사건 미감소). push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `f0a7de9`**(ADR#42, 본 턴 첫 커밋) 위 **ADR#43 = 미커밋 code 2 + fixture 1 + tests 3 + docs 8(신규 파일 5: identity_eval_dataset·export_identity_eval_pairs·identity_eval_pairs.jsonl·test_identity_eval_dataset·test_semantic_identity_eval_metrics)**. **migration 없음**(JSONL 기반).
- code: `identity_eval_dataset(신규: EvalPair/load/predict/evaluate/MERGE_GATE)`·`export_identity_eval_pairs(신규: collect/write/summarize 소비처)`. fixture: `identity_eval_pairs.jsonl`(22 pair). tests: 신규 `test_identity_eval_dataset`·`test_semantic_identity_eval_metrics` + `test_event_resolution_live_pg`(+export 4). docs: ADR#43·RISK_REGISTER(R-IdentityEvalDataset 갱신·R-IdentityHumanLabeling 신규·R-SemanticIdentityAdjudicator closure)·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: R-IdentityEvalDataset **harness 부분 진전 유지**(open) · **R-IdentityHumanLabeling 신규**(open) · R-SemanticIdentityAdjudicator·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (identity eval harness — ADR#43)
- **① ADR#42 커밋**: 15파일 → `f0a7de9`(secret PASS·docs_lifecycle 0·closeout 검증 후, push 0).
- **② eval harness**(옵션 A+B, C[LLM self-labeling] 거부): `identity_eval_dataset.py` 가 labeled observation-pair JSONL(allowlist 키만=raw body/PII 구조적 차단·중복/enum/전문 차단)을 로드해 현재 adjudicator 를 적용·`evaluate_adjudicator`=precision/FPR/recall/coverage + by_language/source_type/risk_tag·hard-neg FP·MERGE_GATE 보고. fixture 22 pair(**진단 stress 세트**·4사분면 TP/TN/FP/FN·KO/EN/mixed).
- **③ 측정 결과(정직)**: precision **0.57**·FPR **0.2**·hard-neg FP **3**·recall **0.57**·KO precision 0.67 → **merge gate(precision≥0.98) 미달**·`auto_merge_enabled=False`(불변). 템플릿 충돌=FP·패러프레이즈/번역=FN 정직 노출 → **결정론 adjudicator auto-merge 미달 증명**.
- **④ adjudication 소비처**(dead-data 완화): `export_identity_eval_pairs.py` 가 `event_identity_adjudication`→human-labeling 워크시트 JSONL(internal·no PII). **자동 병합 0·API 미노출**.
- **adversarial 평결**: safety(병합 0·PII 차단·정직 미달 보고·metric 정확) **JUSTIFIED**. **수정 BUG 2**: ① export 언어 enum 불일치(latin→en 정규화+라운드트립 테스트) ② `fn_ko_paraphrase` gold 오류(동결 vs 인상 상호배타→같은방향 인상 paraphrase 교정). **정직 잔여**: dead-data=한 단계 미룸(human labeling 부재)·한국어=측정만·fixture=진단치(운영 아님)·MERGE_GATE=장식(미배선).

## 🧭 cross-batch identity 4단계 + 평가 gate (정직)
- ① anchor 병합(ADR#40·실 병합) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43: precision≥0.98·FPR≤0.01 — **현재 0.57 미달**).
- **⚠ 미해소(OPEN):** 실 병합 0(중복 count 미감소)·live-derived+human-labeled gold set 0·한국어 실 캘리브레이션·MERGE_GATE 런타임 배선. "harness 구축 ≠ gold set 충족" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응·market=signal·catalog=entity enrichment·search=URL 후보·unknown=fail-closed. eval fixture 도 community/market/catalog/unknown pair=insufficient(merge anchor 불가).
- **제품 계약(raw≠public)**: `INTELLIGENCE_UNIT_CONTRACT.md §4` identity evaluation gate 추가(④ 실 병합 전 precision/FPR 선결). raw source 직노출 금지·Event=substrate·public=Intelligence Unit(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **harness 부분 진전: R-IdentityEvalDataset**(eval 도구·측정 DONE·gold set OPEN: live-derived/human-labeled/규모/한국어 캘리브레이션/MERGE_GATE 배선 미달; 완전종결=OVERCLAIM).
- **신규 등록: R-IdentityHumanLabeling**(MEDIUM, OPEN) — 워크시트→gold 승격 workflow 부재.
- **갱신: R-SemanticIdentityAdjudicator**(gap④ 평가셋만 부분 진전·①②③ 진전 0·실 병합 미입증·OPEN·closure 에 MERGE_GATE 런타임 배선 추가).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 병합(중복 count 감소)**: embedding/LLM/KG adjudicator + MERGE_GATE 충족 필요·미구축.
- **production gold set**: live-derived + human-labeled·통계 규모 필요 → human labeling workflow(R-IdentityHumanLabeling).
- **한국어 실 캘리브레이션**: 측정(KO precision 0.67)만·stopword 영어전용·어절 임계 교정 미이행.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- UNKNOWN: 실 병합 허용 기준(production precision·human-labeled gold·한국어 캘리브레이션·MERGE_GATE 배선) → R-IdentityEvalDataset·R-IdentityHumanLabeling 선결. fragment-strip same-URL 모니터링(ADR#40 잔여).

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#43 code 2 + fixture 1 + tests 3 + docs 8 (총 14파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** R-IdentityHumanLabeling(워크시트→gold 라벨링 workflow) + live-derived gold set → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `f0a7de9`(ADR#42). 코드: `identity_eval_dataset`·`export_identity_eval_pairs`·`identity_eval_pairs.jsonl`.
- 검증: backend 비-live **348p/4s** · live-PG **49p**(export 4) · ingestion **1353p** · frontend tsc0/test12/lint0. 측정: adjudicator precision 0.57·FPR 0.2·KO 0.67(merge gate 미달).
- 문서: ADR#43(`_DECISIONS`)·R-IdentityEvalDataset 갱신+R-IdentityHumanLabeling 신규(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#43 identity evaluation dataset + metrics harness — 신규 `identity_eval_dataset.py`(EvalPair·load[allowlist=raw body/PII 차단]·`evaluate_adjudicator`=precision/FPR/recall/coverage + by_language/source_type/risk_tag·MERGE_GATE 보고)·`fixtures/identity_eval_pairs.jsonl`(22 진단 pair·4사분면·KO/EN/mixed)·`export_identity_eval_pairs.py`(adjudication→human-labeling 워크시트 소비처·no PII). **측정(정직): 현 deterministic adjudicator precision 0.57·FPR 0.2·hard-neg FP 3·recall 0.57·KO 0.67 → merge gate 미달·auto_merge_enabled=False**. 자동 병합 0·API 미노출·migration 없음. adversarial JUSTIFIED(safety)·**BUG 2 수정**(export latin→en 정규화·fn_ko_paraphrase gold 교정)·**정직 잔여**(dead-data 한 단계 미룸·한국어 측정만·fixture 진단치·MERGE_GATE 장식). **R-IdentityEvalDataset harness 부분 진전(OPEN)·R-IdentityHumanLabeling 신규·R-SemanticIdentityAdjudicator gap④ 부분 진전(OPEN)**·완전종결=OVERCLAIM. **backend 비-live 348p/4s · live-PG 49p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#42 커밋 `f0a7de9` 위 ADR#43 미커밋(code 2+fixture 1+tests 3+docs 8=14파일)·커밋 지시 대기·push 안 함._
