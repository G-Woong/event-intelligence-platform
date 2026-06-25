# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 지난 턴에 만든 docker backfill scheduler가 **실제로 켜지긴 하는지** 진짜 docker로 빌드·실행해 확인했습니다. 그 과정에서 **숨어 있던 버그**(필요한 코드 폴더 `ingestion`을 docker 이미지에 안 넣어서, 켜면 곧바로 죽는 문제)를 찾아 **고쳤습니다**. 고친 뒤 3가지 상황(DB 꺼짐·DB 준비 안 됨·DB 준비됨)에서 전부 **안전하게**(쓰기 0·합치기 0) 동작함을 확인했습니다. 자동 합치기는 계속 0.
- **이번 턴에 실제로 끝낸 것:** ADR#52 커밋(`1368abf`) → **ADR#53**: 실 `docker compose build/run` dry-run 3경로 실측(exit 2/1/0)·**ingestion COPY 버그 발견·수정**(`backend/Dockerfile` 1줄+회귀 테스트 2)·**live-PG 91개 테스트 재실행(전부 통과)**. 측정: backend 비-live **480 passed / 4 skipped / 0 failed(963s·postgres 가동)**·ingestion **1353p**·frontend tsc0/test12/lint0·backfill scheduler ops **21p**(신규 2). adversarial-reality-critic **CONDITIONAL VALID**(코드·안전계약 VALID·문서 미반영 HIGH-1은 본 문서/ledger 정정으로 해소). 옵션 C(인덱스)·D(lock)는 **근거와 함께 계속 보류**.
- **정직한 한계:** scheduler가 **실제로 켜져서 도는 것은 아닙니다(실가동 0)** — 검증은 한 번 돌고 끝나는 `--once` dry-run이고, 평소엔 꺼져 있습니다(profile 비활성). run#3의 "처리 0건"은 dev DB가 **비어서**이지 백로그를 처리한 게 아닙니다 — **배관은 검증, 실 처리량은 미검증**. `production 백로그는 0`. 실 reviewer/gold/병합 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `1368abf`**(ADR#52, 본 턴 첫 커밋) 위 **ADR#53 = 미커밋 code 2 + config-주석 1 + docs 8 = 11파일**. **migration 없음**. **신규 파일 0**(전부 기존 파일 수정).
- 변경: `backend/Dockerfile`(`COPY ingestion/` 1줄+주석) + `backend/tests/test_backfill_scheduler_ops.py`(회귀 테스트 2) + `docker-compose.dev.yml`(주석 ADR#53 근거) + docs 8. **파이썬 app 모듈 로직 변경 0**(Dockerfile/테스트/주석/문서만).
- 열린 RISK: **R-LiveIdentityBacklog 부분진전(gap② docker 실행성 실측)**(scheduler docker build/up dry-run 검증·ingestion 버그 수정·live-PG 91p 재실행·**여전히 실가동 0**; 운영 DB 배포·실 fetch·profile 활성+--persist 가동·index/lock 잔여) · R-RealSourceLoopUnproven · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (production scheduler activation VALIDATION — ADR#53)
- **① ADR#52 커밋**: 10파일 → `1368abf`(secret PASS·closeout 후, push 0).
- **② 원자 분석(20문항)**: Docker daemon **UP**·backend 이미지 존재 → 옵션 A(실 build/up) **가능**(fallback B 불요). **(핵심 발견)** `backend/Dockerfile`이 `backend/`·`workers/`만 COPY하고 **`ingestion/` 미COPY** → adjudicator(`semantic_identity_adjudicator.py:29`)의 `ingestion.orchestration.cross_source_dedup` 전이 import가 컨테이너 런타임에 **`ModuleNotFoundError`**. 정적 config·5 테스트·**build까지 통과·run만 죽음** — "docker config만으로 검증 완료" 금지의 정확한 사례.
- **③ docker build/up dry-run 실측**(옵션 A·채택·실행): `docker compose --profile backfill config`(default 11·--profile 12 → profile 격리 docker 실증)·`build` **성공**·`run --once --limit 5` **3경로**: ①`--no-deps`(DB down)→부팅·import·safe-target 통과 후 `gaierror`→graceful **exit 2**(크래시 0); ②postgres 구버전(미마이그레이션)→`BLOCKED block=readiness ready_for_stage3=False`→**exit 1**(write 0); ③dev DB head 마이그레이션 후→`cycle ran dry_run=True processed=0 pending 0->0 event_count 0->0 auto_merge=False`→**exit 0**.
- **④ 🔴 버그 발견·수정**: `backend/Dockerfile`에 `COPY ingestion/ ingestion/` 추가(전이 의존 주석) + 회귀 테스트 2(`test_backend_image_copies_ingestion_for_adjudicator`=Dockerfile COPY[ingestion/backend/workers] 정적 잠금·`test_scheduler_allow_non_dev_db_overrides_safe_target`=APP_ENV=staging+`--allow-non-dev-db` override 경로). compose 주석에 ADR#53 근거.
- **⑤ live-PG 91p 재실행**: `event_intel_test`(disposable·dev event_intel과 분리·head) 대상 `test_event_resolution_live_pg` **91 passed**(221s·직렬 `-p no:xdist`) — ADR#52는 PG 미가동으로 미실행했던 것을 이번 턴 실행.
- **⑥ 옵션 C/D DEFER(근거 강화·critic 실측 확인)**: **C(created_at index)** — backlog 0(run#3 pending 0)·`test_event_resolution_live_pg:1289`(`expected_head=="c9d0e1f2a3b4"`)·`test_identity_backlog_readiness`(`len(chain)==9`·`behind_count 6/9`) 하드코딩 → 0010 추가 시 **4+ assertion churn**(critic 파일 실측) → DDL runbook 문서화·미적용. **D(advisory lock)** — link_id PK upsert(중복행 0·데이터 안전)+단일 instance **규율 가정**(물리 차단 아님) → defense-in-depth DEFER. **E(운영 DB upgrade) 금지**.
- **read-only 입증 정직(MEDIUM-1)**: run#3 `event_count 0->0`은 dev DB가 **비어서**(처리 0건)이지 read-only를 입증하지 **않음** — read-only 입증은 **코드**(`_persist_adjudication`이 adjudication 테이블만 upsert)**+live-PG 91p**(non-empty DB Event count 불변).
- **adversarial 평결**: adversarial-reality-critic **CONDITIONAL VALID** — 코드·4대 안전계약(자동 병합 0·dry-run default·profile-gated·운영 DB 무단 upgrade 0) **전부 성립**(ingestion COPY 최소·정확한 회귀 *수정*·cross_source_dedup/eventqueue_dedup/time_normalizer **stdlib-only 실측 일치**·C/D DEFER 근거 파일 실측·종결 과대 0). **HIGH-1**(ADR#53 산출물이 ADR#52 상태에 머물러 "build/up 미검증" 오기재) → **본 PROJECT_STATUS + ledger [#53] + compose 주석 정정으로 해소**. **MEDIUM-1**(run#3 read-only 약증거→코드+live-PG 귀속)·**MEDIUM-2**(live-PG 91=DB orchestration 정확성·scheduler 주기 가동 아님) 반영.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48·incremental/no-cluster ADR#49·keyset/CLI ADR#50·preflight/exit/created_at cursor ADR#51·docker scaffold ADR#52·docker 실행성 실측 ADR#53**) → ④ 실 병합(**미구현**). **④ 전 선결 = eval gate(ADR#43)+gold(ADR#44)+reviewer(ADR#45)+packet(ADR#46)+live pilot(ADR#47)+stage③ wiring(ADR#48)+incremental(ADR#49)+keyset/CLI(ADR#50)+scheduler-ready(ADR#51)+docker scaffold(ADR#52)+docker 실행성 검증(ADR#53)**.
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·**실제 profile 활성+--persist docker 가동**·전수 report 경로 keyset·created_at index·advisory lock·실 병합·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE. "배선(능력)·docker 실행성(검증) ≠ production 가동(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: backfill/scheduler는 Intelligence Unit **merge safety substrate**(자동 병합 0·read+adjudication upsert only·preflight/exit/cursor/scheduler/docker 전부 internal·public API 미노출). `INTELLIGENCE_UNIT_CONTRACT §4`에 ADR#53 노트 추가. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(gap② docker 실행성 실측): R-LiveIdentityBacklog**(scheduler docker build/up dry-run 검증·ingestion 버그 수정·live-PG 91p 재실행 DONE; 운영 DB 배포·실 fetch·profile 활성+--persist 가동·index/lock·실 gold/merge 잔여·완전종결 금지).
- **R-SchedulerDockerRuntime/R-BackfillCursorIndex/R-BackfillConcurrency 미등록**(docker 실행성 입증됨[버그 수정]·index/lock DEFER 문서화·동시성 단일 runner 규율 가정·R-LiveIdentityBacklog 교차 추적·RISK 남발 금지). 종결 0·신규 0(risk count 불변).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·deploy checklist 작성됨·미실행) + flag on + 실 fetch 필요 → 능력 DONE·production 0(run#3 pending 0=빈 dev DB).
- **scheduler 실가동**: docker로 **배선됨**·**실행성 실측 입증됨**(build+run 3경로)이나 **실가동 0**(`--once` dry-run만 검증·while-loop 주기 가동 미입증·profile 비활성·운영 DB 0003·flag off·--persist 미지정·승인 필요·이월).
- **created_at 인덱스(C)·동시 work 회피(D)**: backlog 0·prod 0003 → DDL/single-instance 요건 runbook 문서화·미적용(test churn 회피·이월). D=PK upsert 멱등 안전+단일 runner 규율(물리 차단 아님·`--scale`/수동 CLI 우회 가능)·advisory lock 미구현(OS-race stress-test 없음).
- **safe-target 실 보호막(MEDIUM-1)**: dev/운영 공유 `event_intel`·scheduler APP_ENV=dev 상속이라 safe-target이 컨테이너 경로엔 no-op → 실 persist 운영 활성 전 별도 운영 DB+`APP_ENV=production`+`--allow-non-dev-db` 필요(이월).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위·승인 필요) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#53 code 2 + config-주석 1 + docs 8 (총 11파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(deploy checklist) + flag on → **docker profile 활성**(`docker compose --profile backfill up`) + dry-run 검증 → command에 `--persist` 추가 가동 + `(created_at,id)` cursor 인덱스 migration(0010) + advisory lock → 실 cross-source fetch 볼륨 → 다중 reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `1368abf`(ADR#52). ADR#53 변경: `backend/Dockerfile`(`COPY ingestion/`+주석)·`test_backfill_scheduler_ops`(회귀 테스트 2)·`docker-compose.dev.yml`(주석)·docs 8.
- 검증(정직): docker build **성공**·`run --once` 3경로 **exit 2/1/0**·`docker compose config` profile 격리(default 11·--profile 12)·**live-PG `test_event_resolution_live_pg` 91 passed**(221s·`event_intel_test` head·ADR#52 미실행→이번 턴 재실행)·`test_backfill_scheduler_ops` **21 passed**(19+신규 2)·ingestion **1353 passed**·frontend tsc **0**/node:test **12**/lint **0**·backend 비-live(live-PG 제외) **480 passed / 4 skipped / 0 failed(963s·postgres 가동)**. 검증 위해 dev `event_intel`을 `c3d4e5f6a7b8`→head 마이그레이션(운영 DB 아님·additive·비파괴).
- 문서: ADR#53(`_DECISIONS`)·R-LiveIdentityBacklog gap②(`_RISK/RISK_REGISTER`)·runbook step10 docker 검증+RealSourceLoop row6(`2_ROADMAP/15`)·`_CANONICAL/02`·`2_ROADMAP/00`·`RAG_KG_AGENT_READINESS`·`INTELLIGENCE_UNIT_CONTRACT §4`.

---
_as_of: 2026-06-25 · ADR#53 production scheduler activation VALIDATION — ADR#52의 "정적만" 한계를 실 docker로 해소. `docker compose --profile backfill build` 성공·`run --once --limit 5` **3경로 실측**(①DB down→부팅·import·safe-target 후 graceful **exit 2**·②미마이그레이션 DB→`BLOCKED readiness ready_for_stage3=False`→**exit 1**·③dev DB head→`dry_run=True processed=0 pending 0->0 event_count 0->0 auto_merge=False`→**exit 0**)·`docker compose config` profile 격리(default 11·--profile 12). **🔴 정적 config/build가 못 잡은 런타임 버그 발견·수정**: `backend/Dockerfile`이 `ingestion/` 미COPY→adjudicator의 `ingestion.orchestration.cross_source_dedup` 전이 import `ModuleNotFoundError`→`COPY ingestion/ ingestion/` 추가 + 회귀 테스트 2(Dockerfile COPY 정적 잠금·--allow-non-dev-db override). **live-PG `test_event_resolution_live_pg` 91 passed**(ADR#52 미실행→`event_intel_test` head 재실행). **측정(정직)**: docker build 성공·run 3경로 exit 2/1/0·live-PG 91p·backfill scheduler ops 21p(19+신규2)·ingestion 1353p·frontend tsc0/test12/lint0·backend 비-live 480 passed / 4 skipped / 0 failed(963s·postgres 가동). **정직 경계**: run#3 `event_count 0->0`은 빈 dev DB라 read-only 미입증(입증=코드 `_persist_adjudication` adjudication-only+live-PG)·live-PG 91=DB orchestration 정확성(scheduler 주기 가동 아님)·검증 위해 dev event_intel head 마이그레이션(운영 DB 아님·additive). C/D 계속 DEFER(backlog 0·test churn 실측). **adversarial-reality-critic: CONDITIONAL VALID** — 코드·4대 안전계약 VALID(stdlib-only 실측·read-only 코드+live-PG·종결 과대 0)·HIGH-1(ADR#53 문서 미반영→본 문서·ledger·compose 정정 해소)·MEDIUM-1/2(run#3 read-only 귀속·live-PG 범위) 반영. **R-LiveIdentityBacklog 부분진전(gap② docker 실행성 실측)**·완전종결=OVERCLAIM. scheduler 실가동 0(one-shot dry-run만·profile 비활성)·**production 백로그 0**. ADR#52 커밋 `1368abf` 위 ADR#53 미커밋(code 2+config-주석 1+docs 8=11파일)·커밋 지시 대기·push 안 함._
