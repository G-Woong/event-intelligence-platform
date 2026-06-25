# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴 만든 도구(ADR#55)를 안정 기준점으로 **커밋**한 뒤, "왜 진짜 소스 한 번 fetch 로는 같은 사건 자동판정이 0이었나"를 코드 단계로 정밀 분해했습니다. 그리고 **같은 사건을 다른 주소(URL)로 시간 차를 두고 두 번 집어넣는 합성 재생(replay)** 을 만들어, **버리는 테스트 DB**에서 실제로 cross-batch 후보가 생기고 자동판정(adjudication)이 누적되는지 측정했습니다.
- **이번 턴에 실제로 끝낸 것:** ADR#55 커밋(`bc86c36`) → **ADR#56**: `run_time_series_replay_smoke`(합성 2배치·같은 사건·다른 URL·교차배치)로 `event_intel_test` 에서 **cross-batch 후보 링크 1·자동판정 1(같은 사건일 가능성 높음)·사건수 0→2·자동병합 0** 실측 — **substrate(cross-batch 동일성→자동판정)가 닫힘을 진짜 데이터로 입증**. 동시에 "왜 자동판정 0/N 인가"를 6가지 단계 원인으로 귀속하는 분류기(`classify_adjudication_block_reason`)를 추가.
- **정직한 한계:** 이 replay 는 **합성(artificial)** 이라 진짜 소스 동작이 아닙니다 — 실제로는 여러 소스가 같은 사건을 보도하거나 시간 축으로 반복돼야 합니다(다음 단계). 단일 소스(ADR#55) 0의 원인은 `no_cross_batch_overlap` 로 정확히 분해. **production 백로그 0·운영 DB 무변경·실 gold/reviewer/병합 0·LLM/Agent 본경로 0(No-Go)** 불변. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `bc86c36`**(ADR#55, 본 턴 첫 커밋) 위 **ADR#56 = 미커밋**: 코드 2(`real_source_identity_smoke.py` 확장 + `real_source_smoke_report.py` 확장) + 테스트 3(smoke unit 2 확장 + live-PG 1 확장) + docs 8 = **변경 13파일**(신규 0·전부 기존 확장). **migration 없음**.
- 수정: `backend/app/tools/{real_source_identity_smoke,real_source_smoke_report}.py`·`backend/tests/{test_real_source_identity_smoke,test_real_source_smoke_report,test_event_resolution_live_pg}.py` + docs 8(`2_ROADMAP/00·15`·`_RISK/RISK_REGISTER`·`5_REFERENCE/RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT`·`_CANONICAL/02`·`_DECISIONS/2026-06`·`PROJECT_STATUS`).
- 열린 RISK: **R-RealSourceLoopUnproven 부분진전(단계 5 stage③ adjudication 실데이터 도달·artificial)** · **R-LiveIdentityBacklog 부분진전(백로그 발생 조건 실데이터 입증·block-reason 분해)** · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). 신규 RISK 0·종결 0. throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (time-series replay smoke + adjudication block-reason 분해 — ADR#56)
- **① ADR#55 커밋**: 12파일 → `bc86c36`(secret PASS 262·docs_lifecycle conflicts 0·closeout SIGNATURE MATCH 15·push 0).
- **② 원자 분석(§2·20문항)**: substrate 4모듈 정독(file:line). **adjudications 0 의 call path 확정** — cross-batch `semantic_cross_batch_candidate` link 은 `resolve_and_apply_cluster` 에서 **새로 CREATE 된 Event 의 fingerprint(제목 token-set+date bucket)가 기존 `event_identity_candidate` 의 *다른-URL* Event 정확히 1개와 매칭**될 때만 생성·stage③ 는 그 link 만 처리. held-member link reason `new_event_low_confidence:{key}` 는 제외. **federal_register=distinct document=distinct URL=distinct event=distinct fingerprint → 같은-사건·다른-URL 후보 구조적 불가(source scarcity)**.
- **③ 옵션 결정(ADR#56)**: **B 채택**(time-series replay·핵심 결정론 substrate 검증) + **C 채택**(sanitized 계약을 replay 템플릿에 내재·별도 capture 파일 미생성·YAGNI) + **E 채택**(§5 block-reason 분해). **A 정직 분해만**(key-free 공식 단독 cross-source overlap 구조적 희소·깨지기 쉬운 스크레이퍼 미구현). **C(production)/D(LLM) 금지.**
- **④ run_time_series_replay_smoke**(safe-target gated·`--time-series-replay`): `build_replay_batches()`(artificial 2배치·배치 A 같은 URL 2 record→CREATE E1+fingerprint F·배치 B **다른 URL** 2 record[같은 제목·날짜=같은 F]→CREATE E2→`semantic_cross_batch_candidate` link→stage③)·배치 순차 ingest·`_link_reason_distribution`/`_adjudication_status_distribution` read-only 집계·**artificial_replay=True**·본문 미저장.
- **⑤ 측정(실데이터·`event_intel_test` head 0009·TRUNCATE 격리·live-PG 잠금)**: replay 2배치 → **created 2 · semantic_cross_batch_candidate link 1 · adjudications 1(likely_same_event 1) · event_count 0→2 · no_auto_merge=True**. **cross-batch adjudication substrate 가 같은-사건·다른-URL·교차배치 데이터에서 닫힘을 실데이터로 입증.**
- **⑥ §5 block-reason 분해**: `classify_adjudication_block_reason`(순수·결정론)=`db_not_reached`/`none`/`semantic_link_without_adjudication`/`non_publishable_role`/`no_fingerprint_overlap`/`no_cross_batch_overlap`. 단일소스(ADR#55) 0 → `no_cross_batch_overlap` 로 정확 귀속(adjudication 0 을 '실패'로 뭉뚱그리지 않음). `assemble_activation_report` 에 smoke_mode/artificial_replay/batches/link_reason_distribution/adjudication_status/block_reason 추가.
- **⑦ 감사 반영**: (closeout 에서 adversarial-reality-critic + code-review 호출) — 평결·지적은 closeout stamp 에 기록.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·운영 배선 ADR#48·incremental ADR#49·keyset/CLI ADR#50·preflight/cursor ADR#51·docker scaffold ADR#52·docker 실행성 ADR#53·activation preflight+smoke ADR#54·real-source live-db smoke ADR#55·**time-series replay substrate 실데이터 입증 ADR#56**) → ④ 실 병합(**미구현**).
- **⚠ 미해소(OPEN):** 실 동일사건 다중소스/시계열 fetch(artificial replay ≠ 실 source)·운영 DB 0009 배포·실제 profile 활성+--persist 가동·실 병합·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE. "substrate 입증(능력) ≠ production 운영(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed. replay 배치는 publishable(article) 만(anchor 자격)·community/market/catalog 는 `guard_only`(anchor 금지·matrix).
- **제품 계약(raw≠public)**: replay smoke 는 Intelligence Unit **merge safety substrate** 의 실데이터 진단(read-only·자동 병합 0·**본문 미저장**·public API 미노출). LLM/Agent 진입 9조건(현재 1·4·5·7 미충족 No-Go)·조건 3 의 cross-batch adjudication evidence 를 ADR#56 replay 로 보강(여전히 No-Go). final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-RealSourceLoopUnproven**(ADR#55 단일소스 adjudications 0 → ADR#56 **artificial time-series replay 가 단계 5[stage③ adjudication]을 실데이터로 도달**·block-reason 분해·no-auto-merge 유지) + **R-LiveIdentityBacklog**(백로그가 채워지는 조건[동일사건·다른-URL·교차배치]을 실데이터 입증·"왜 0/N 인가" source/data/fingerprint/cross-batch 귀속). 둘 다 완전종결 금지(artificial≠실 source·운영 DB·실 cross-source 볼륨·gold·merge 잔여).
- **신규 RISK 미등록**(replay validity/coverage 는 기존 R-RealSourceLoopUnproven/R-LiveIdentityBacklog 의 gap·RISK 남발 금지). 종결 0·신규 0.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **실 cross-source identity link/adjudication**: artificial replay 는 substrate 검증이지 실 source behavior 가 아니다 — 실제로 같은 사건을 여러 소스가 보도하거나 시간 축으로 반복돼야(이월·다음 hard blocker). 옵션 A(multi-source 실 fetch)는 key-free 공식 단독 cross-source overlap 희소로 정직 분해만(스크레이퍼 미구현).
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·승인 필요·옵션 C 금지) + flag on + 실 fetch 볼륨 필요 → production 0.
- **실 병합/gold/합의·LLM/Agent 본경로**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축. 9조건 docs 명문화만(본경로 0·No-Go).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 실 cross-source identity link = 동일사건 다중소스 커버리지/시계열 볼륨 선결(artificial replay 로 substrate 만 입증·실 source 아님). 운영 production 백로그 = 운영 DB 0009 배포(승인) + 실 fetch 볼륨.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#56: 코드 2(smoke+report 확장) + 테스트 3(smoke unit 2+live-PG 1 확장) + docs 8 = 13파일 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (a) **실** 동일사건 다중소스/시계열 fetch(artificial replay 를 실 source 로 대체 → 실 adjudication backlog) → (b) (운영 승인 하) 운영 DB 0009 배포 + 별도 운영 DB URL + `APP_ENV=production` + flag on + `production_activation_preflight --persist` → docker profile 활성 + `--persist` 가동 → (c) reviewer 합의 gold + 한국어 캘리브레이션 → (d) embedding/LLM/KG 실 병합 adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `bc86c36`(ADR#55). ADR#56 변경: `real_source_identity_smoke.py`(replay 빌더+실행기+분포 쿼리)·`real_source_smoke_report.py`(block-reason 분류기+report 필드)·테스트 3·docs 8.
- 검증(정직): artificial time-series replay `event_intel_test`(created 2·semantic_cross_batch_candidate 1·adjudications 1[likely_same]·event_count 0→2·no_auto_merge·live-PG 잠금)·신규/확장 테스트 **15**(unit 12+live-PG 3)·smoke 2파일 unit **51 passed**·backend 비-live(live-PG 제외) **559 passed/4 skipped/0 failed(965s)**·live-PG **94 passed**(91→94·event_intel_test·TRUNCATE 격리)·ingestion **1353 passed**·frontend tsc **0**/node:test **12**/lint **0**(`next lint`)·secret scan **PASS(262)**·docs_lifecycle conflicts **0**. 운영 DB 무변경(disposable test DB).
- 문서: ADR#56(`_DECISIONS`)·R-RealSourceLoopUnproven/R-LiveIdentityBacklog 부분진전(`_RISK`)·time-series replay 서브섹션+RealSourceLoop 표 row5(`2_ROADMAP/15`)·(11n)(`2_ROADMAP/00`)·agent readiness 조건 3 status(`RAG_KG §6b`)·`IU_CONTRACT`·`_CANONICAL/02`.

---
_as_of: 2026-06-25 · ADR#56 time-series replay smoke + adjudication block-reason 분해 — ADR#55 커밋(`bc86c36`) 후 "단일소스 adjudications 0"의 원인을 call path 로 정밀 분해(distinct document=distinct URL=distinct fingerprint→같은-사건·다른-URL 후보 구조적 불가=source scarcity)하고, `run_time_series_replay_smoke`(safe-target gated·`--time-series-replay`·**artificial** 2배치·같은 사건·다른 URL·교차배치·본문 미저장)로 **cross-batch adjudication substrate 가 닫힘을 실데이터 입증**: `event_intel_test`(head 0009·TRUNCATE 격리·live-PG 잠금) → **created 2·semantic_cross_batch_candidate link 1·adjudications 1(likely_same_event)·event_count 0→2·no_auto_merge=True**. `classify_adjudication_block_reason`(§5 순수: db_not_reached/none/semantic_link_without_adjudication/non_publishable_role/no_fingerprint_overlap/no_cross_batch_overlap)가 단일소스 0 을 `no_cross_batch_overlap` 로 귀속(조용한 0 금지). 옵션 **B+C+E 채택·A 정직분해(key-free 공식 단독 overlap 희소·스크레이퍼 미구현)·C(prod)/D(LLM) 금지**. **측정**: 신규/확장 15(unit 12+live-PG 3)·smoke unit 51 passed·backend 비-live <BACKEND_NONLIVE>·live-PG 94 passed·ingestion 1353p·frontend tsc0/test12/lint0·secret PASS·docs_lifecycle 0. **정직 경계**: `artificial_replay=True`≠실 source behavior(실 동일사건 다중소스/시계열 fetch 잔여)·운영 DB 배포·reviewer/gold/merge·LLM 본경로 잔여(production 백로그 0 불변·완전종결 금지·substrate 입증≠production 운영). **R-RealSourceLoopUnproven·R-LiveIdentityBacklog 부분진전**·신규 RISK 0·종결 0. ADR#55 커밋 `bc86c36` 위 ADR#56 미커밋(코드 2+테스트 3+docs 8=13)·커밋 지시 대기·push 안 함._
