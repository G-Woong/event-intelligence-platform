# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 ADR#53을 안정 기준점으로 커밋한 뒤, **운영 가동을 켜기 직전 필요한 점검을 하나의 보고서로 묶는 도구**(production activation preflight)와 **실제 소스 수집이 어디까지 닿는지 단계별로 진단하는 도구**(real-source smoke)를 만들었습니다. 둘 다 **읽기 전용/안전**(DB 변경 0·자동 합치기 0)이고, 진짜 보호막은 dev DB에서 사실상 작동 안 함을 **숨기지 않고 경고로 드러냅니다**. LLM/에이전트가 언제 들어와도 되는지의 **진입 조건 9가지**도 문서로 못박았습니다.
- **이번 턴에 실제로 끝낸 것:** ADR#53 커밋(`6a006eb`) → **ADR#54**: `production_activation_preflight`(17필드 한 보고서·can_persist 게이트·환경 분류·APP_ENV↔DB 불일치 경고) + `real_source_identity_smoke`(기본 가짜소스·네트워크 0·DB 0·단계별 실패 분류) + `db_target.classify_write_target`(환경 named 분류) + 신규 테스트 2파일 **38 passed** + docs 8 동기화. **adversarial+code-review 가 classify 의 cross-tier 불일치 갭(MEDIUM)을 발견→수정**. C(인덱스)·D(lock)는 계속 보류, E(LLM/Agent)는 docs 설계만.
- **정직한 한계:** 이 둘은 **점검·진단이지 가동이 아닙니다**(read-only). smoke는 기본이 **가짜 소스**(실제 네트워크 fetch 0·DB 단계는 offline에서 None). scheduler **실가동 0**·**production 백로그 0**·운영 DB 무변경·실 reviewer/gold/병합 0·LLM/Agent 본경로 0(docs만). push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `6a006eb`**(ADR#53, 본 턴 첫 커밋) 위 **ADR#54 = 미커밋 신규 도구 2 + 신규 테스트 2 + `db_target.py`(classify 추가) + docs 8**. **migration 없음**.
- 신규 파일: `backend/app/tools/{production_activation_preflight,real_source_identity_smoke}.py`·`backend/tests/{test_production_activation_preflight,test_real_source_identity_smoke}.py`. 수정: `backend/app/tools/db_target.py`(classify_write_target·기존 assert 불변) + docs 8.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전(운영 boundary·진단 tool)** · **R-RealSourceLoopUnproven 부분진전(단계별 진단)** · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (production live backlog activation preflight — ADR#54)
- **① ADR#53 커밋**: 11파일 → `6a006eb`(secret PASS·closeout EXACT_MATCH·push 0).
- **② 원자 분석(20문항)**: 4 서브시스템 병렬 탐색(file:line). safe-target=binary(classification 없음·dev event_intel no-op)·preflight 6필드·readiness 9필드·yna/bbc/hacker_news=key-free smoke·community/market/catalog anchor 금지·packet→gold→MERGE_GATE 코드 BUILT·auto_merge 불변·fake-source smoke network/DB 0 재현 가능. **결론:** preflight 17필드 대부분 기존 함수 조합·신규는 classification/mismatch/can_persist/block_reasons/next_actions.
- **③ 옵션 결정(ADR#54)**: **A 채택**(preflight package) + **B 채택**(real-source smoke·tool·fake-default·CI 필수 아님) + **C/D 금지**(승인 필요·DEFER 유지) + **E docs만**(LLM/Agent 진입 9조건).
- **④ production_activation_preflight.py**(read-only·DDL/upgrade/persist 0): `_build_preflight_report`(순수·DB 무관)가 readiness+flag+safe_target+`classify_write_target`를 17필드 report 로 조립. `can_persist = persist ∧ ready ∧ (flag∨allow_flag_off) ∧ safe_target ∧ ¬destructive ∧ (consistent∨allow_non_dev)`. dev head 실측: dry-run eval **exit 0**·persist+flag off→blocked **exit 1**·persist+allow_flag_off→**exit 0**. safe-target no-op(MEDIUM-1)·index/lock DEFER 를 warning 으로 표면화. DATABASE_URL fingerprint 만(원문 미로그).
- **⑤ db_target.classify_write_target**(신설): safe-target binary 위에 **named 분류**(dev/test/staging/production/unknown) + APP_ENV↔URL mismatch(URL prod-marker 가 APP_ENV 보다 위험하면 채택·거짓 안심 차단). 기존 `assert_safe_write_target` 불변. **adversarial+code-review 가 `consistent` 가 cross-tier 불일치(production↔staging·unknown+prod)를 "일치"로 오보고하는 갭(MEDIUM·차단은 fail-closed 보존이나 진단 신호 거짓)을 발견 → tier-일치 규칙으로 수정·회귀 테스트 6 추가**.
- **⑥ real_source_identity_smoke.py**(기본 offline fake·network 0·DB 0·결정론): fetch(주입)→cluster→candidate write-free 진단 → source_role_distribution·failures_by_stage(body_missing/no_cluster_singleton/non_publishable_role/no_semantic_fingerprint). fake fixture 결정론(sources 8·clusters 3·singletons 2·fingerprints 2·role article5/official1/community2). DB 단계 offline **None**·`run_db_identity_smoke`(safe-target gated·test/dev·opt-in)는 기존 `ingest_records_to_events`(live-PG 검증됨) 호출. real_fetch 플래그로 "실 fetch 0 = RealSourceLoop 미닫음" 표면화.
- **⑦ E(LLM/Agent) docs 진입 9조건**: backlog>0·source role guard·candidate/adjudication·reviewer/gold 또는 eval gate·MERGE_GATE·raw/public 분리·uncertainty·community reaction layer·time-series substrate. Agent 역할(evidence/gold/MERGE_GATE/uncertainty 통제 하 IU 생성·임의 병합 금지)을 `RAG_KG_AGENT_READINESS §6b`·`INTELLIGENCE_UNIT_CONTRACT §4`에 명문화. 현재 No-Go(조건 1·4·5 미충족).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·운영 배선 ADR#48·incremental/no-cluster ADR#49·keyset/CLI ADR#50·preflight/exit/created_at cursor ADR#51·docker scaffold ADR#52·docker 실행성 실측 ADR#53·**activation preflight + real-source smoke ADR#54**) → ④ 실 병합(**미구현**).
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·실제 profile 활성+--persist 가동·실 병합·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE. "점검(preflight)·진단(smoke)·docker 실행성 ≠ production 가동" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: preflight/smoke 는 Intelligence Unit **merge safety substrate** 의 가동 전 점검·진단(read-only·자동 병합 0·smoke offline DB 0·public API 미노출). LLM/Agent 진입 9조건·Agent 최종 역할을 `RAG_KG §6b`·`IU_CONTRACT §4`에 명문화. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-LiveIdentityBacklog**(production activation preflight·DB boundary/safe-target no-op 표면화·can_persist 게이트) + **R-RealSourceLoopUnproven**(real-source smoke 단계별 실패 분류·fake-default·CI 강제 아님). 둘 다 완전종결 금지(운영 DB·실 fetch·gold·merge 잔여).
- **신규 RISK 미등록**(R-ProductionActivationBoundary/R-RealSourceSmoke/R-AgentReadinessGate 불요 — preflight 는 기존 게이트 조합·smoke 는 진단 tool·LLM/Agent 진입 docs 명문화·전부 R-LiveIdentityBacklog/R-RealSourceLoopUnproven 교차 추적·RISK 남발 금지). 종결 0·신규 0.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·승인 필요·옵션 C/E 금지) + flag on + 실 fetch 필요 → preflight 가 게이트·체크리스트로 점검만·production 0.
- **scheduler 실가동**: docker 실행성 입증(ADR#53)이나 실가동 0(profile 비활성·운영 DB 0003·flag off·--persist 미지정·승인 필요·이월).
- **safe-target 실 보호막(MEDIUM-1)**: ADR#54 preflight 가 classification + mismatch warning 으로 **표면화**하나, dev event_intel 경로는 여전히 no-op — 실 persist 운영 활성 전 별도 운영 DB+`APP_ENV=production`+`--allow-non-dev-db` 필요(이월).
- **실 source smoke(실 network)**: smoke 기본은 fake-source(network 0·DB offline None) — 실 network fetch/실 볼륨은 probe 주입 opt-in(이번 턴 미수행·CI 강제 아님·이월).
- **실 병합/gold/합의·LLM/Agent 본경로**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축. LLM/Agent 진입 9조건 docs 명문화만(본경로 0).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위·승인 필요) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#54 신규 도구 2 + 신규 테스트 2 + `db_target.py`(classify) + docs 8 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(deploy checklist + preflight) → 별도 운영 DB URL + `APP_ENV=production` + flag on → `production_activation_preflight --persist` can_persist=True 확인 → docker profile 활성 + `--persist` 가동 → 실 cross-source fetch(real-source smoke `--live-db`) → reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `6a006eb`(ADR#53). ADR#54 변경: `production_activation_preflight.py`·`real_source_identity_smoke.py`·`db_target.py`(classify_write_target)·테스트 2·docs 8.
- 검증(정직): 신규 테스트 2파일 **38 passed**(preflight 28+smoke 10·classify consistent 갭 수정 회귀 6 포함)·db_target consumer 슬라이스 **29 passed**·ingestion **1353 passed**·frontend tsc **0**/node:test **12**/lint **0**·backend 비-live(live-PG 제외) **512 passed / 4 skipped / 0 failed(959s·pre-fix ADR#54 test 29 포함·classify fix 후 38p 재검증)**·preflight CLI 3모드 실측(dry-run exit 0·persist+flag off exit 1·persist+allow_flag_off exit 0)·smoke CLI offline 결정론. 운영 DB 무변경(preflight read-only·smoke offline DB 0).
- 문서: ADR#54(`_DECISIONS`)·R-LiveIdentityBacklog/R-RealSourceLoopUnproven 부분진전(`_RISK`)·운영 activation preflight+smoke 서브섹션·RealSourceLoop 표 헤더(`2_ROADMAP/15`)·LLM/Agent 진입 9조건(`RAG_KG §6b`·`IU_CONTRACT §4`)·`_CANONICAL/02`·`2_ROADMAP/00`.

---
_as_of: 2026-06-25 · ADR#54 production live backlog activation preflight — ADR#53 커밋(`6a006eb`) 후 운영 가동 직전 통합 점검 + 단계별 진단 도구 추가. `production_activation_preflight.py`(read-only·DDL/upgrade/persist 0): readiness+flag+safe_target+`classify_write_target`(named 분류 dev/test/staging/production/unknown + APP_ENV↔URL mismatch)를 **17필드 한 report** 로 묶어 can_persist[persist∧ready∧flag∧safe_target∧¬destructive∧consistent]·block_reasons·next_required_actions 산출·dev event_intel safe-target **no-op(MEDIUM-1) warning 표면화**(은폐 금지)·DATABASE_URL fingerprint 만·**--allow-non-dev-db 는 readiness/flag 못 우회**(테스트 잠금). `real_source_identity_smoke.py`(기본 offline fake·network 0·DB 0·결정론): fetch→cluster→candidate write-free 진단·failures_by_stage(body_missing/no_cluster/non_publishable_role/no_fingerprint)+source_role_distribution·DB 단계 offline None·`--live-db`(safe-target gated·test/dev) opt-in·**real_fetch 0(기본 fake)**·community anchor 금지·no_auto_merge 불변. `db_target.classify_write_target` 신설(기존 assert 불변). C/D 계속 DEFER(persist 시 warning)·E(LLM/Agent) docs 진입 9조건만(`RAG_KG §6b`·No-Go). **측정**: 신규 테스트 2파일 38 passed(preflight 28+smoke 10·classify 갭 수정 회귀 포함)·db_target consumer 29p·ingestion 1353p·frontend tsc0/test12/lint0·backend 비-live 512 passed/4 skipped/0 failed(959s)·preflight CLI 3모드 exit 0/1/0·smoke CLI offline 결정론. **정직 경계**: preflight 는 점검(read-only)이지 가동 아님·smoke 기본 fake-source(real_fetch 0·DB offline None)·`run_db_identity_smoke` 는 opt-in(safe-target gated·이번 턴 실행 0)·운영 DB 무변경·scheduler 실가동 0·production 백로그 0·LLM/Agent 본경로 0(docs 9조건만·No-Go). **R-LiveIdentityBacklog·R-RealSourceLoopUnproven 부분진전**·신규 RISK 0(교차 추적·남발 금지)·완전종결=OVERCLAIM. ADR#53 커밋 `6a006eb` 위 ADR#54 미커밋(도구 2+테스트 2+db_target+docs 8)·커밋 지시 대기·push 안 함._
