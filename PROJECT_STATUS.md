# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 검수 후보 판정(③)을 운영에서 **싸고 안전하게** 돌리도록 고쳤습니다. ① 이미 판정한 건 다시 안 보고 **새 것만** 판정(비용↓), ② 수집할 새 묶음이 없어도 **밀린 후보를 따라잡기**(no-cluster backfill), ③ 밀린 백로그를 한 번에 정해진 양만 처리하는 **별도 도구**(dry-run 지원)를 추가했습니다. 또 운영 DB를 0003→0009로 올리는 **배포 절차서(runbook)**를 적었습니다(실행은 승인 후). 자동 합치기는 계속 0.
- **이번 턴에 실제로 끝낸 것:** ADR#48 커밋(`8f47d29`) → **ADR#49 구현**: `adjudicate_semantic_links(only_unadjudicated=,limit=)` incremental + `ingest_records_to_events` no-cluster backfill(`if not clusters: return` 제거) + 신규 `backfill_semantic_adjudications.py`(dry-run·bounded) + 운영 DB 배포 runbook. 측정: **backend 비-live 456p/4s · live-PG 78p · ingestion 1353p · frontend tsc0/test12/lint0**. adversarial **코드 JUSTIFIED**(MEDIUM 1=ambiguity 회귀 가드 추가·HIGH 1=본 docs 작성으로 해소).
- **정직한 한계:** backfill은 **능력**입니다 — 운영 DB는 여전히 0003(미적용), flag off, 실 fetch 0이라 **production 백로그는 0**입니다. cheap 전수 스캔은 여전히 O(전체 link)·주기 스케줄러·동시 직렬화 잔여. 실 reviewer 합의·gold·병합은 0. push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `8f47d29`**(ADR#48, 본 턴 첫 커밋) 위 **ADR#49 = 미커밋 code 2(`semantic_identity_adjudicator.py` incremental + `event_ingest_pipeline.py` no-cluster) + tool 1(신규 `backfill_semantic_adjudications.py`) + tests 2(`test_event_ingest_pipeline`[+1] + `test_event_resolution_live_pg`[+7]) + docs 8**. **migration 없음**.
- code: `adjudicate_semantic_links(*, only_unadjudicated=False, limit=None)` + `_adjudicated_link_ids`(id-only) — 미판정 link 만 비싼 view-load+persist(O(N) 완화)·ambiguity 는 cand_targets 전체 산출(필터 전·회귀 가드). `ingest_records_to_events`: `if not clusters: return` 제거→`if clusters:`·stage③ `only_unadjudicated=True`(no-cluster backfill). 신규 `backfill_semantic_adjudications.py`(read+adjudication upsert only·`count_pending_semantic_links`·dry-run·bounded·event count before-after·auto_merge_enabled=False). docs: ADR#49(`_DECISIONS`)·RISK_REGISTER(R-LiveIdentityBacklog gap②③ 해소)·15_ROADMAP(**배포 runbook**)·CANONICAL/02·ROADMAP/00·RAG_KG_AGENT_READINESS·INTELLIGENCE_UNIT_CONTRACT.
- 열린 RISK: **R-LiveIdentityBacklog 부분진전**(gap②③ 해소: incremental·no-cluster backfill·backfill tool·runbook DONE; 운영 DB 배포·실 fetch·주기 스케줄러·cheap-scan keyset·동시 직렬화 잔여) · R-RealSourceLoopUnproven · R-SemanticIdentityAdjudicator · R-IdentityEvalDataset · R-IdentityHumanLabeling · R-ReviewerAgreement · R-GoldSamplingBias · R-CrossBatchEventIdentity(open). throwaway는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (incremental / no-cluster backfill + runbook — ADR#49)
- **① ADR#48 커밋**: 15파일 → `8f47d29`(secret PASS·docs_lifecycle 0·closeout EXACT MATCH 후, push 0).
- **② 원자 분석**: ADR#48 adversarial 두 갭 확정 — (a) `if not clusters: return` 으로 no-cluster ③ 미실행 (b) 매 배치 전수 재판정 O(N)(link 마다 2 Event view 재조회). 운영 DB 배포 runbook 부재.
- **③ incremental adjudication**(옵션 A): `adjudicate_semantic_links(only_unadjudicated=,limit=)` — 미판정 link 만 비싼 work·**ambiguity 정확성 불변**(cand_targets 는 incremental 필터 **전** 전체 link 로 산출→부분 선판정된 모호 candidate 도 나머지 link ambiguous; **회귀 가드 테스트 추가**). limit=link id 정렬 결정론 chunk.
- **④ no-cluster backfill + backfill tool**(옵션 A+B): `ingest_records_to_events` early-return 제거→클러스터 0 배치도 stage③ `only_unadjudicated=True` backfill. 신규 `backfill_semantic_adjudications.py`(dry-run·bounded·read+adjudication only·event count·auto_merge_enabled=False).
- **⑤ 운영 DB 배포 runbook**(옵션 C): `15_ROADMAP §` 에 0003→0009 절차(current→head→pending→destructive→backup→upgrade→table→readiness→rollback) + flag 순서(EVENT_RESOLUTION_ENABLED→0009→readiness PASS→EVENT_SEMANTIC_ADJUDICATION_ENABLED→backfill dry-run→limited→packet/reviewer). **운영 upgrade 미실행**.
- **⑥ 측정(정직)**: live-PG only_unadjudicated 재실행→판정 link skip(전수 회피·멱등). limit=1→2 link 2 chunk 결정론. backfill dry-run(영속 0)→persist(pending 1→0)·Event 불변. no-cluster 배치(pending 1)→adjudications 1. packet exclusion 1→0(eligible 0→1). ambiguity 부분 선판정 회귀 가드.
- **adversarial 평결**: 코드 JUSTIFIED(ambiguity 순서·no-merge·idempotent/limit 결정론·no-cluster 재구조·과잉 종결 0). MEDIUM 1 해소(ambiguity 회귀 가드 테스트)·HIGH 1 해소(본 docs/runbook/RISK 작성)·LOW 3 메모(동시 backfill 직렬화·cheap O(all) 스캔 keyset·`rss` 어휘 정합).

## 🧭 cross-batch identity 4단계 + 평가/gold gate (정직)
- ① anchor 병합(ADR#40) → ② 후보 LINK(ADR#41) → ③ shadow 판정(ADR#42·**운영 배선 ADR#48·incremental+no-cluster backfill ADR#49**) → ④ 실 병합(**미구현**). **④ 전 선결 = eval gate(ADR#43)+gold workflow(ADR#44)+reviewer agreement(ADR#45)+labeling packet(ADR#46)+live packet pilot(ADR#47)+stage③ wiring(ADR#48)+incremental/backfill(ADR#49)**.
- **⚠ 미해소(OPEN):** 운영 DB 0003→0009 배포·실 fetch·주기 스케줄러·cheap-scan keyset·동시 직렬화·실 병합·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE. "배선(능력) ≠ production(actuality)" — 완전종결=OVERCLAIM.

## 🔎 source orchestration / 제품 계약
- official/news=publishable evidence·community=반응 evidence(merge anchor 불가)·market=signal·catalog=entity·search=URL·unknown=fail-closed.
- **제품 계약(raw≠public)**: incremental/backfill 은 deterministic shadow(자동 병합 0·read+adjudication upsert only). `INTELLIGENCE_UNIT_CONTRACT §4` 에 incremental/backfill 노트 추가. final IU=curated synthesis(미구축).

## ⚠️ 이번 턴 종결/갱신 RISK
- **부분진전(gap②③ 해소): R-LiveIdentityBacklog**(incremental·no-cluster backfill·backfill tool·배포 runbook DONE; 운영 DB 배포·실 fetch·주기 스케줄러·cheap-scan keyset·동시 직렬화 잔여·완전종결 금지).
- **R-IncrementalAdjudicationCost·R-NoClusterBackfill 미등록**(이번 턴 해소·R-LiveIdentityBacklog gap 으로 추적·RISK 남발 금지). R-OperationalDbMigration 미등록(R-RealSourceLoop/R-LiveIdentityBacklog 추적).

## ❌ 달성하지 못한 것 & 왜 (이월)
- **운영 production 백로그**: 운영 DB 0009 배포(배포 행위·runbook 작성됨·미실행) + flag on + 실 fetch 필요 → 능력 DONE·production 0.
- **주기 스케줄러**: backfill tool 은 entry·Celery beat/cron 자동 가동 미배선(이월).
- **cheap O(all-links) 전수 스캔**: `_semantic_links`/`_adjudicated_link_ids` id-only 는 여전히 전수(비싼 view-load 만 bounded)·대형 백로그 keyset 필요(이월).
- **실 병합/gold/합의**: embedding/LLM/KG + MERGE_GATE·실 human gold·reviewer 합의 필요·미구축.

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED: 운영 production 백로그 = 운영 DB 0009 배포(배포 행위) + 실 source fetch 볼륨 선결 — 이번 턴 범위 외.
- UNKNOWN: 실 병합 허용 기준(production precision·실 gold·reviewer 합의·sampling 대표성·한국어 캘리브레이션·MERGE_GATE) → R-IdentityHumanLabeling·R-ReviewerAgreement·R-GoldSamplingBias·R-IdentityEvalDataset 선결.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 ADR#49 code 2 + tool 1 + tests 2 + docs 8 (총 13파일) 커밋 여부 지시 대기. push 금지.
2. **[다음 단계]** (운영 승인 하) 운영 DB 0009 배포(runbook) + flag on + backfill dry-run/limited → 주기 스케줄러(Celery beat) 배선·동시 직렬화 명세·cheap-scan keyset → 실 cross-source fetch 볼륨 → 다중 reviewer 합의 gold → 한국어 캘리브레이션 → embedding/LLM/KG **실 병합** adjudicator(MERGE_GATE) → RAG/KG.

## 📁 근거 (이번 턴 핵심)
- 커밋: `8f47d29`(ADR#48). 코드: `semantic_identity_adjudicator`(incremental)·`event_ingest_pipeline`(no-cluster)·`backfill_semantic_adjudications`(신규).
- 검증: backend 비-live **456p/4s** · live-PG **78p**(incremental/backfill/no-cluster/ambiguity 가드 7) · ingestion **1353p** · frontend tsc0/test12/lint0. 신규 8(결정론 1 + live-PG 7). 측정: only_unadjudicated skip·limit chunk·backfill pending 1→0·no-cluster adjudications 1·packet exclusion 1→0·Event 불변·멱등·ambiguity 가드.
- 문서: ADR#49(`_DECISIONS`)·R-LiveIdentityBacklog gap②③ 해소(`_RISK/RISK_REGISTER`)·배포 runbook(`2_ROADMAP/15`)·`_CANONICAL/02`·`2_ROADMAP/00`·`RAG_KG_AGENT_READINESS §4`·`INTELLIGENCE_UNIT_CONTRACT §4`.

---
_as_of: 2026-06-24 · ADR#49 incremental / no-cluster backfill adjudication + 운영 DB 배포 runbook. `adjudicate_semantic_links(*, only_unadjudicated=False, limit=None)` + `_adjudicated_link_ids` — 미판정 link 만 비싼 per-link Event view load+persist(O(N) 완화)·ambiguity(cand_targets)는 incremental 필터 **전** 전체 link 로 산출(회귀 가드 테스트). `ingest_records_to_events`: `if not clusters: return` 제거→no-cluster 배치도 stage③ `only_unadjudicated=True` backfill. 신규 `backfill_semantic_adjudications.py`(read+adjudication upsert only·`count_pending_semantic_links`·dry-run·bounded limit·event count before-after·auto_merge_enabled=False). 운영 DB 0003→0009 배포 runbook(`15_ROADMAP §`·절차+flag 순서·실행 미승인). **측정(정직): live-PG only_unadjudicated 재실행 skip·limit=1 2-chunk 결정론·backfill dry-run(영속 0)→persist(pending 1→0)·no-cluster 배치 adjudications 1·packet exclusion 1→0·Event 불변·멱등·ambiguity 부분 선판정 회귀 가드. 운영 DB 0003 미적용·실 fetch 0 → production 백로그 0.** 옵션 A+B-일부+C 채택·D(즉시 upgrade) 금지. adversarial 코드 JUSTIFIED(ambiguity 순서·no-merge·idempotent/limit·no-cluster 재구조·과잉 종결 0)·MEDIUM 1 해소(회귀 가드)·HIGH 1 해소(docs/runbook/RISK)·LOW 3 메모(동시 직렬화·cheap O(all) keyset·rss 어휘). **R-LiveIdentityBacklog 부분진전(gap②③ 해소)**·완전종결=OVERCLAIM·R-IncrementalAdjudicationCost/R-NoClusterBackfill 미등록(해소·RISK 남발 금지). **backend 비-live 456p/4s · live-PG 78p · ingestion 1353p · frontend tsc0/test12/lint0**. ADR#48 커밋 `8f47d29` 위 ADR#49 미커밋(code 2+tool 1+tests 2+docs 8=13파일)·커밋 지시 대기·push 안 함._
