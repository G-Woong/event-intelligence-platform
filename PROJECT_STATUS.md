# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 만든 진단 도구(ADR#54)를 안정 기준점으로 **커밋**한 뒤, 그 도구를 **가짜 소스에서 한 단계 더 나아가 진짜 소스로** 돌렸습니다. 키가 필요 없는 공식 출처(미국 연방관보 API)에서 실제 기사 5건을 받아와, **버리는 테스트용 DB**에 실제로 집어넣어 사건(Event)이 어디까지 만들어지는지 측정했습니다. 동시에 **소스별 품질 표**와 **AI/에이전트가 들어와도 되는지 9조건 판정**을 자동으로 뽑는 도구를 추가했습니다.
- **이번 턴에 실제로 끝낸 것:** ADR#54 커밋(`0c29d9c`) → **ADR#55**: 실제 federal_register fetch **5건(공식)** → `event_intel_test`(최신 스키마) 적재: **사건 1개 생성·연결 1개·자동판정 0·자동병합 0·사건수 4→6**. `real_source_smoke_report`(소스 품질 표 + 9조건 판정·결정론) 추가. **적대적 검토(안전계약 성립·과대주장 0)+코드리뷰(버그 0)** 가 sec_edgar 모순(MEDIUM)을 발견→**제거**, 잔여 지적 3건도 반영(설명 보강·회귀 테스트 +3·CLI 경고).
- **정직한 한계:** 실제 fetch 는 **수동 도구(CI 강제 아님)**, DB 적재는 **버리는 테스트 DB(운영 아님)**. **자동 판정(adjudication) 0** 인 이유까지 정직하게 분해함 — 같은 사건을 여러 소스가 보도하거나 시간 축으로 반복돼야 cross-batch 후보가 생기는데, 단일 소스 한 번 fetch 로는 안 됨(source scarcity). **production 백로그 0·운영 DB 무변경·실 gold/reviewer/병합 0·LLM/Agent 본경로 0(No-Go)**. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `0c29d9c`**(ADR#54, 본 턴 첫 커밋) 위 **ADR#55 = 미커밋**: 코드 2(`real_source_identity_smoke.py` 확장 + `real_source_smoke_report.py` 신규) + 테스트 2(확장 1 + 신규 1) + docs 8 = **12파일**. **migration 없음**.
- 신규: `backend/app/tools/real_source_smoke_report.py`·`backend/tests/test_real_source_smoke_report.py`. 수정: `backend/app/tools/real_source_identity_smoke.py`·`backend/tests/test_real_source_identity_smoke.py` + docs 8.
- 열린 RISK: **R-RealSourceLoopUnproven 부분진전(실 fetch+실 DB 1회 도달)** · **R-LiveIdentityBacklog 부분진전(smoke↔preflight 연결)** · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). 신규 RISK 0·종결 0. throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (real-source live-db smoke + source quality matrix — ADR#55)
- **① ADR#54 커밋**: 13파일 → `0c29d9c`(secret PASS 143·docs_lifecycle 0·closeout 무결성·push 0).
- **② 원자 분석(20문항)**: 4 서브시스템 병렬 탐색(file:line)+환경 실측. **로컬 `event_intel`·`event_intel_test` 둘 다 head 0009**(문서 "운영 DB 0003"=미배포 production 타깃)·federalregister.gov status 200(network egress 작동)·live-PG fixture TRUNCATE(test DB 잔여행 무해)·`federal_register`/`sec_edgar`=key-free official JSON API·`ingest_records_to_events` write surface 확정. **결론:** 실 fetch+실 live_db smoke 이번 턴 실행 가능(disposable test DB·official key-free).
- **③ 옵션 결정(ADR#55)**: **A 채택**(bounded real-source smoke dev/test DB) + **B 채택**(fixture/capture·**본문 미저장**·headline/canonical/published_at 만) + **E 채택**(source quality matrix) + **C 금지**(운영 DB activation·승인 필요) + **D docs/schema only**(LLM/Agent).
- **④ live_network 실 fetch**(`--live-network`·opt-in·CI 아님): `fetch_real_source_records`(key-free official allowlist=**federal_register 만**·bounded source당 ≤5·`_parse_payload_records` 가 raw JSON→다중 record[canonical=document_number URL·published_at·**headline[:512] 만·raw_payload/body 미저장**]·실패 source별 분류·transport 주입 CI network 0). **실측: federal_register status 200·5 official records**(body/canonical/published 5/5·role official·clusters 1·singletons 3·fingerprints 1).
- **⑤ live_db smoke**(`--live-db`·safe-target gated·test/dev): 실 fetch 5 → `event_intel_test`(head 0009·target=test consistent) ingest **created 1 + identity_link 1(held member) · adjudications 0 · packet_eligible 0 · no_auto_merge=True · event_count 4→6**. **+2 분해 = primary CREATE 1 + held-member degenerate event 1**(ADR#19 materialize·자동병합 아님). DB read-only 검증(events 6·possible link 1·candidate 1·adjudication 0).
- **⑥ real_source_smoke_report.py**(신규·순수·DB/network 0): `assemble_activation_report`(§4 fields) + `build_source_quality_matrix`(§9·옵션 E·source별 body/canonical/published/dedup_clusterability/identity_linkability[official+canonical=anchor_eligible·community/market/catalog=`guard_only`]/readiness/failure_stage) + `agent_readiness_conditions`(§8 9조건 PASS/PARTIAL/FAIL/NOT_BUILT·단일 출처)·`agent_readiness_gate`(No-Go).
- **⑦ 정직 분해(Q13·Q19·Q20)**: adjudications 0 = held-member link reason `new_event_low_confidence`(≠`semantic_cross_batch_candidate`) → 실 Event 는 형성되나 **cross-batch adjudication substrate 는 동일사건 다중소스/시계열 fingerprint 중첩 필요**(single bounded single-source=source scarcity). **다음 hard blocker = 실 fetch 커버리지/볼륨** → 운영 DB 배포 → reviewer/gold.
- **⑧ 감사 반영**: adversarial **CONDITIONAL VALID**(안전계약 5 성립·과대주장 0)·code-review **correctness 버그 0**. **MEDIUM(sec_edgar allowlist 모순·canonical 미파생→anchor 불가·endpoint 미실측) → allowlist 에서 제거**·LOW 3(event_count +2 산술·수신≠미저장·조건 2/8 PASS) 반영(설명 보강·**회귀 테스트 +3**·CLI 경고).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·운영 배선 ADR#48·incremental ADR#49·keyset/CLI ADR#50·preflight/cursor ADR#51·docker scaffold ADR#52·docker 실행성 ADR#53·activation preflight+smoke ADR#54·**real-source live-db smoke ADR#55**) → ④ 실 병합(**미구현**).
- **⚠ 미해소(OPEN):** 운영 DB 0009 배포·실 cross-source fetch 볼륨·실제 profile 활성+--persist 가동·실 병합·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE. "실 fetch(능력)·실 live_db smoke(검증) ≠ production 운영(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed. smoke matrix 가 community/market/catalog 를 `guard_only`(anchor 금지)로 분리.
- **제품 계약(raw≠public)**: real-source smoke 는 Intelligence Unit **merge safety substrate** 의 실데이터 진단(read-only·자동 병합 0·**본문 미저장**·public API 미노출). LLM/Agent 진입 9조건(현재 1·4·5·7 미충족 No-Go)·Agent 최종 역할을 `RAG_KG §6b`·`IU_CONTRACT §4`에 명문화. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-RealSourceLoopUnproven**(ADR#54 fake-default → ADR#55 **실 federal_register fetch + 실 live_db ingest 로 1~5 단계 실데이터 1회 도달**·단계별 실패 실 흐름 설명·no-auto-merge 유지) + **R-LiveIdentityBacklog**(real-source smoke↔preflight 연결·packet/reviewer export 경로 수치화). 둘 다 완전종결 금지(운영 DB·실 cross-source 볼륨·gold·merge 잔여).
- **신규 RISK 미등록**(coverage/matrix/readiness 는 기존 R-RealSourceLoopUnproven/R-LiveIdentityBacklog 의 gap·RISK 남발 금지). 종결 0·신규 0.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 cross-source identity link/adjudication**: 단일 bounded single-source fetch → singletons·held member 만(source scarcity). 동일사건 다중소스/시계열 fetch 볼륨 필요(이월·다음 hard blocker).
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·승인 필요·옵션 C 금지) + flag on + 실 fetch 볼륨 필요 → production 0.
- **실 network fetch 의 CI 편입**: flaky(network/schema) → CI 는 MockTransport 결정론만·실 fetch 는 opt-in tool(이월·옵션 B fixture capture 는 추후).
- **실 병합/gold/합의·LLM/Agent 본경로**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축. 9조건 docs 명문화만(본경로 0·No-Go).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 실 cross-source identity link = 동일사건 다중소스 커버리지/시계열 볼륨 선결(단일 bounded fetch 로 불가). 운영 production 백로그 = 운영 DB 0009 배포(승인) + 실 fetch 볼륨.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#55: 코드 2(smoke 확장+report 신규) + 테스트 2 + docs 8 = 12파일 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (a) 실 fetch 커버리지/볼륨 확대(동일사건 다중소스·시계열 cross-batch → adjudication backlog 생성) → (b) (운영 승인 하) 운영 DB 0009 배포 + 별도 운영 DB URL + `APP_ENV=production` + flag on + `production_activation_preflight --persist` → docker profile 활성 + `--persist` 가동 → (c) reviewer 합의 gold + 한국어 캘리브레이션 → (d) embedding/LLM/KG 실 병합 adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `0c29d9c`(ADR#54). ADR#55 변경: `real_source_identity_smoke.py`(확장)·`real_source_smoke_report.py`(신규)·테스트 2·docs 8.
- 검증(정직): live_network 실 federal_register fetch **5 official**(body/canonical/published 5/5)·live_db `event_intel_test`(created 1·identity_link 1·adjudications 0·event_count 4→6·no_auto_merge)·신규/확장 테스트 **39 passed**·backend 비-live(live-PG 제외) **547 passed/4 skipped/0 failed(963s)**·live-PG **91 passed**(event_intel_test·smoke 행 TRUNCATE 정리)·ingestion **1353 passed**·frontend tsc **0**/node:test **12**/lint **0**(`next lint`)·secret scan **PASS**. 운영 DB 무변경(disposable test DB·read-only 검증).
- 문서: ADR#55(`_DECISIONS`)·R-RealSourceLoopUnproven/R-LiveIdentityBacklog 부분진전(`_RISK`)·real-source live-db smoke 서브섹션+RealSourceLoop 표(`2_ROADMAP/15`)·(11m)(`2_ROADMAP/00`)·agent readiness 9조건 status(`RAG_KG §6b`)·`IU_CONTRACT`·`_CANONICAL/02`.

---
_as_of: 2026-06-25 · ADR#55 real-source live-db smoke — ADR#54 커밋(`0c29d9c`) 후 fake-source 진단을 **실 fetch+실 DB** 로 한 단계 진전. `real_source_identity_smoke.py` 확장: **live_network**(key-free official JSON API `federal_register`·bounded·opt-in·CI 아님·**본문 미저장**·transport 주입 CI network 0)+**live_db**(disposable `event_intel_test` head 0009·safe-target gated)·신규 `real_source_smoke_report.py`(순수)가 §4 activation report+**source quality matrix**(§9·옵션 E)+**agent readiness 9조건**(§8·단일 출처·No-Go) 조립. **실측**: 실 federal_register fetch 5 official records → ingest **created 1+identity_link 1(held member)·adjudications 0·packet_eligible 0·no_auto_merge=True·event_count 4→6**(+2=primary 1+held degenerate 1). **정직 분해**: adjudications 0=held-member link reason `new_event_low_confidence`(≠`semantic_cross_batch_candidate`)·cross-batch adjudication 은 동일사건 다중소스/시계열 fingerprint 중첩 필요(source scarcity). adversarial **CONDITIONAL VALID**(안전계약 5 성립·과대주장 0)·code-review **correctness 0**·**MEDIUM(sec_edgar allowlist 모순) 제거**+LOW 3 반영(설명·회귀 +3·CLI 경고). **측정**: 신규/확장 39 passed·backend 비-live 547 passed/4 skipped/0 failed(963s)·live-PG 91p·ingestion 1353p·frontend tsc0/test12/lint0·secret PASS. **정직 경계**: live_network=opt-in tool(CI 아님)·live_db=disposable test DB(production 아님)·실 cross-source 비뉴스 Event·실 adjudication backlog·reviewer/gold/merge·운영 DB 배포 잔여(production 백로그 0 불변·완전종결 금지·실 fetch≠production 운영). **R-RealSourceLoopUnproven·R-LiveIdentityBacklog 부분진전**·신규 RISK 0. ADR#54 커밋 `0c29d9c` 위 ADR#55 미커밋(코드 2+테스트 2+docs 8=12)·커밋 지시 대기·push 안 함._
