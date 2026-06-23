# 📊 프로젝트 진행 현황 (PROJECT_STATUS)

> 매 턴 끝에 새로 쓰입니다. 항상 "가장 최근 1턴"만. 과거는 `git log -- PROJECT_STATUS.md`.
> 사실 원본(자동): `.harness/machine_status.json` · 완료 증거: `.harness/closeout_stamp.json` · 서술: 이 파일(에이전트).

## 🟢 한눈에 (비개발자용 3줄)
- **지금 무엇을 했나:** 사건(Event)이 만들어질 때 **누가 사건의 "대표"가 되는지**를 출처 신뢰도 순으로 정했습니다(primary-authority). 공식·뉴스가 섞이면 공식/뉴스가 대표가 되고, **시장 숫자·커뮤니티는 절대 사건의 얼굴이 되지 않습니다**(상용 신뢰도).
- **이번 턴에 실제로 끝낸 것:** 먼저 source-type publish gate를 `8969a5e`로 커밋. 이어 **primary-authority 구현**: `candidate_from_cluster`가 클러스터 대표(제목·도메인·시각·증거 primary)를 **최고 authority 출처**(공식5>뉴스4>지표3>검색2>커뮤니티1>미지0)로 선정. **측정: backend 290 passed/4 skip/0 fail(+5) + ingestion 1331 = 1621 green · frontend tsc0/test12/lint0.** 결정론 단위 4(공식>커뮤니티·뉴스>시장·뉴스>커뮤니티 약신호·뉴스+뉴스 동률 회귀) + live-PG 1.
- **정직한 한계(adversarial):** **R-SourceTypeFidelityGate는 LOW 부분종결 유지**(완전 종결 아님). 제목 대표는 해소됐으나 **held-publishable DB 이중 등장**(유일 발행가능 멤버가 약신호로 분리되면 대표 증거이자 held degenerate로 동시 등장 — 화면엔 안 보이나 데이터 정합 잔여) + fail-open 잔여. P1 0. **BLOCKED 0.** push 금지.

## 📋 자동 수집 사실 (machine_status.json)
- **git HEAD `8969a5e`**(source-type publish gate, 본 턴 첫 커밋) 위 **primary-authority = 미커밋 code 1 + tests 2 + docs 6**. `machine_status.json` 은 직전 Stop 기준 **stale**(lag).
- code 1: `event_ingest_pipeline.py`(`_SOURCE_TYPE_AUTHORITY`+`_select_primary_by_authority`+candidate_from_cluster). tests 2: `test_event_ingest_pipeline`(+primary-authority 4)·`test_event_resolution_live_pg`(+1). docs 6: `PROJECT_STATUS`·`_DECISIONS/2026-06`(ADR#34)·`_RISK/RISK_REGISTER`(LOW 부분종결)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.
- 열린 RISK **29**(R-SourceTypeFidelityGate **LOW 부분종결=유지**, held 이중등장 잔여; 신규 0). throwaway(검증 하니스)는 `.harness/_TRASH/`(gitignored).

## ✅ 이번 턴에 달성한 것 (primary-authority — ADR#34)
- **구현**: `candidate_from_cluster` 가 cluster.primary_record_key(=members[0]) 대신 **distinct 멤버 중 최고 authority**(`_SOURCE_TYPE_AUTHORITY` official5>article4>signal3>search2>community1>미지0)를 대표로 — title/도메인/관측시각/delta_summary kind/evidence relation="primary" 모두 이 기준. tie=distinct_members 순서(결정적). 위치=`candidate_from_cluster` 단 1파일(cluster identity/source_refs/resolver held 무변경). 마이그레이션/schema/UI/API **0**.
- **효과**: mixed cluster(community+official, market+news)에서 **community/market 이 Event 대표가 되는 것 차단** — 발행되는(publishable 보유) cluster 의 대표는 항상 official/article. gate(ADR#33, 발행 가부)와 **직교**(authority=발행 시 대표).
- **검증**: 단위 4(official>community→공식 title·news>market→뉴스 kind·news>community 약신호→news primary·news+news 동률→members[0] 회귀) + live-PG 1(실 DB community+official→official canonical_title). cluster_id/source_refs/FSD 단조성 무영향(adversarial 확인).
- **adversarial 반영**: P1 0. P2(완전 종결 차단 — held-publishable DB 이중등장·fail-open)→**R-SourceTypeFidelityGate LOW 부분종결 유지(완전 종결 금지)**·잔여 명시. P3(미지 "rss" 사문·delta kind primary-only)=관찰.

## ❌ 달성하지 못한 것 & 왜 (이월)
- **held-publishable DB 이중 등장**: 유일 publishable 이 weak_only(held)면 primary-authority 가 그것을 대표(title)로 세우나, resolver 가 동시에 held degenerate event 로 분리 → 같은 record 가 대표 evidence ↔ held degenerate 이중 등장(화면 차단·데이터 정합 잔여). 해소엔 resolver held_members 에서 primary 제외 필요 → 이월.
- **fail-open**: 커스텀 `candidate_for` 가 source_type 미제공 시 gate·authority 우회(기본 매퍼 안전).
- **delta_summary kind primary-only**(corroborator 미반영, 경미).

## 🚧 닫을 수 없는 문제 (BLOCKED/UNKNOWN)
- BLOCKED 0. UNKNOWN: held-publishable 이중등장 제거의 resolver 영향 범위·실제 발생률.

## ⚠️ 이번 턴 종결/갱신 RISK
- **R-SourceTypeFidelityGate: LOW 부분종결(유지)** — gate(ADR#33, pure 비뉴스 발행 차단) + primary-authority(ADR#34, 대표 authority·**title 해소**). **완전 종결 아님**(adversarial: closure 의 held-publishable 잔여는 DB 이중등장으로 미충족·fail-open). Closure: held degenerate 이중등장 제거 + fail-open 가드.
- **종결 0**(부분종결만; 완전 종결 금지 — adversarial). 유지: RealSourceLoop·S2Hardening·ModelMigration·FalseMerge·ExpansionPartialFailure·ApiScale.

## 👉 다음 할 일
1. **[커밋 대기]** 본 턴 code 1 + tests 2 + docs 6 커밋 여부 지시 대기. push 금지.
2. **[다음 단계 = R-SourceTypeFidelityGate 완전 종결]** held-publishable 멤버가 대표일 때 resolver `held_members` 에서 primary 제외(DB 이중등장 제거) + fail-open 가드(candidate_for source_type 강제). → 완전 종결. (그 다음) 실 cross-source 비뉴스 Event·실 fetch APPEND·주기 auto-trigger·full compose E2E.

## 📁 근거 (이번 턴 핵심)
- 코드: `event_ingest_pipeline.py`(`_SOURCE_TYPE_AUTHORITY`·`_select_primary_by_authority`·candidate_from_cluster authority primary).
- 검증: 단위 4(`test_event_ingest_pipeline`)+live-PG 1(`test_event_resolution_live_pg`) — backend 290. frontend tsc0/test12/lint0.
- 문서: ADR#34(`_DECISIONS`)·R-SourceTypeFidelityGate LOW 부분종결(`_RISK/RISK_REGISTER`)·`_CANONICAL/02`·`2_ROADMAP/{00,15}`.

---
_as_of: 2026-06-23 · primary-authority(ADR#34) — `candidate_from_cluster` 가 mixed cluster 의 Event 대표(title/도메인/관측시각/delta_summary kind/primary evidence)를 최고 authority source(official5>article4>signal3>search2>community1>미지0)로 선정. **community/market 이 Event 대표가 되는 것 차단**(발행 cluster 대표는 항상 official/article). tie=입력순(결정적·단일타입 회귀 0). gate(ADR#33)와 직교. 위치=candidate_from_cluster 1파일(cluster identity/source_refs/held 무변경·마이그레이션/schema/UI 0). 검증 단위 4+live-PG 1(**backend 290 passed/4 skip/0 fail + ingestion 1331 = 1621 green · frontend tsc0/test12/lint0**). adversarial: P1 0·구현 정확/결정적/회귀 0/FSD 무영향; **R-SourceTypeFidelityGate LOW 부분종결 유지(완전 종결 금지** — held-publishable DB 이중등장·fail-open 잔여). 열린 RISK 29(부분종결 유지)·code 1+tests 2+docs 6 미커밋(커밋 지시 대기)·push 안 함._
