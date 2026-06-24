# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 밀린 검수 후보 판정(③)을 **운영에서 안전하게 돌릴 수 있게** 다듬었습니다. ① 백로그를 한 번에 정해진 양·정해진 위치(cursor)부터 처리하도록 페이지 단위로 끊고(메모리 절약), ② 그걸 **명령 한 줄로 실행**하는 운영 도구(`--limit/--after-link-id/--dry-run`)를 붙이고, ③ 운영 DB를 올리는 **배포 체크리스트**(백업 필수·명령 문자열·실행은 안 함)를 만들었습니다. 자동 합치기는 계속 0.
- **이번 턴에 실제로 끝낸 것:** ADR#49 커밋(`1d56054`) → **ADR#50 구현**: keyset 페이지네이션(`after_link_id`·SQL push) + backfill 운영 CLI + `build_operational_deploy_checklist` + readiness CLI. 측정: **backend 비-live 459p/4s · live-PG 82p · ingestion 1353p · frontend tsc0/test12/lint0**(신규 7). adversarial: ambiguity 핵심 **VALID(날조 없음)**, **정직성 3건 정정**(아래).
- **정직한 한계:** 여전히 **능력**입니다 — 운영 DB는 0003(미적용), 실 fetch 0, 주기 서비스 미배선이라 **production 백로그는 0**. cursor는 UUID라 "시간순"이 아니라 재현용 페이지 경계(진행 보장은 "미판정만" 필터가 담당). 동시 실행은 데이터는 안전(중복행 0)하나 OS-병렬 race는 stress-test 안 됨. 실 reviewer/gold/병합 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `1d56054`**(ADR#49, 본 턴 첫 커밋) 위 **ADR#50 = 미커밋 code 3 + tests 2 + docs 8 = 13파일**. **migration 없음**.
- code: `semantic_identity_adjudicator.py`(keyset — `_semantic_links(after_link_id=,only_unadjudicated=,limit=)`가 `WHERE id>cursor·NOT IN·LIMIT`를 SQL push·ambiguity는 `_candidate_target_counts` page-scoped GROUP BY로 동작 보존·unused `_adjudicated_link_ids` 제거) + `backfill_semantic_adjudications.py`(`after_link_id`·`__main__` CLI·safe-target 가드·next_cursor/full_scan/idempotent_persist) + `identity_backlog_readiness.py`(`build_operational_deploy_checklist`·read-only CLI). tests: `test_identity_backlog_readiness`[+3 deterministic] + `test_event_resolution_live_pg`[+4 live-PG]. docs 8.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전(gap③④ 추가)**(keyset·backfill CLI·deploy checklist·scheduler 관용구 식별 DONE; 운영 DB 배포·실 fetch·실제 docker 주기 서비스·전수 report keyset·실 gold/merge 잔여) · R-RealSourceLoopUnproven · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (backfill operation hardening + deploy checklist — ADR#50)
- **① ADR#49 커밋**: 13파일 → `1d56054`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석**: scheduler 인프라 광역 조사로 직전 "scheduler 없음" **사실 오류 정정** — `run_recovery_scheduler.py`(`--interval-sec`/`--once`·docker `recovery-scheduler`)·Redis consumer 2종 **존재**(Celery 설치만·task/beat 0). private 헬퍼 외부 import 0(keyset 재작성 안전). `event_links.id`=UUIDv4.
- **③ keyset**(옵션 A): `_semantic_links`가 `after_link_id`/`only_unadjudicated`/`limit`을 SQL로 push(전 link 적재 회피). ambiguity는 in-memory map 대신 `_candidate_target_counts`(page candidate 한정 GROUP BY·각 candidate 전 target 집계)→cursor/필터/limit 무관 **link별 status 동작 보존**(기존 78 live-PG 무회귀).
- **④ backfill 운영 CLI**(옵션 A): `--limit/--after-link-id/--dry-run/--allow-non-dev-db`·`assert_safe_write_target` 가드(dev/test만·fail-closed)·`asyncio.run`·utf-8 stdout. report에 `next_cursor`·`full_scan`·`idempotent_persist`.
- **⑤ deploy checklist + readiness CLI**(옵션 A+C): `build_operational_deploy_checklist`(순수·0003→head 명령 문자열·`backup_required=True`·`executed=False`) + `python -m …identity_backlog_readiness`(read-only·DDL 0). 주기 가동=기존 `run_recovery_scheduler --once` 관용구 **재사용 가능**(옵션 B=runbook 한정·미배선·운영 DB 후 게이트). 옵션 C(즉시 upgrade)·D(실 fetch smoke) 미수행.
- **⑥ 측정(정직)**: live-PG keyset cursor(after_link_id→cursor 초과만·모호성 정확)·교차 2-세션 backfill 중복행 0·실 readiness→deploy checklist(backup_required·executed=False)·full_scan/next_cursor report.
- **adversarial 평결**: ambiguity 핵심 **VALID**(page 분할·partial 선판정·cursor 제외 공격 무효화·날조 없음)·no-merge·NOT IN·deploy checklist·full_scan VALID. **정직성 3건 정정(commit 전)**: HIGH② UUIDv4 cursor "단조" 거짓→"byte 순서·시간순 아님·진행은 only_unadjudicated" 정정. HIGH③ 동시성 테스트 약함→2-link 강화+"중복-persist 멱등(OS-race 미stress-test)" 재명명. MEDIUM⑧ scheduler "재사용한다"→"재사용 가능(미배선)" 정정.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48·incremental/no-cluster backfill ADR#49·keyset/운영 CLI ADR#50**) → ④ 실 병합(**미구현**). **④ 전 선결 = eval gate(ADR#43)+gold workflow(ADR#44)+reviewer agreement(ADR#45)+labeling packet(ADR#46)+live packet pilot(ADR#47)+stage③ wiring(ADR#48)+incremental/backfill(ADR#49)+backfill hardening(ADR#50)**.
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·실제 docker 주기 서비스 가동·전수 report 경로 keyset·실 병합·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE. "배선(능력) ≠ production(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: backfill/scheduler는 Intelligence Unit **merge safety substrate**(자동 병합 0·read+adjudication upsert only). `INTELLIGENCE_UNIT_CONTRACT §4`에 keyset/CLI/deploy checklist 노트 추가(정직 경계 포함). final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(gap③④ 추가): R-LiveIdentityBacklog**(keyset·backfill 운영 CLI·deploy checklist·readiness CLI·scheduler 관용구 식별 DONE; 운영 DB 배포·실 fetch·실제 주기 서비스·전수 report keyset·동시 work 회피 잔여·완전종결 금지).
- **R-BackfillSchedulerOps/R-BackfillConcurrency/R-BackfillKeysetCost/R-OperationalDbDeployment 미등록**(scheduler 관용구 존재·동시성 멱등 안전·keyset 완화·운영 DB 배포는 R-LiveIdentityBacklog/R-RealSourceLoopUnproven 교차 추적·RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·deploy checklist 작성됨·미실행) + flag on + 실 fetch 필요 → 능력 DONE·production 0.
- **실제 주기 서비스**: scheduler 관용구(`run_recovery_scheduler --once`) **식별**·backfill CLI entry 준비됨·docker 서비스 미배선(운영 DB 후 게이트·이월).
- **cursor 시간순 / 전수 report keyset**: cursor=UUIDv4 byte 순서(시간순 아님)·`full_scan` 전수 경로는 여전히 전체 scan(`(created_at,id)` 복합 cursor는 이월).
- **동시 work 회피**: 데이터는 멱등 안전이나 중복 work 회피(직렬화/advisory lock)·OS-병렬 race stress-test 미구현(이월).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위·승인 필요) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#50 code 3 + tests 2 + docs 8 (총 13파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(deploy checklist) + flag on + backfill dry-run/limited → 실제 docker 주기 서비스 배선(`run_recovery_scheduler` 식)·`(created_at,id)` 복합 cursor·동시 work 직렬화 → 실 cross-source fetch 볼륨 → 다중 reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `1d56054`(ADR#49). 코드: `semantic_identity_adjudicator`(keyset)·`backfill_semantic_adjudications`(cursor+CLI)·`identity_backlog_readiness`(deploy checklist+CLI).
- 검증: backend 비-live **459p/4s** · live-PG **82p**(keyset/cursor/교차 backfill/deploy checklist 4) · ingestion **1353p** · frontend tsc0/test12/lint0. 신규 7(deterministic 3 + live-PG 4). 측정: cursor 초과만·중복행 0·deploy checklist backup_required·executed False·full_scan/next_cursor.
- 문서: ADR#50(`_DECISIONS`)·R-LiveIdentityBacklog gap③④(`_RISK/RISK_REGISTER`)·runbook CLI+RealSourceLoop 표(`2_ROADMAP/15`)·`_CANONICAL/02`·`2_ROADMAP/00`·`RAG_KG_AGENT_READINESS`·`INTELLIGENCE_UNIT_CONTRACT §4`.

---
_as_of: 2026-06-24 · ADR#50 backfill operation hardening + deploy checklist + scheduler idiom. keyset: `_semantic_links(after_link_id=,only_unadjudicated=,limit=)`가 `WHERE id>cursor·NOT IN adjudication·LIMIT`를 SQL push(전 link 적재 회피)·ambiguity는 `_candidate_target_counts`(page candidate 한정 GROUP BY·전 target 집계)로 cursor/필터 무관 link별 status 동작 보존·unused `_adjudicated_link_ids` 제거. backfill 운영 CLI(`--limit/--after-link-id/--dry-run/--allow-non-dev-db`·safe-target·next_cursor/full_scan/idempotent_persist). `build_operational_deploy_checklist`(0003→head 명령·backup_required·executed=False)+readiness read-only CLI. 주기 가동=기존 `run_recovery_scheduler --once` 관용구 재사용 가능(설계·미배선). **측정(정직): backend 비-live 459p/4s·live-PG 82p(keyset cursor·교차 backfill 중복행 0·deploy checklist·full_scan/next_cursor)·ingestion 1353p·frontend tsc0/test12/lint0·신규 7. 기존 78 live-PG 무회귀.** 옵션 A+B(runbook)·C/D 미수행. **adversarial: ambiguity 핵심 VALID(날조 없음)·정직성 3건 정정 — ②UUIDv4 cursor "단조" 거짓→"시간순 아님·진행은 only_unadjudicated", ③동시성 테스트 2-link 강화+재명명(OS-race 미stress-test), ⑧scheduler "재사용한다"→"재사용 가능(미배선)".** **R-LiveIdentityBacklog 부분진전(gap③④ 추가)**·완전종결=OVERCLAIM·신규 RISK 4종 미등록(해소/교차추적·남발 금지). cursor=UUIDv4 byte 순서(시간순 아님)·scheduler 미배선·운영 DB 0003 미적용·실 fetch 0 → **production 백로그 0**. ADR#49 커밋 `1d56054` 위 ADR#50 미커밋(code 3+tests 2+docs 8=13파일)·커밋 지시 대기·push 안 함._
