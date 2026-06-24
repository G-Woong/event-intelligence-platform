# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 라이브 후보가 운영에서 **자동으로 쌓이지 않던 근본 원인**(단계 ③ "판정" 작업이 운영 루프에 연결 안 됨)을 **연결**했습니다. 이제 수집 배치가 끝나면 결정론 판정이 자동 실행돼 검수 후보 백로그가 쌓이고, 그 결과 작업지(packet)가 **수동 조작 없이** 운영 후보를 읽습니다(스위치 off 기본·자동 합치기 0). 또 운영 DB가 **얼마나 뒤처졌는지**(6단계)를 읽기 전용으로 진단합니다.
- **이번 턴에 실제로 끝낸 것:** ADR#47 커밋(`9d466c4`) → **ADR#48 구현**: `ingest_records_to_events`에 단계 ③ 운영 배선(flag `EVENT_SEMANTIC_ADJUDICATION_ENABLED`·off-by-default) + 신규 `identity_backlog_readiness.py`(운영 DB 0003 vs head 0009 **6 revision 뒤·non-destructive** 정량화). 측정: **backend 비-live 455p/4s · live-PG 71p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial **JUSTIFIED**(안전 견고).
- **정직한 한계:** 이번 턴은 **배선(능력)**입니다 — 운영 DB는 여전히 0003(미적용)이고 실 fetch도 0이라 **production 백로그는 여전히 0**입니다(flag on + 운영 DB 0009 배포 + 실 fetch 선결). 실 reviewer 합의·gold·병합은 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `9d466c4`**(ADR#47, 본 턴 첫 커밋) 위 **ADR#48 = 미커밋 code 3(`event_ingest_pipeline.py` stage③ 배선 + `config.py` flag + 신규 `identity_backlog_readiness.py`) + config 1(`.env.example`) + tests 3(신규 `test_identity_backlog_readiness.py` + `test_event_ingest_pipeline`[+1] + `test_event_resolution_live_pg`[+5]) + docs 8**. **migration 없음**.
- code: `event_ingest_pipeline.ingest_records_to_events(adjudicate_semantic=)` — 클러스터 루프 뒤 flag on 이면 `adjudicate_semantic_links`(③) 배치 전역 1회 자동 실행(`summary.adjudications`·try/except 격리·자동 병합 0·shadow write only·멱등). `config.EVENT_SEMANTIC_ADJUDICATION_ENABLED`(off-by-default) + `.env.example`. 신규 `identity_backlog_readiness.py`(read-only: `load_migration_chain`/`compute_migration_gap`/`pending_destructive`[upgrade 본문만]/`operational_db_readiness`). `build_live_identity_labeling_packet.py` read-only 유지(write 미추가). docs: ADR#48(`_DECISIONS`)·RISK_REGISTER(R-LiveIdentityBacklog 부분진전·R-RealSourceLoopUnproven)·RAG_KG_AGENT_READINESS·CANONICAL/02·ROADMAP{00,15}·PROJECT_STATUS.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전**(stage③ 배선[flag]·migration readiness DONE·운영 DB 배포·실 fetch·주기 job·incremental 잔여) · R-RealSourceLoopUnproven(운영 DB 0003 정량화) · R-SemanticIdentityAdjudicator·R-IdentityEvalDataset·R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (stage③ operational wiring + migration readiness — ADR#48)
- **① ADR#47 커밋**: 12파일 → `9d466c4`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석(probe)**: live_selected 운영 0 의 3중 근본 확정 — ⓐ 운영 DB `event_intel` **0003**(head 0009 대비 6 뒤·event/identity 테이블 부재) ⓑ 단계 ③ adjudication **live 루프 미배선**(production 호출자 0) ⓒ synthetic 측정.
- **③ stage③ operational wiring**(옵션 A): `ingest_records_to_events(adjudicate_semantic: Optional[bool]=None)` — 클러스터 루프(② link commit) 뒤 flag(`EVENT_SEMANTIC_ADJUDICATION_ENABLED`, off-by-default) on 이면 `adjudicate_semantic_links(session, persist=True)`(③) 배치 전역 1회 자동 실행. **자동 병합 0**(③ = event_links/events/event_updates **read** + event_identity_adjudication **upsert only**·link_id PK 멱등). off-path 는 `_FakeSession` 크래시 테스트로 load-bearing 입증(하위호환).
- **④ migration readiness probe**(read-only): `identity_backlog_readiness.py` — alembic chain(0001~0009 linear)·gap(운영 0003→behind 6)·`pending_destructive`(미적용 **upgrade() 본문**의 drop_table/column 만 — downgrade drop 제외 → 0004~0009 **non-destructive**)·`operational_db_readiness`(alembic_version+information_schema). **운영 DB upgrade 미적용**(배포 행위·무단 destructive 금지).
- **⑤ 측정(정직)**: live-PG ingest(adjudicate_semantic=True) 2 batch → events 2(병합 0)·event_links 1(②)·**event_identity_adjudication 1 자동(③·수동 호출 0)**·`summary.adjudications=1`. ingest→packet: eligible 1·**live_selected 1(운영 loop 유래)**·Event 불변. off → adjudication 0(게이트). 재실행 → upsert 멱등(1 유지). test DB readiness: on_head·ready_for_stage3·non-destructive.
- **adversarial 평결**: JUSTIFIED(부분진전) — no-auto-merge(shadow write 1개)·idempotent·off-by-default load-bearing·"운영 백로그"=wired(능력)≠production(actuality) 정직 구분(R-LiveIdentityBacklog OPEN 유지)·migration probe(upgrade-body 격리) VALID·**과잉 종결 0**. 문서화 권고 반영: no-cluster 배치 backfill 갭·O(N) 전수 재판정 비용(운영 closure 메모).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48**: ingest 후 flag-gated 자동 누적) → ④ 실 병합(**미구현**). **④ 전 선결 = identity eval gate**(ADR#43) **+ human gold workflow**(ADR#44) **+ reviewer agreement protocol**(ADR#45) **+ labeling packet**(ADR#46) **+ live packet pilot**(ADR#47) **+ stage③ operational wiring**(ADR#48).
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 network fetch·주기 job(no-cluster backfill)·incremental adjudication(O(N))·실 병합·실 human gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE 배선. "배선(능력) ≠ production(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=**반응 evidence**(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: stage③ 운영 배선은 deterministic shadow(자동 병합 0)·packet 은 internal ops artifact. final IU=curated synthesis(미구축). 단계 ③ 자동 누적이 reviewer/gold/RAG-KG 의 안전 substrate 를 운영에서 채우는 첫 배선(단 운영 가동 잔여).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전: R-LiveIdentityBacklog**(stage③ flag 배선[ingest 후 자동 adjudication·자동 병합 0]·migration readiness probe·live-PG ingest→③→packet E2E DONE; 운영 DB 배포·실 fetch·주기 job·incremental 잔여·완전종결 금지).
- **갱신: R-RealSourceLoopUnproven**(운영 DB 0003 vs head 0009 6 revision 뒤·non-destructive 정량화).
- **R-Stage3AdjudicationWiring·R-OperationalDbMigration 미등록**(R-LiveIdentityBacklog 가 정확히 그 blocker 추적·R-RealSourceLoopUnproven/R-SemanticIdentityAdjudicator 와 중복 회피·RISK 남발 금지).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위) + flag on + 실 fetch 필요 → 배선 DONE·production 0(R-LiveIdentityBacklog).
- **주기 job / no-cluster backfill**: `if not clusters: return` 으로 클러스터 없는 배치는 ③ 미실행 → 주기 trigger 필요(이월).
- **incremental adjudication**: 매 배치 O(N) 전수 재판정 → 운영 볼륨 시 미판정 link 만/배치 상한 필요(이월·안전 아님).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외(배포/네트워크 의존).
- UNKNOWN: 실 병합 허용 기준(production precision·실 human-labeled gold·reviewer 합의 실측·sampling 대표성·한국어 캘리브레이션·MERGE_GATE 배선) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#48 code 3 + config 1 + tests 3 + docs 8 (총 15파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** 운영 DB(event_intel) 0009 배포(운영 승인 하) + `EVENT_RESOLUTION_ENABLED`/`EVENT_SEMANTIC_ADJUDICATION_ENABLED` on + 주기 job(no-cluster backfill·incremental adjudication) → 실 cross-source fetch 볼륨으로 운영 백로그 누적 → 다중 reviewer 배정·합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE 충족·런타임 배선) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `9d466c4`(ADR#47). 코드: `event_ingest_pipeline`(stage③ 배선)·`config`(flag)·`identity_backlog_readiness`(신규·readiness).
- 검증: backend 비-live **455p/4s** · live-PG **71p**(stage③/readiness 5) · ingestion **1353p** · frontend tsc0/test12/lint0. 신규 13(결정론 8 + live-PG 5). 측정: ingest(adj=True)→adjudication 1 자동·packet eligible 1·live_selected 1·off→adjudication 0·재실행 멱등·운영 0003 vs head 0009 behind 6·non-destructive.
- 문서: ADR#48(`_DECISIONS`)·R-LiveIdentityBacklog 부분진전+R-RealSourceLoopUnproven(`_RISK/RISK_REGISTER`)·`RAG_KG_AGENT_READINESS §4`·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-24 · ADR#48 stage③ shadow adjudication operational wiring + migration readiness. `event_ingest_pipeline.ingest_records_to_events(adjudicate_semantic=)` 가 클러스터 루프(② link) 뒤 flag(`EVENT_SEMANTIC_ADJUDICATION_ENABLED`·off-by-default) on 이면 `adjudicate_semantic_links`(③)를 배치 전역 1회 자동 실행→event_identity_adjudication 백로그 자동 누적(자동 병합 0·shadow write only·link_id PK 멱등·try/except 격리·`summary.adjudications`). config flag + `.env.example`. 신규 `identity_backlog_readiness.py`(read-only: load_migration_chain[0001~0009 linear]·compute_migration_gap·pending_destructive[upgrade 본문 drop_table/column 만]·operational_db_readiness[alembic_version+information_schema]). **측정(정직): 운영 DB 0003 vs head 0009 = 6 revision 뒤(0004~0009 upgrade additive·non-destructive)·identity 테이블 부재; test DB 0009 HEAD(ready_for_stage3). live-PG: ingest(adjudicate_semantic=True)→adjudication 1 자동(수동 0)·packet eligible 1·live_selected 1(운영 loop 유래)·Event 불변·off→0·재실행 멱등. 운영 DB upgrade 미적용(배포 행위)·실 fetch 0 → production 백로그 0.** 옵션 A 채택·B fallback·C 단독 금지·D optional smoke. adversarial JUSTIFIED(부분진전·no-merge·off-path load-bearing·과잉 종결 0·문서화 권고[no-cluster backfill·O(N) 비용] 반영). **R-LiveIdentityBacklog 부분진전·R-RealSourceLoopUnproven 갱신**·완전종결=OVERCLAIM·R-Stage3AdjudicationWiring/R-OperationalDbMigration 미등록(RISK 남발 금지). **backend 비-live 455p/4s · live-PG 71p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#47 커밋 `9d466c4` 위 ADR#48 미커밋(code 3+config 1+tests 3+docs 8=15파일)·커밋 지시 대기·push 안 함._
