# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 밀린 검수 후보 판정(③) backfill scheduler를 **실제 운영(docker) 서비스로 배선**했습니다. 다만 **기본은 꺼져 있습니다(profile-gated)** — 평소 `docker compose up`에 안 뜨고, 명시적으로 켜야만 뜨며, 켜도 **기본은 안전한 dry-run**(실제 쓰기 0)이고, 운영 DB가 준비 안 됐으면 자동으로 건너뜁니다. 자동 합치기는 계속 0.
- **이번 턴에 실제로 끝낸 것:** ADR#51 커밋(`4fdd263`) → **ADR#52 구현**: docker `semantic-backfill-scheduler` 서비스(profile-gated·dry-run default·preflight gated·단일 instance)·운영 배포 순서 runbook(docker 활성 단계 추가)·compose 일관성 테스트 5. **코드(파이썬) 변경 0** — docker-compose.dev.yml + 테스트 + 문서만. 측정: backend 비-live **459p/4s/0f**(신규 compose 5 포함)·ingestion **1353p**·frontend tsc0/test12/lint0(live-PG는 docker 미가동으로 이번 턴 미재실행). adversarial-reality-critic **VALID**(MEDIUM 2건 정정). 옵션 C(인덱스)·D(동시성 lock)는 **근거와 함께 보류**(아래).
- **정직한 한계:** 여전히 **능력**입니다 — scheduler는 **실가동 0**(profile 비활성·운영 DB 0003·flag off). docker 정의는 build/up으로 검증하지 않았습니다(정적 일관성 테스트 + `--help` 명령 검증만). `production 백로그는 0`. 실 reviewer/gold/병합 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `4fdd263`**(ADR#51, 본 턴 첫 커밋) 위 **ADR#52 = 미커밋 config 1 + tests 1 + docs 8 = 10파일**. **migration 없음**. **신규 파일 0**(전부 기존 파일 수정). 파이썬 source 모듈 변경 0.
- 변경: `docker-compose.dev.yml`(신규 서비스 `semantic-backfill-scheduler`·profile-gated·dry-run default) + `backend/tests/test_backfill_scheduler_ops.py`(compose 일관성 테스트 5) + docs 8.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전(gap② docker scaffold)**(scheduler docker 배선·profile-gated·dry-run default·미가동; 운영 DB 배포·실 fetch·profile 활성+--persist 가동·index/lock 잔여) · R-RealSourceLoopUnproven · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (production scheduler activation readiness — ADR#52)
- **① ADR#51 커밋**: 13파일 → `4fdd263`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석(20문항)**: (핵심) **worker 이미지로 scheduler 배선 불가** — workers/Dockerfile은 `backend/app/{services,tools,models}` 미COPY(import 실패) → **backend 이미지**(전체 backend) + `entrypoint` override(entrypoint.sh의 alembic+uvicorn 우회) + `DATABASE_URL` env 필요. compose v2 `profiles:` = 기본 `up` 미기동(정확한 "scaffold but disabled" 해법). `ready_for_stage3=all(tables_present)` = **테이블 존재** 기반(head 동등성 아님) → index migration 추가해도 0009 DB stage3 gate 무손상. `.env.example` 충분(scheduler 모드=CLI flag·신규 env 불필요).
- **③ docker scaffold**(옵션 A·채택): compose 서비스 `semantic-backfill-scheduler` — `profiles:["backfill"]`(기본 미기동)·`build: backend/Dockerfile`·`entrypoint:[python,-m,workers.tools.run_semantic_backfill_scheduler]`·`command:[--interval-sec 300,--limit 100,--cursor-mode created_at]`(**--persist 없음=dry-run default**)·`DATABASE_URL`(dev event_intel — safe-target 는 이 경로 no-op·안전=dry-run+preflight·MEDIUM-1)·`depends_on: postgres healthy`·`restart:"no"`(단일 runner 규율).
- **④ 옵션 C/D DEFER(근거)**: **C(created_at index)** — backlog 0·prod 0003에서 순수 미래-스케일 최적화인데 추가 시 `test_identity_backlog_readiness`(behind_count 9·6 하드코딩)·`test_event_resolution_live_pg:1289`(expected_head 하드코딩) 깨짐+test DB upgrade 필요 → **현 이득 0·실 test churn** → DDL(`ix_event_links_created_at_id (created_at,id)`) runbook 문서화. **D(advisory lock)** — 데이터 안전 이미 보장(link_id PK upsert·중복행 0) + docker 단일 runner 운영 규율 가정 → lock은 중복 work(성능) defense-in-depth → single-instance **규율**(물리적 차단 아님·`--scale`/수동 CLI 병행 우회 가능) runbook 명시. **둘 다 별도 RISK 미등록**(현 blocker 아님·directive §6/§7 sanctioned). **E(운영 DB upgrade) 금지**(승인 없음).
- **⑤ runbook + 일관성 테스트**: runbook (B) step10(docker 활성 순서·--persist 전환)·RealSourceLoop row6(scheduler PARTIAL=docker scaffold)·index DDL 문서화. compose 일관성 5: 서비스 존재·profile-gated(`["backfill"]`)·**--persist 부재(dry-run default)**·entrypoint=scheduler 모듈(uvicorn 부재)·DATABASE_URL+postgres dep·단일 instance(replicas None/1·restart no). scheduler `--help`(DB 무접근)로 entrypoint 명령 유효성 검증.
- **adversarial 평결**: adversarial-reality-critic **VALID(정직성 양호)** — 4대 안전계약(자동 병합 0·dry-run default·profile-gated·운영 DB 무단 upgrade 0) **전부 성립**(entrypoint override 가 alembic+uvicorn 실제 대체→무단 마이그레이션 0)·HIGH 0·코드 버그 0·index/lock DEFER 근거 실재. **지적 2건 정정**: **MEDIUM-1**(scheduler APP_ENV 부재+DATABASE_URL=dev event_intel→`assert_safe_write_target` 가 이 경로엔 **사실상 no-op**·안전은 dry-run+preflight 책임)→compose 주석·runbook step10·docs 정정(실 persist 가동 선결=별도 운영 DB+`APP_ENV=production`+`--allow-non-dev-db`); **MEDIUM-2**("단일 instance 차단"→"단일 runner 규율 가정"·`--scale`/수동 CLI 병행 우회 가능·데이터 안전 무관)→정정. LOW(build/up 미입증·live-PG 회귀근거)→정직 표기 유지.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48·incremental/no-cluster ADR#49·keyset/CLI ADR#50·preflight/exit/created_at cursor ADR#51·docker scaffold ADR#52**) → ④ 실 병합(**미구현**). **④ 전 선결 = eval gate(ADR#43)+gold(ADR#44)+reviewer(ADR#45)+packet(ADR#46)+live pilot(ADR#47)+stage③ wiring(ADR#48)+incremental(ADR#49)+keyset/CLI(ADR#50)+scheduler-ready(ADR#51)+docker scaffold(ADR#52)**.
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·**실제 profile 활성+--persist docker 가동**·전수 report 경로 keyset·created_at index·advisory lock·실 병합·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE. "배선(능력) ≠ production(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: backfill/scheduler는 Intelligence Unit **merge safety substrate**(자동 병합 0·read+adjudication upsert only·preflight/exit/cursor/scheduler/docker 전부 internal·public API 미노출). `INTELLIGENCE_UNIT_CONTRACT §4`에 ADR#52 노트 추가. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(gap② docker scaffold): R-LiveIdentityBacklog**(scheduler docker 배선·profile-gated·dry-run default·preflight gated·단일 instance DONE; 운영 DB 배포·실 fetch·profile 활성+--persist 가동·index/lock·실 gold/merge 잔여·완전종결 금지).
- **R-BackfillSchedulerOps/R-BackfillConcurrency/R-BackfillCursorIndex 미등록**(docker scaffold 존재·동시성 단일 runner 규율 가정[물리 차단 아님]·index DEFER 문서화·R-LiveIdentityBacklog 교차 추적·RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·deploy checklist 작성됨·미실행) + flag on + 실 fetch 필요 → 능력 DONE·production 0.
- **실제 docker 주기 서비스 가동**: scheduler가 docker로 **배선됨**(profile-gated·dry-run default)·**실가동 0**(profile 비활성·운영 DB 0003·flag off·--persist 미지정·운영 DB 후 게이트·승인 필요·이월). docker build/up 미검증(정적 일관성 테스트만·이월).
- **created_at 인덱스(C)**: backlog 0·prod 0003 상태에서 순수 미래-스케일 최적화 → DDL 문서화·미적용(적용 시점=백로그 유의미·test churn 회피·이월).
- **동시 work 회피(D)**: 데이터 멱등 안전(PK upsert·중복행 0) + docker 단일 runner **규율 가정**(물리 차단 아님·`--scale`/수동 CLI 병행 우회 가능)·advisory lock 미구현(OS-병렬 race stress-test 없음·이월).
- **safe-target 실 보호막(MEDIUM-1)**: dev/운영 공유 `event_intel`·scheduler APP_ENV=dev 상속이라 safe-target 이 컨테이너 경로엔 no-op → 실 persist 운영 활성 전 별도 운영 DB+`APP_ENV=production`+`--allow-non-dev-db` 필요(이월).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위·승인 필요) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#52 config 1 + tests 1 + docs 8 (총 10파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(deploy checklist) + flag on → **docker profile 활성**(`docker compose --profile backfill up`) + dry-run 검증 → command에 `--persist` 추가 가동 + `(created_at,id)` cursor 인덱스 migration(0010) + advisory lock → 실 cross-source fetch 볼륨 → 다중 reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `4fdd263`(ADR#51). 변경: `docker-compose.dev.yml`(`semantic-backfill-scheduler` profile-gated·dry-run default)·`test_backfill_scheduler_ops`(compose 일관성 5)·docs 8.
- 검증(정직): backend 비-live(`test_event_resolution_live_pg`+`test_seed_event_timeline` 제외) **459 passed / 4 skipped / 0 failed**(신규 compose 5 포함·961s — docker 미가동 연결 타임아웃으로 느렸으나 완주·0 실패; baseline "473"과 차이는 본 측정이 seed 비-live 테스트까지 추가 제외) · ingestion **1353 passed** · frontend tsc **0**/node:test **12**/lint **0**. **live-PG(91p)는 docker(PG) 미가동으로 이번 턴 미재실행**(live-PG 코드 경로·기존 compose 서비스 정의 미변경→회귀 risk 0). scheduler `--help` 명령 유효성(DB 무접근). **`docker compose config`(데몬 불필요): default 서비스 목록에 scheduler 부재·`--profile backfill` 에만 포함 → profile 격리 docker 실증.**
- 문서: ADR#52(`_DECISIONS`)·R-LiveIdentityBacklog gap②(`_RISK/RISK_REGISTER`)·runbook step10+RealSourceLoop 표+index DDL(`2_ROADMAP/15`)·`_CANONICAL/02`·`2_ROADMAP/00`·`RAG_KG_AGENT_READINESS`·`INTELLIGENCE_UNIT_CONTRACT §4`.

---
_as_of: 2026-06-25 · ADR#52 production scheduler activation readiness — docker `semantic-backfill-scheduler` 서비스(`profiles:["backfill"]` 기본 미기동·`build: backend/Dockerfile`·entrypoint override[alembic+uvicorn 대신 scheduler 모듈]·`command` --persist 부재=**dry-run default**·`DATABASE_URL`·`depends_on: postgres healthy`·`restart:"no"` 단일 instance). 옵션 A(채택)·C(created_at index DEFER·근거: backlog 0·prod 0003·test churn 회피·DDL runbook 문서화)·D(advisory lock DEFER·근거: 데이터 안전+단일 instance 운영 차단·single-instance runbook)·E(운영 DB upgrade 금지). **코드(파이썬) 변경 0** — docker-compose.dev.yml + compose 일관성 테스트 5 + docs 8. runbook (B) step10(docker 활성)·RealSourceLoop row6·index DDL 문서화. **측정(정직): backend 비-live(live-PG 2파일 제외) 459p/4s/0f(신규 compose 5 포함)·ingestion 1353p·frontend tsc0/test12/lint0·scheduler --help·`docker compose config`(default 목록 scheduler 부재·--profile 시 포함); live-PG(91p)는 docker(PG) 미가동으로 이번 턴 미재실행(코드 경로·기존 서비스 정의 미변경→회귀 risk 0).** **adversarial-reality-critic: VALID(정직성 양호)** — 4대 안전계약(자동 병합 0·dry-run default·profile-gated·운영 DB 무단 upgrade 0) 전부 성립(entrypoint override 가 alembic+uvicorn 실제 대체)·HIGH 0·코드 버그 0·index/lock DEFER 근거 실재. 지적 2건 정정: MEDIUM-1(safe-target 이 dev event_intel 경로엔 no-op→안전은 dry-run+preflight·실 persist 가동 선결 별도 운영 DB+APP_ENV=production+--allow-non-dev-db)·MEDIUM-2("단일 instance 차단"→"단일 runner 규율 가정"·--scale/수동 CLI 우회 가능). **R-LiveIdentityBacklog 부분진전(gap② docker scaffold)**·완전종결=OVERCLAIM·신규 RISK 3종 미등록(교차추적·남발 금지). scheduler 실가동 0(profile 비활성·운영 DB 0003·flag off)·docker build/up 미검증(정적 일관성 테스트만) → **production 백로그 0**. ADR#51 커밋 `4fdd263` 위 ADR#52 미커밋(config 1+tests 1+docs 8=10파일)·커밋 지시 대기·push 안 함._
