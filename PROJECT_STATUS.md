# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 밀린 검수 후보 판정(③) backfill을 **주기 운영 job으로 안전하게 돌릴 준비**를 끝냈습니다. ① 실행 전 **안전 점검(preflight)** — 운영 DB가 준비됐는지·기능 스위치가 켜졌는지 확인하고, 미준비면 **건너뛰고 에러코드로 알림**(잘못 돌려 죽는 일 방지), ② **오래된 백로그부터** 처리하도록 시간순 cursor 추가(`created_at`), ③ 이걸 주기로 돌리는 **scheduler 스크립트**(다만 기본은 안전한 dry-run·아직 자동 가동 안 함). 자동 합치기는 계속 0.
- **이번 턴에 실제로 끝낸 것:** ADR#50 커밋(`bc8e670`) → **ADR#51 구현**: preflight gate(readiness/flag)·deterministic exit code(0/1/2/3)·`created_at` 시간순 cursor·`run_semantic_backfill_scheduler.py`(gated·dry-run default·docker 미배선). 측정: **backend 비-live 473p/4s · live-PG 91p · ingestion 1353p · frontend tsc0/test12/lint0**(신규 23). adversarial: **기술 안전 계약 전부 VALID(정직)**, 지적 4건 전부 처리(아래).
- **정직한 한계:** 여전히 **능력**입니다 — 운영 DB는 0003(미적용), 실 fetch 0, scheduler 미가동이라 **production 백로그는 0**. `created_at` cursor는 **배치 간**만 시간순(같은 배치 내는 임의·인덱스 없어 정렬 비용). 동시 실행은 데이터 안전(중복행 0)하나 advisory lock 미구현(중복 work 가능·OS-race 미stress-test). 실 reviewer/gold/병합 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `bc8e670`**(ADR#50, 본 턴 첫 커밋) 위 **ADR#51 = 미커밋 code 3 + tests 2 + docs 8 = 13파일**. **migration 없음**. 신규 파일: `workers/tools/run_semantic_backfill_scheduler.py`·`backend/tests/test_backfill_scheduler_ops.py`.
- code: `semantic_identity_adjudicator.py`(`cursor_mode`[id|created_at]·`or_/and_` 복합 cursor·`AdjudicationResult.link_created_at`·`_semantic_links` 4-tuple) + `backfill_semantic_adjudications.py`(`backfill_preflight`·`decide_exit_code`·`run_backfill_with_preflight`/`run_backfill_session` 공유·`after_created_at`/`cursor_mode` report·CLI preflight+exit code) + `run_semantic_backfill_scheduler.py`(recovery-scheduler 관용구·gated·dry-run default). tests: `test_backfill_scheduler_ops`[+14 deterministic] + `test_event_resolution_live_pg`[+9 live-PG]. docs 8.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전(gap④ scheduler-ready+cursor)**(preflight·exit code·created_at cursor·scheduler 스크립트 DONE; 운영 DB 배포·실 fetch·실제 docker 주기 서비스 가동·전수 report keyset·실 gold/merge 잔여) · R-RealSourceLoopUnproven · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`·`frontend/.harness/`(gitignored).

## ✅ 이번 턴에 달성한 것 (backfill scheduler operationalization — ADR#51)
- **① ADR#50 커밋**: 13파일 → `bc8e670`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석(20문항)**: (핵심 발견) `event_links.created_at` **이미 존재**(server_default now()) → migration 없이 `(created_at,id)` 시간순 cursor 가능(직전 "시간순 불가" 정정). created_at 인덱스 없음(0005 확인·정렬 비용)·intra-txn tie→id. scheduler 관용구(recovery-scheduler)·Celery 설치만·advisory lock 선례 0·flag 기본 off·0003은 adjudication 테이블 부재→쿼리 크래시.
- **③ preflight gate**(옵션 A): `backfill_preflight`+`run_backfill_with_preflight` — `ready_for_stage3` **hard gate**(0003에서 dry-run 포함 차단·크래시 방지) + flag **persist gate**(`EVENT_SEMANTIC_ADJUDICATION_ENABLED` off면 persist만 차단·dry-run 허용·`allow_flag_off` 우회).
- **④ exit code + 공유 진입점**(옵션 A): `decide_exit_code` 0=성공/1=blocked/2=runtime/3=dry-run pending(scheduler/cron 결정론·recovery-scheduler convention). `run_backfill_session`/`decide_exit_code` public 승격(CLI·scheduler 공유·순환 0).
- **⑤ created_at 시간순 cursor**(옵션 §5): `cursor_mode='created_at'` → `or_(created_at>cur, and_(created_at==cur, id>after_link_id))` 컬럼 비교(행값 `tuple_`는 우변 UUID 타입강제 실패 'uuid>varchar'→교체·동치)·`next_created_at` report → 오래된 백로그 우선(default `id`·하위호환).
- **⑥ scheduler 스크립트**(옵션 B·제한): `workers/tools/run_semantic_backfill_scheduler.py`(recovery-scheduler `--once`/`--interval-sec` 관용구 복제·preflight gated·**dry-run default·--limit 기본 100·docker 미배선·미가동**). 옵션 C(advisory lock) 거부·문서화. D(운영 upgrade) 금지.
- **adversarial 평결**: adversarial-reality-critic **기술 안전 계약 전부 VALID(정직)** — 자동 병합 0(event_count 불변)·dry-run default(--persist 없으면 영속 0)·scheduler docker 미배선(grep)·lock 미과대주장·preflight hard gate 실차단·exit code 정직·created_at intra-batch 임의 docstring 정직(0005 인덱스 부재 교차검증)·복합 cursor 동치. **지적 4건 처리**: HIGH-A(ADR#51 docs 미등록)→`_DECISIONS [#51]`+RISK_REGISTER 등록; HIGH-B(PROJECT_STATUS 복합cursor "이월" 모순)→본 갱신; MEDIUM(tie-break·0003 차단 실DB 미검증)→**live-PG 2건 추가**(동일 created_at tie-break resume·테이블 DROP block); LOW(help)→CLI/scheduler help 정정. 구현 중 복합 cursor `uuid>varchar` 버그 **self-found+fixed**.

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48·incremental/no-cluster ADR#49·keyset/CLI ADR#50·scheduler-ready preflight/exit/created_at cursor ADR#51**) → ④ 실 병합(**미구현**). **④ 전 선결 = eval gate(ADR#43)+gold(ADR#44)+reviewer agreement(ADR#45)+packet(ADR#46)+live pilot(ADR#47)+stage③ wiring(ADR#48)+incremental/backfill(ADR#49)+keyset/CLI(ADR#50)+scheduler-ready(ADR#51)**.
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·실제 docker 주기 서비스 **가동**·전수 report 경로 keyset·실 병합·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE·advisory lock. "배선(능력) ≠ production(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: backfill/scheduler는 Intelligence Unit **merge safety substrate**(자동 병합 0·read+adjudication upsert only·preflight/exit/cursor/scheduler 전부 internal·public API 미노출). `INTELLIGENCE_UNIT_CONTRACT §4`에 ADR#51 노트 추가. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(gap④ scheduler-ready+cursor): R-LiveIdentityBacklog**(preflight·exit code·created_at cursor·scheduler 스크립트 DONE; 운영 DB 배포·실 fetch·실제 주기 서비스 가동·전수 report keyset·실 gold/merge 잔여·완전종결 금지).
- **R-BackfillSchedulerOps/R-BackfillConcurrency/R-BackfillCursorSemantics 미등록**(scheduler 스크립트 존재·동시성 데이터 안전·cursor 한계 문서화·R-LiveIdentityBacklog 교차 추적·RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·deploy checklist 작성됨·미실행) + flag on + 실 fetch 필요 → 능력 DONE·production 0.
- **실제 주기 서비스 가동**: scheduler 스크립트(`run_semantic_backfill_scheduler.py`) **작성·gated**·docker 서비스 미배선·미가동(운영 DB 후 게이트·승인 필요·이월).
- **전수 report keyset / cursor 인덱스**: `full_scan` 전수 경로(limit/cursor 미지정)는 여전히 전체 scan·created_at cursor는 **배치 간**만 정확(intra-txn tie→id 임의)·created_at 인덱스 없음(정렬 비용·미래 선택적 migration·이월).
- **동시 work 회피**: 데이터는 멱등 안전이나 중복 work 회피(advisory lock/직렬화)·OS-병렬 race stress-test 미구현(단일 instance scheduler/disjoint cursor 권고·이월).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위·승인 필요) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#51 code 3 + tests 2 + docs 8 (총 13파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(deploy checklist) + flag on + scheduler dry-run 검증 → **실제 docker 주기 서비스 배선·가동**(`run_semantic_backfill_scheduler --persist --interval-sec`) + `(created_at,id)` cursor 인덱스 migration + advisory lock(중복 work 직렬화) → 실 cross-source fetch 볼륨 → 다중 reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `bc8e670`(ADR#50). 코드: `semantic_identity_adjudicator`(cursor_mode)·`backfill_semantic_adjudications`(preflight+exit code+공유 진입점)·`run_semantic_backfill_scheduler`(신규·gated).
- 검증: backend 비-live **473p/4s** · live-PG **91p**(created_at 시간순·복합/tie-break resume·0003 차단·preflight gate·Event 불변) · ingestion **1353p** · frontend tsc0/test12/lint0. 신규 **23**(deterministic 14 + live-PG 9). 측정: created_at 순서≠id 순서·tie-break 중복0·테이블 DROP block readiness·flag on/off persist gate·exit code 0/1/2/3.
- 문서: ADR#51(`_DECISIONS`)·R-LiveIdentityBacklog gap④(`_RISK/RISK_REGISTER`)·runbook scheduler step+RealSourceLoop 표(`2_ROADMAP/15`)·`_CANONICAL/02`·`2_ROADMAP/00`·`RAG_KG_AGENT_READINESS`·`INTELLIGENCE_UNIT_CONTRACT §4`.

---
_as_of: 2026-06-25 · ADR#51 backfill scheduler operationalization — preflight gate(readiness ready_for_stage3 hard gate + flag persist gate·`backfill_preflight`/`run_backfill_with_preflight`)·deterministic exit code(`decide_exit_code` 0=성공/1=blocked/2=runtime/3=dry-run pending)·`created_at` 시간순 cursor(`cursor_mode='created_at'`·`or_(created_at>cur, and_(created_at==cur, id>after_link_id))`·행값 tuple_ uuid>varchar 교체·`next_created_at`)·scheduler 스크립트(`workers/tools/run_semantic_backfill_scheduler.py`·recovery-scheduler 관용구·gated·dry-run default·--limit 기본 100·docker 미배선). 공유 진입점 `run_backfill_session`/`decide_exit_code` public. **측정(정직): backend 비-live 473p/4s·live-PG 91p(created_at 시간순·tie-break resume·0003 테이블 DROP block·preflight gate·Event 불변)·ingestion 1353p·frontend tsc0/test12/lint0·신규 23(deterministic 14+live-PG 9).** 옵션 A+B(scheduler 미배선)·C(advisory lock 거부·문서화)·D(운영 upgrade 금지). **adversarial: 기술 안전 계약 전부 VALID(정직)·지적 4건 처리(HIGH-A docs 미등록→_DECISIONS [#51]+RISK 등록·HIGH-B PROJECT_STATUS 모순→본 갱신·MEDIUM tie-break/0003→live-PG 2건 보강·LOW help 정정)·복합 cursor uuid>varchar 버그 self-found+fixed.** **R-LiveIdentityBacklog 부분진전(gap④)**·완전종결=OVERCLAIM·신규 RISK 3종 미등록(교차추적·남발 금지). created_at cursor 배치 간만 정확·인덱스 없음·scheduler 미가동·운영 DB 0003·실 fetch 0 → **production 백로그 0**. ADR#50 커밋 `bc8e670` 위 ADR#51 미커밋(code 3+tests 2+docs 8=13파일)·커밋 지시 대기·push 안 함._
